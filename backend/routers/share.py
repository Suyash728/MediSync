"""
POST /share              — create a new time-limited share grant (returns token)
GET  /share              — list all share grants for the patient
DELETE /share/{id}       — revoke a share grant (sets is_active=False)
GET  /share/view/{token} — public endpoint: validate token, return scoped records

Security invariants (enforced here, not just in RLS):
  1. Token is a 32-byte cryptographically random hex string (secrets.token_hex(32)).
  2. Expired or revoked grants return 403, never 404 (to avoid token enumeration).
  3. Every call to view/{token} writes a row to access_log.
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def create_share_grant() -> JSONResponse:
    """Create a share grant — implemented in Phase 5."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "Share grant creation not yet implemented (Phase 5)."},
    )


@router.get("/", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_share_grants() -> JSONResponse:
    """List share grants — implemented in Phase 5."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "Share grant list not yet implemented (Phase 5)."},
    )


@router.delete("/{grant_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def revoke_share_grant(grant_id: str) -> JSONResponse:
    """Revoke a share grant — implemented in Phase 5."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "Share grant revocation not yet implemented (Phase 5)."},
    )


@router.get("/view/{token}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def view_shared_records(token: str) -> JSONResponse:
    """Clinician-facing: return scoped records for a share token — implemented in Phase 5."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "Share view endpoint not yet implemented (Phase 5)."},
    )
