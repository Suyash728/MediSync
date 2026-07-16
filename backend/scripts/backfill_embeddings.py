"""
One-off backfill: embed all existing health_records into record_chunks.

Re-uses services.rag.build_chunks + embed_and_store_chunks directly, so the
chunk format and idempotency behaviour are identical to the live upload pipeline.

Usage (from the backend/ directory, with your venv active):

    # All patients:
    python scripts/backfill_embeddings.py

    # Single patient:
    python scripts/backfill_embeddings.py 8c5cf54d-72f5-4a0d-adb4-d06a5fb4706b

Note: diagnoses are not stored in the DB (they live only in the LLM response at
upload time), so backfilled chunks will not include diagnosis sentences.  Every
other field (medications, lab values with ranges + flags, summary) is included.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Put backend/ on sys.path so we can import from services/, utils/, etc.
# Run this script from the backend/ directory so pydantic-settings finds .env there.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# These imports trigger pydantic-settings to load .env — must come after sys.path patch.
from utils.db import get_supabase          # noqa: E402
from services import rag as rag_svc        # noqa: E402


async def backfill(user_id: str | None) -> None:
    supabase = get_supabase()

    # ── Fetch records ─────────────────────────────────────────────────────────
    query = (
        supabase.table("health_records")
        .select("id, patient_id, summary, processing_status")
    )
    if user_id:
        query = query.eq("patient_id", user_id)

    result = query.execute()
    records: list[dict] = result.data or []

    if not records:
        print("No records found" + (f" for user {user_id}" if user_id else "") + ".")
        return

    print(f"Found {len(records)} record(s).  Starting backfill…\n")

    ok_count    = 0
    skip_count  = 0
    error_count = 0
    total_chunks = 0

    for i, record in enumerate(records, 1):
        record_id  = record["id"]
        patient_id = record["patient_id"]
        short_id   = record_id[:8]
        prefix     = f"  [{i:>{len(str(len(records)))}}/{len(records)}] {short_id}…"

        # Fetch persisted structured data for this record.
        # Service-role client bypasses RLS — returns rows for any patient.
        meds = (
            supabase.table("medications")
            .select("name, dosage, frequency, duration, document_date")
            .eq("record_id", record_id)
            .execute()
            .data or []
        )
        labs = (
            supabase.table("lab_values")
            .select("test_name, value, unit, reference_range, is_abnormal, document_date")
            .eq("record_id", record_id)
            .execute()
            .data or []
        )

        record_data = {
            "medications": meds,
            "lab_values":  labs,
            "diagnoses":   [],          # not persisted to DB; cannot recover
            "summary":     record.get("summary") or "",
        }

        chunks = rag_svc.build_chunks(record_data)

        if not chunks:
            print(f"{prefix}  0 chunks — skipped (no extractable content)")
            skip_count += 1
            continue

        try:
            await rag_svc.embed_and_store_chunks(record_id, patient_id, chunks)
            print(f"{prefix}  {len(chunks)} chunk(s) stored")
            total_chunks += len(chunks)
            ok_count += 1
        except Exception as exc:
            print(f"{prefix}  ERROR — {exc}", file=sys.stderr)
            error_count += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"""
─────────────────────────────────────────
Backfill complete.
  Records processed : {ok_count}
  Records skipped   : {skip_count}  (no content to chunk)
  Errors            : {error_count}
  Total chunks      : {total_chunks}
─────────────────────────────────────────""")

    if error_count:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill record_chunks embeddings for existing health_records.",
    )
    parser.add_argument(
        "user_id",
        nargs="?",
        default=None,
        metavar="PATIENT_UUID",
        help="Restrict backfill to a single patient UUID (optional).",
    )
    args = parser.parse_args()

    asyncio.run(backfill(args.user_id))


if __name__ == "__main__":
    main()
