"""
GET  /conflicts/               — list all drug-conflict alerts for the patient
POST /conflicts/recheck        — re-run detection across all active medications
POST /conflicts/{id}/acknowledge — patient marks a conflict as reviewed
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from services import conflict as conflict_svc
from utils.auth import get_current_patient
from utils.db import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", summary="List all drug-conflict alerts for the current patient")
async def list_conflicts(
    patient_id: str = Depends(get_current_patient),
) -> dict:
    """Return all drug-conflict rows ordered by severity then detected_at.

    Active (unacknowledged) alerts come first within each severity tier.
    Severity order: major → moderate → minor.
    """
    supabase = get_supabase()

    result = (
        supabase.table("drug_conflicts")
        .select("*")
        .eq("patient_id", patient_id)
        .order("detected_at", desc=True)
        .execute()
    )

    rows = result.data or []

    # Sort: unacknowledged before acknowledged, then by severity
    _SEV_ORDER = {"major": 0, "moderate": 1, "minor": 2}
    rows.sort(key=lambda r: (
        1 if r.get("is_acknowledged") else 0,
        _SEV_ORDER.get(r.get("severity", "minor"), 9),
    ))

    unacknowledged = sum(1 for r in rows if not r.get("is_acknowledged"))

    return {
        "conflicts":            rows,
        "total":                len(rows),
        "unacknowledged_count": unacknowledged,
    }


@router.post("/recheck", summary="Re-run drug-conflict detection for the patient")
async def recheck_conflicts(
    patient_id: str = Depends(get_current_patient),
) -> dict:
    """Re-scan all active medications and insert any newly-detected interactions.

    Existing acknowledged conflicts are not disturbed — only new pairs are
    added.  Safe to call at any time; idempotent for existing conflicts.
    """
    logger.info("Manual conflict recheck requested for patient %s.", patient_id[:8])
    try:
        new_conflicts = await conflict_svc.run_conflict_check(patient_id)
    except Exception as exc:
        logger.error("Conflict recheck failed for patient %s: %s", patient_id[:8], exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Conflict detection failed. Please try again.",
        )

    return {
        "new_conflicts": new_conflicts,
        "count":         len(new_conflicts),
        "message": (
            f"Found {len(new_conflicts)} new interaction(s)."
            if new_conflicts
            else "No new interactions detected."
        ),
    }


@router.post(
    "/{conflict_id}/acknowledge",
    summary="Acknowledge a drug-conflict alert",
)
async def acknowledge_conflict(
    conflict_id:  str,
    patient_id:   str = Depends(get_current_patient),
) -> dict:
    """Mark a conflict alert as acknowledged (reviewed by the patient).

    Does NOT delete the row — the audit trail must be preserved.
    """
    supabase = get_supabase()

    # Verify ownership before updating
    existing = (
        supabase.table("drug_conflicts")
        .select("id, patient_id, is_acknowledged")
        .eq("id", conflict_id)
        .eq("patient_id", patient_id)
        .single()
        .execute()
    )

    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conflict alert not found.",
        )

    supabase.table("drug_conflicts").update(
        {"is_acknowledged": True}
    ).eq("id", conflict_id).execute()

    logger.info(
        "Conflict %s acknowledged by patient %s.",
        conflict_id[:8], patient_id[:8],
    )

    return {"success": True, "id": conflict_id}
