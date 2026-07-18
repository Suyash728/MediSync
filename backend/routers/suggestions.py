"""
GET /suggestions — return cached checkup suggestions (paid feature).
POST /suggestions/refresh — re-generate and re-cache them on demand.

Suggestions are normally pre-generated at upload time (upload.py step 11d) and
stored in profiles.checkup_suggestions.  GET just reads that cache — no LLM
call happens there, so the response is fast and idempotent.  POST /refresh is
the on-demand escape hatch (e.g. a "regenerate" button) — it calls the same
generation path as the upload pipeline and overwrites the cache.

Auth: Bearer token required.
Tier: gated — HTTP 402 when trial expired and not paid.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from services import rag as rag_svc
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


def _build_response(raw_suggestions: object, generated_at_raw: object) -> SuggestionsResponse:
    """Normalise a profiles row's cache columns into the contract response shape.

    Handles both string and datetime timestamps (Supabase client version
    dependent) and tolerates a null/missing suggestions column.
    """
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
    return SuggestionsResponse(suggestions=items, generated_at=generated_at)


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

    Response shape:
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
    response = _build_response(
        row.get("checkup_suggestions"), row.get("suggestions_generated_at"),
    )
    logger.info(
        "suggestions [%.8s]: returning %d cached item(s).",
        patient_id, len(response.suggestions),
    )
    return response


@router.post(
    "/refresh",
    response_model=SuggestionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Re-generate checkup suggestions from the patient's records [paid]",
)
async def refresh_suggestions(
    patient_id: str = Depends(require_active_access),
) -> SuggestionsResponse:
    """Re-run suggestion generation and persist the result.

    Calls generate_checkup_suggestions(patient_id) — which is self-contained and
    returns [] on any failure mode (retrieval error, LLM error, parse error).
    Writes the result + a fresh UTC timestamp to profiles via the service-role
    client, then returns the new values in the contract shape.

    This is the ONLY endpoint-level trigger for suggestion regeneration besides
    a new document upload.  It is idempotent: calling it multiple times overwrites
    the cache with a fresh result each time.

    Response shape:
      { suggestions: [{text, based_on_record_id}], generated_at: string | null }
    """
    suggestions = await rag_svc.generate_checkup_suggestions(patient_id)
    generated_at = datetime.now(timezone.utc).isoformat()

    supabase = get_supabase()
    supabase.table("profiles").update({
        "checkup_suggestions":      suggestions,
        "suggestions_generated_at": generated_at,
    }).eq("id", patient_id).execute()

    logger.info(
        "suggestions [%.8s]: refreshed, cached %d item(s).",
        patient_id, len(suggestions),
    )
    return _build_response(suggestions, generated_at)
