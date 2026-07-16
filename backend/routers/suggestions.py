"""
GET /suggestions — return cached checkup suggestions (paid feature).

Suggestions are pre-generated at upload time (upload.py step 11d) and stored
in profiles.checkup_suggestions.  This endpoint just reads the cache — no LLM
call happens here, so the response is fast and idempotent.

Auth: Bearer token required.
Tier: gated — HTTP 402 when trial expired and not paid.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from utils.access import require_active_access
from utils.db import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()


class SuggestionItem(BaseModel):
    text: str
    based_on_record_id: str | None


class SuggestionsResponse(BaseModel):
    suggestions: list[SuggestionItem]
    generated_at: str | None   # ISO 8601 with timezone, or null if never generated


@router.get(
    "/",
    response_model=SuggestionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Return cached checkup suggestions from the patient's records [paid]",
)
async def get_suggestions(
    patient_id: str = Depends(require_active_access),
) -> SuggestionsResponse:
    """Read pre-generated checkup suggestions from the profiles cache.

    Suggestions are computed during the upload pipeline and stored on the
    patient's profile row.  Returns an empty list when the patient has no
    uploaded records or suggestions have not been generated yet.

    Contract shape (API_CONTRACT.md):
      { suggestions: [{text, based_on_record_id}], generated_at: string | null }
    """
    supabase = get_supabase()
    result = (
        supabase.table("profiles")
        .select("checkup_suggestions, suggestions_generated_at")
        .eq("id", patient_id)
        .single()
        .execute()
    )

    row: dict = result.data or {}
    raw_suggestions = row.get("checkup_suggestions") or []
    generated_at_raw = row.get("suggestions_generated_at")

    # Normalise timestamp to an ISO 8601 string regardless of what the Supabase
    # client version returns (string vs datetime object).
    generated_at: str | None = None
    if generated_at_raw:
        if isinstance(generated_at_raw, str):
            generated_at = generated_at_raw
        elif isinstance(generated_at_raw, datetime):
            generated_at = generated_at_raw.isoformat()

    items = [
        SuggestionItem(
            text=str(s.get("text", "")),
            based_on_record_id=s.get("based_on_record_id"),
        )
        for s in (raw_suggestions if isinstance(raw_suggestions, list) else [])
        if s.get("text")
    ]

    logger.info(
        "suggestions [%.8s]: returning %d cached item(s).", patient_id, len(items),
    )
    return SuggestionsResponse(suggestions=items, generated_at=generated_at)
