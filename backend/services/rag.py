"""
RAG service — embedding-on-upload pipeline + retrieval for MediSync 2.0.

Write path (upload pipeline):
  build_chunks(record)
      Converts structured extraction output (medications, lab values, diagnoses,
      summary) into short, natural-language sentences suitable for embedding.

  embed_and_store_chunks(record_id, user_id, chunks)
      Embeds the chunks via services.embeddings and upserts them into the
      record_chunks table (idempotent: old chunks are deleted first).

Read path (/api/chat endpoint):
  search_records(user_id, query, k)
      Embeds the query and calls the match_record_chunks RPC.  RLS scopes
      results to the caller's rows — no extra filter needed.

  is_relevant(matches)
      Deterministic refusal gate: returns True only when the top result clears
      SIMILARITY_FLOOR.  The LLM is never invoked on a False return; this is
      the "never hallucinate" guarantee.

The match_record_chunks Postgres function (008_record_chunks.sql) does the
actual cosine-similarity ranking at query time.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_CHUNK_LEN = 300

# Minimum cosine similarity for a retrieval result to be considered relevant.
# When the top match falls below this threshold, is_relevant() returns False and
# the /api/chat endpoint refuses to answer rather than risk hallucinating an
# answer from unrelated context.  Tune this value against real patient queries;
# 0.65 is a conservative starting point for 768-dim Gemini embeddings.
SIMILARITY_FLOOR = 0.58


# ── Chunk construction ────────────────────────────────────────────────────────

def build_chunks(record: dict) -> list[str]:
    """Convert one record's structured extraction into semantic sentence chunks.

    Each chunk is a standalone sentence describing a single clinical item so
    that cosine similarity against a patient query is meaningful and precise.

    Args:
        record: dict with keys:
            medications  – list of medication DB rows (name, dosage, frequency, …)
            lab_values   – list of lab-value DB rows after reference fallback
                           (test_name, value, unit, reference_range, is_abnormal, …)
            diagnoses    – list of str or dict from LLM extraction
            summary      – clinical summary string (may be empty)

    Returns:
        List of strings each ≤ _MAX_CHUNK_LEN characters.
    """
    chunks: list[str] = []

    # ── Medications ───────────────────────────────────────────────────────────
    for med in record.get("medications", []):
        name = (med.get("name") or med.get("drug_name") or "").strip()
        if not name:
            continue
        parts = [name]
        if med.get("dosage"):
            parts.append(str(med["dosage"]).strip())
        if med.get("frequency"):
            parts.append(str(med["frequency"]).strip())
        if med.get("duration"):
            parts.append(f"for {str(med['duration']).strip()}")
        chunk = ", ".join(parts) + "."
        if chunk and len(chunk) <= _MAX_CHUNK_LEN:
            chunks.append(chunk)

    # ── Lab values ────────────────────────────────────────────────────────────
    for lab in record.get("lab_values", []):
        test_name = (lab.get("test_name") or "").strip()
        value     = str(lab.get("value") or "").strip()
        if not test_name or not value:
            continue

        unit = (lab.get("unit") or "").strip()
        val_str = f"{value}{unit}" if unit else value
        parts: list[str] = [f"{test_name}: {val_str}"]

        ref = (lab.get("reference_range") or "").strip()
        if ref:
            parts.append(f"reference range {ref}")

        abnormal = lab.get("is_abnormal")
        if abnormal is True:
            parts.append("flagged ABNORMAL")
        elif abnormal is False:
            parts.append("within normal range")

        date = (lab.get("document_date") or "").strip()
        if date:
            parts.append(f"dated {date}")

        chunk = ", ".join(parts) + "."
        if len(chunk) <= _MAX_CHUNK_LEN:
            chunks.append(chunk)

    # ── Diagnoses ─────────────────────────────────────────────────────────────
    for diag in record.get("diagnoses", []):
        if isinstance(diag, str):
            text = diag.strip()
        elif isinstance(diag, dict):
            text = (diag.get("name") or diag.get("diagnosis") or "").strip()
        else:
            continue
        if text:
            chunk = f"Diagnosis: {text}."
            if len(chunk) <= _MAX_CHUNK_LEN:
                chunks.append(chunk)

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = (record.get("summary") or "").strip()
    if summary:
        # Hard-cap at _MAX_CHUNK_LEN; a well-formed summary is usually shorter.
        chunk = f"Summary: {summary}"
        chunks.append(chunk[:_MAX_CHUNK_LEN])

    return chunks


# ── Embedding + storage ───────────────────────────────────────────────────────

async def embed_and_store_chunks(
    record_id: str,
    user_id: str,
    chunks: list[str],
) -> None:
    """Embed chunks and upsert into record_chunks (idempotent).

    Deletes all existing rows for record_id before inserting so that
    re-processing a record never duplicates chunks.

    Args:
        record_id: UUID of the parent health_records row.
        user_id:   UUID of the owning patient (written into user_id column for RLS).
        chunks:    Sentences produced by build_chunks().
    """
    from services import embeddings as emb_svc
    from utils.db import get_supabase

    supabase = get_supabase()

    # Remove stale chunks so re-upload is idempotent.
    supabase.table("record_chunks").delete().eq("record_id", record_id).execute()

    if not chunks:
        return

    # embed_documents is a synchronous network call — run in thread pool so we
    # don't block the FastAPI event loop during the upload response.
    vectors: list[list[float]] = await asyncio.to_thread(emb_svc.embed_documents, chunks)

    rows = [
        {
            "record_id": record_id,
            "user_id":   user_id,
            "content":   text,
            # pgvector expects the text representation "[f1,f2,…]"
            "embedding": f"[{','.join(str(x) for x in vec)}]",
        }
        for text, vec in zip(chunks, vectors)
    ]
    supabase.table("record_chunks").insert(rows).execute()
    logger.info("Stored %d RAG chunk(s) for record %.8s.", len(rows), record_id)


# ── Retrieval (used by /api/chat endpoint) ────────────────────────────────────

async def search_records(user_id: str, query: str, k: int = 5) -> list[dict]:
    """Semantic search over the caller's records via the match_record_chunks RPC.

    RLS on record_chunks already scopes results to user_id — do NOT add a
    PostgREST .eq() filter after .rpc().  A filter applied at that layer runs
    after the SQL function has already ranked and limited rows, so it would
    silently drop valid results and return fewer than k matches.

    Args:
        user_id: UUID of the authenticated patient (used only for logging;
                 RLS enforces scoping, not an explicit filter here).
        query:   Natural-language question string.
        k:       Number of most-relevant chunks to return (passed to the RPC).

    Returns:
        List of {record_id, content, similarity} dicts, ordered closest first.
        similarity is 1 − cosine_distance, so higher = more relevant.
    """
    from services import embeddings as emb_svc
    from utils.db import get_supabase

    # embed_query is a synchronous network call — offload so we don't stall the loop.
    query_vec: list[float] = await asyncio.to_thread(emb_svc.embed_query, query)

    supabase = get_supabase()
    response = supabase.rpc(
        "match_record_chunks",
        {
            "query_embedding": f"[{','.join(str(x) for x in query_vec)}]",
            "match_count": k,
        },
    ).execute()

    matches: list[dict] = response.data or []
    logger.debug(
        "RAG search for user %.8s: %d result(s), top similarity=%.3f",
        user_id,
        len(matches),
        matches[0]["similarity"] if matches else 0.0,
    )
    return matches


def is_relevant(matches: list[dict]) -> bool:
    """Return True only when retrieval found something above SIMILARITY_FLOOR.

    This is the deterministic refusal gate for /api/chat: if the top result's
    cosine similarity does not clear the floor, the patient's question has no
    grounding in their actual records and we must refuse rather than let the LLM
    confabulate an answer.  The LLM is never called when this returns False.

    Design note: the check is intentionally simple and stateless — one threshold,
    one comparison — so it can be audited and tuned without touching LLM logic.
    """
    if not matches:
        return False
    # matches is ordered by the RPC (closest first); index 0 is the best hit.
    return float(matches[0].get("similarity", 0.0)) >= SIMILARITY_FLOOR
