"""
DELETE /profile — Permanently delete the authenticated patient's account.

Steps (in order):
  1. List and delete all files in the 'medical-docs' Storage bucket under
     this patient's prefix ({patient_id}/*).
  2. Delete the profile row from the profiles table. The schema uses
     ON DELETE CASCADE on all FK relationships from profiles, so this
     removes health_records, medications, lab_values, drug_conflicts,
     share_grants, and access_log rows automatically.
  3. Delete the Supabase Auth user via the service-role admin REST API.

Authorization: the patient_id extracted from the JWT MUST match the
account being deleted. The get_current_patient dependency enforces this
— there is no "delete another user's account" path.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from utils.auth import get_current_patient
from utils.db import get_supabase
from utils.config import settings
from utils.storage import BUCKET

logger = logging.getLogger(__name__)
router = APIRouter()


@router.delete("/", summary="Permanently delete this patient's account and all data")
async def delete_profile(patient_id: str = Depends(get_current_patient)) -> dict:
    """Delete Storage files, profile row (cascades), then the Auth user."""
    supabase = get_supabase()

    # ── 1. Delete all Storage files for this patient ──────────────────────────
    # Files are stored as {patient_id}/{record_id}.{ext} so listing the prefix
    # returns all files belonging exclusively to this patient.
    try:
        storage_objects = supabase.storage.from_(BUCKET).list(path=patient_id)
        if storage_objects:
            paths = [f"{patient_id}/{obj['name']}" for obj in storage_objects]
            supabase.storage.from_(BUCKET).remove(paths)
            logger.info(
                "Deleted %d Storage file(s) for patient %s",
                len(paths), patient_id,
            )
    except Exception as exc:
        # Log and continue — a Storage failure should not block account deletion
        logger.warning("Storage cleanup partial failure for %s: %s", patient_id, exc)

    # ── 2. Delete the profile row (cascades to all related rows) ─────────────
    result = supabase.table("profiles").delete().eq("id", patient_id).execute()
    logger.info("Deleted profile row for patient %s (rows affected: %s)",
                patient_id, len(result.data) if result.data else "unknown")

    # ── 3. Delete the Supabase Auth user ─────────────────────────────────────
    # This must use the service-role key — the anon key does not have admin rights.
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(
                f"{settings.supabase_url}/auth/v1/admin/users/{patient_id}",
                headers={
                    "Authorization": f"Bearer {settings.supabase_service_key}",
                    "apikey": settings.supabase_service_key,
                },
            )

        if resp.status_code not in (200, 204):
            logger.error(
                "Auth user deletion failed for %s: HTTP %s — %s",
                patient_id, resp.status_code, resp.text,
            )
            # The profile data is already gone; raise so the frontend
            # knows the Auth entry persists and can contact support.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Account data deleted but Auth user removal failed. "
                    "Please contact support to complete the deletion."
                ),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Auth user deletion error for %s: %s", patient_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth user removal failed. Please contact support.",
        )

    logger.info("Account fully deleted for patient %s", patient_id)
    return {"deleted": True}
