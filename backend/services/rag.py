"""
RAG (Retrieval-Augmented Generation) service — optional Phase 3+.

Uses sentence-transformers all-MiniLM-L6-v2 (384-dim) to embed record chunks
and Supabase pgvector for similarity search. Allows patients to ask natural-
language questions over their own records ("What was my last cholesterol reading?").

This stub will be replaced with the real implementation in Phase 3 (optional).
"""

# from sentence_transformers import SentenceTransformer
# from utils.config import settings


async def embed_record_chunks(record_id: str, text: str) -> None:
    """Split text into chunks, embed with all-MiniLM-L6-v2, store in pgvector.

    Args:
        record_id: UUID of the record being embedded.
        text:      Full text of the record (OCR output or parsed content).
    """
    raise NotImplementedError("RAG embedding will be implemented in Phase 3 (optional).")


async def search_records(patient_id: str, query: str, top_k: int = 5) -> list[dict]:
    """Semantic search over a patient's records.

    Args:
        patient_id: UUID of the patient (RLS ensures we only search their data).
        query:      Natural-language query string.
        top_k:      Number of most-relevant chunks to return.

    Returns:
        List of {record_id, chunk_text, similarity_score} dicts.
    """
    raise NotImplementedError("RAG search will be implemented in Phase 3 (optional).")
