"""
Gemini Embedding Service — wraps gemini-embedding-001 via the google-genai SDK.

task_type asymmetry: RETRIEVAL_DOCUMENT optimises stored chunk vectors for being
retrieved; RETRIEVAL_QUERY optimises the search vector so cosine distance between
the two types is maximised for relevant pairs.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = "gemini-embedding-001"
_BATCH_SIZE = 100  # Gemini embedding API limit per call

# Lazily initialised — same pattern as ocr.py / llm.py.
_client: Optional[object] = None  # google.genai.Client once initialised


def _get_client() -> Optional[object]:
    """Lazy-init the google-genai Client.  Returns None if key not configured."""
    global _client
    if _client is not None:
        return _client
    try:
        from utils.config import settings

        if not settings.gemini_api_key:
            logger.warning("GEMINI_API_KEY not set — embeddings unavailable.")
            return None

        from google import genai  # type: ignore[import-untyped]

        _client = genai.Client(api_key=settings.gemini_api_key)
        logger.info("Gemini embedding client initialised (model=%s).", _EMBEDDING_MODEL)
        return _client
    except ImportError:
        logger.warning("google-genai not installed — embeddings unavailable.")
        return None


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a list of document chunks for storage.

    Uses task_type RETRIEVAL_DOCUMENT.  Splits into sub-batches of at most
    _BATCH_SIZE texts so large uploads don't hit API limits in one shot.

    Returns one 768-float vector per input text, in the same order.
    """
    if not texts:
        return []

    client = _get_client()
    if client is None:
        raise RuntimeError("Gemini embedding client is not available.")

    from google.genai import types  # type: ignore[import-untyped]

    config = types.EmbedContentConfig(
        task_type="RETRIEVAL_DOCUMENT",
        output_dimensionality=768,
    )

    results: list[list[float]] = []

    for batch_start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[batch_start : batch_start + _BATCH_SIZE]
        response = client.models.embed_content(
            model=_EMBEDDING_MODEL,
            contents=batch,
            config=config,
        )
        for embedding in response.embeddings:
            results.append(embedding.values)

    return results


def embed_query(text: str) -> list[float]:
    """Embed a single search query.

    Uses task_type RETRIEVAL_QUERY so the resulting vector is comparable
    against RETRIEVAL_DOCUMENT vectors stored in pgvector.

    Returns one 768-float vector.
    """
    client = _get_client()
    if client is None:
        raise RuntimeError("Gemini embedding client is not available.")

    from google.genai import types  # type: ignore[import-untyped]

    config = types.EmbedContentConfig(
        task_type="RETRIEVAL_QUERY",
        output_dimensionality=768,
    )

    response = client.models.embed_content(
        model=_EMBEDDING_MODEL,
        contents=text,
        config=config,
    )
    # Single content → single embedding in the list.
    return response.embeddings[0].values
