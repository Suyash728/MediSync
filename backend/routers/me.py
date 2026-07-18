"""
GET /me/access — ungated tier-status check for the frontend.

Intentionally cheap: reads two columns from profiles and computes has_access.
The frontend calls this on load to decide which features to surface and whether
to show the upgrade CTA.

Auth is required (Bearer token), but the endpoint is NOT gated behind
require_active_access — the whole point is to report access status, not to
deny the check to unauthenticated / expired users.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from utils.auth import get_current_patient
from utils.db import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()


class AccessStatus(BaseModel):
    is_paid: bool
    trial_ends_at: str | None   # ISO 8601 with timezone, or null
    has_access: bool


@router.get(
    "/access",
    response_model=AccessStatus,
    summary="Return this patient's tier and trial status",
)
async def get_access_status(
    patient_id: str = Depends(get_current_patient),
) -> AccessStatus:
    """Read is_paid and trial_ends_at from profiles; compute has_access.

    Response shape:
      { is_paid: bool, trial_ends_at: string | null, has_access: bool }
    """
    supabase = get_supabase()
    result = (
        supabase.table("profiles")
        .select("is_paid, trial_ends_at")
        .eq("id", patient_id)
        .single()
        .execute()
    )

    row: dict = result.data or {}
    is_paid: bool = bool(row.get("is_paid", False))
    trial_raw = row.get("trial_ends_at")

    trial_ends_at: str | None = None
    has_trial: bool = False

    if trial_raw:
        if isinstance(trial_raw, str):
            trial_dt = datetime.fromisoformat(trial_raw.replace("Z", "+00:00"))
        else:
            trial_dt = trial_raw
        if trial_dt.tzinfo is None:
            trial_dt = trial_dt.replace(tzinfo=timezone.utc)
        trial_ends_at = trial_dt.isoformat()
        has_trial = datetime.now(timezone.utc) < trial_dt

    has_access: bool = is_paid or has_trial

    logger.info(
        "me/access: patient=%.8s is_paid=%s has_trial=%s",
        patient_id, is_paid, has_trial,
    )
    return AccessStatus(
        is_paid=is_paid,
        trial_ends_at=trial_ends_at,
        has_access=has_access,
    )
