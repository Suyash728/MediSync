"""
POST /upload — accepts a medical document (PDF or image) from the patient,
stores it in the private Supabase Storage bucket, creates a MedicalRecord row
with status=pending, then enqueues async processing.

Phase 2 will implement the full pipeline. This stub returns a 501 placeholder.
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def upload_document() -> JSONResponse:
    """Upload a medical document — implemented in Phase 2."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "Upload endpoint not yet implemented (Phase 2)."},
    )
