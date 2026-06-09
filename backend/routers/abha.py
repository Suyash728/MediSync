"""
ABDM Health ID (ABHA) integration — Phase 5 optional.

POST /abha/verify  — verify an ABHA number via the ABDM sandbox
POST /abha/link    — link the patient's profile to their ABHA ID

Uses the ABDM sandbox at sandbox.abdm.gov.in.
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/verify", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def verify_abha() -> JSONResponse:
    """Verify an ABHA number — implemented in Phase 5."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "ABHA verification not yet implemented (Phase 5)."},
    )


@router.post("/link", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def link_abha() -> JSONResponse:
    """Link patient to ABHA ID — implemented in Phase 5."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "ABHA linking not yet implemented (Phase 5)."},
    )
