"""
FastAPI dependency for tier-gating paid features.

require_active_access
    Use as Depends() on paid endpoints. Returns patient_id on success,
    raises HTTP 402 when the patient has no active plan and their trial
    (if any) has expired.

check_access
    Plain boolean helper — no raise. Use inside endpoints that are
    fundamentally free but contain paid sub-features (e.g. AI summary
    inside the free document-upload flow).
"""

import logging
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status

from utils.auth import get_current_patient
from utils.db import get_supabase

logger = logging.getLogger(__name__)


def check_access(patient_id: str) -> bool:
    """Return True when the patient has an active paid plan or active trial.

    Reads is_paid and trial_ends_at from profiles via the service-role client.
    Returns False on any DB error rather than raising — callers handle the
    degraded path (e.g. skip the summary, not block the upload).
    """
    supabase = get_supabase()
    try:
        result = (
            supabase.table("profiles")
            .select("is_paid, trial_ends_at")
            .eq("id", patient_id)
            .single()
            .execute()
        )
    except Exception as exc:
        logger.warning("check_access: DB error for patient %.8s: %s", patient_id, exc)
        return False

    if not result.data:
        return False

    row: dict = result.data
    if row.get("is_paid"):
        return True

    trial_raw = row.get("trial_ends_at")
    if trial_raw:
        # Supabase returns timestamps as ISO strings; some client versions return datetime.
        if isinstance(trial_raw, str):
            trial_dt = datetime.fromisoformat(trial_raw.replace("Z", "+00:00"))
        else:
            trial_dt = trial_raw
        if trial_dt.tzinfo is None:
            trial_dt = trial_dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < trial_dt

    return False


async def require_active_access(
    patient_id: str = Depends(get_current_patient),
) -> str:
    """FastAPI dependency: verify auth AND active paid/trial access.

    Usage in a route:
        @router.post("/")
        async def my_route(patient_id: str = Depends(require_active_access)):
            ...

    Returns patient_id on success. Raises HTTP 402 when the trial has
    expired and the patient has not upgraded to a paid plan.
    """
    if not check_access(patient_id):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Trial expired — upgrade to continue",
        )
    return patient_id
