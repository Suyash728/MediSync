"""
GET  /conflicts          — list all drug-conflict alerts for the patient
POST /conflicts/scan     — re-run conflict detection across all active medications
POST /conflicts/{id}/ack — patient acknowledges a conflict alert

Phase 4 will implement the DrugBank-backed conflict detection engine.
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_conflicts() -> JSONResponse:
    """List drug conflicts — implemented in Phase 4."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "Conflicts list endpoint not yet implemented (Phase 4)."},
    )


@router.post("/scan", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def scan_conflicts() -> JSONResponse:
    """Trigger conflict scan — implemented in Phase 4."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "Conflict scan endpoint not yet implemented (Phase 4)."},
    )


@router.post("/{conflict_id}/ack", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def acknowledge_conflict(conflict_id: str) -> JSONResponse:
    """Acknowledge a conflict alert — implemented in Phase 4."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "Conflict acknowledge endpoint not yet implemented (Phase 4)."},
    )
