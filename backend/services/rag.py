"""
RAG service — embedding-on-upload pipeline for MediSync 2.0.

Two public callables used by the upload pipeline:

  build_chunks(record)
      Converts structured extraction output (medications, lab values, diagnoses,
      summary) into short, natural-language sentences suitable for embedding.

  embed_and_store_chunks(record_id, user_id, chunks)
      Embeds the chunks via services.embeddings and upserts them into the
      record_chunks table (idempotent: old chunks are deleted first).

The match_record_chunks Postgres function (008_record_chunks.sql) does the
actual cosine-similarity retrieval at query time; we only write here.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_CHUNK_LEN = 300


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


# ── Retrieval (used by /api/chat endpoint, Phase 3) ──────────────────────────

async def search_records(patient_id: str, query: str, top_k: int = 5) -> list[dict]:
    """Semantic search over a patient's records via match_record_chunks RPC.

    RLS on record_chunks scopes the search to the calling user's rows.
    match_record_chunks orders by cosine distance (brute-force, exact at our scale).

    Args:
        patient_id: UUID of the patient (used to build the authed supabase client).
        query:      Natural-language question string.
        top_k:      Number of most-relevant chunks to return.

    Returns:
        List of {record_id, content, similarity} dicts ordered closest first.
    """
    from services import embeddings as emb_svc
    from utils.db import get_supabase

    query_vec: list[float] = await asyncio.to_thread(emb_svc.embed_query, query)

    supabase = get_supabase()
    response = supabase.rpc(
        "match_record_chunks",
        {
            "query_embedding": f"[{','.join(str(x) for x in query_vec)}]",
            "match_count": top_k,
        },
    ).execute()

    return response.data or []
