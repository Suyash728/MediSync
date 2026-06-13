"""
GET /records        — list all health_records for the authenticated patient
GET /records/{id}   — single record with its medications and lab_values
DELETE /records/{id}— delete record, Storage file, and child rows

RLS on the DB tables enforces ownership, but we also check patient_id here
so the error message is explicit rather than a silent empty result.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from utils.auth import get_current_patient
from utils.db import get_supabase
from utils.storage import delete_file, get_signed_url

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", summary="List all records for the current patient")
async def list_records(patient_id: str = Depends(get_current_patient)) -> dict:
    """Return all health_records ordered by document_date descending."""
    supabase = get_supabase()

    result = (
        supabase.table("health_records")
        .select("*")
        .eq("patient_id", patient_id)
        .order("document_date", desc=True)
        .execute()
    )

    return {"records": result.data, "total": len(result.data)}


@router.get("/{record_id}", summary="Get a single record with parsed details")
async def get_record(
    record_id: str,
    patient_id: str = Depends(get_current_patient),
) -> dict:
    """Return a single health_record plus its medications, lab_values, and a
    fresh signed URL for the original file."""
    supabase = get_supabase()

    # Fetch the record
    result = (
        supabase.table("health_records")
        .select("*")
        .eq("id", record_id)
        .eq("patient_id", patient_id)   # belt-and-suspenders ownership check
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Record not found.",
        )

    record = result.data

    # Fetch child rows
    meds = (
        supabase.table("medications")
        .select("*")
        .eq("record_id", record_id)
        .execute()
    ).data

    labs = (
        supabase.table("lab_values")
        .select("*")
        .eq("record_id", record_id)
        .execute()
    ).data

    # Generate a 1-hour signed URL if the record has a file
    file_url: str | None = None
    if record.get("file_path"):
        try:
            file_url = get_signed_url(record["file_path"], expires_in=3600)
        except Exception as exc:
            logger.warning("Could not generate signed URL: %s", exc)

    # Log this view in the access audit trail
    supabase.table("access_log").insert({
        "patient_id": patient_id,
        "record_id":  record_id,
        "action":     "view",
        "actor_type": "patient",
        "actor_id":   patient_id,
    }).execute()

    return {
        "record":      {**record, "file_url": file_url},
        "medications": meds,
        "lab_values":  labs,
    }


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record(
    record_id: str,
    patient_id: str = Depends(get_current_patient),
) -> None:
    """Delete a health_record and its associated Storage file.

    Child rows (medications, lab_values, access_log entries) are handled
    by ON DELETE CASCADE in the schema.
    """
    supabase = get_supabase()

    # Fetch to verify ownership and get the file_path
    result = (
        supabase.table("health_records")
        .select("id, patient_id, file_path")
        .eq("id", record_id)
        .eq("patient_id", patient_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Record not found.",
        )

    record = result.data

    # Delete the Storage file first (non-fatal if it fails — row deletion is more important)
    if record.get("file_path"):
        try:
            delete_file(record["file_path"])
        except Exception as exc:
            logger.warning("Storage delete failed (continuing with DB delete): %s", exc)

    # Delete the DB row — cascades to medications, lab_values
    supabase.table("health_records").delete().eq("id", record_id).execute()
    logger.info("Deleted health_record %s for patient %s", record_id[:8], patient_id[:8])
