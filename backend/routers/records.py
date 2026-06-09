"""
GET /records        — list all records for the authenticated patient
GET /records/{id}   — get a single record (with parsed data)
DELETE /records/{id}— delete a record and its Storage file

RLS on the Supabase records table ensures patients can only read their own rows.
This router enforces that at the API layer too via the JWT dependency (Phase 1).
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_records() -> JSONResponse:
    """List all records for the current patient — implemented in Phase 2."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "Records list endpoint not yet implemented (Phase 2)."},
    )


@router.get("/{record_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_record(record_id: str) -> JSONResponse:
    """Get a single record — implemented in Phase 2."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "Record detail endpoint not yet implemented (Phase 2)."},
    )


@router.delete("/{record_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def delete_record(record_id: str) -> JSONResponse:
    """Delete a record — implemented in Phase 2."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "Record delete endpoint not yet implemented (Phase 2)."},
    )
