"""
FastAPI dependency for verifying Supabase JWTs.

Strategy: call Supabase's /auth/v1/user endpoint with the Bearer token.
This is the same check the Supabase dashboard does — no JWT secret needed on
our side, and it automatically handles token expiry and rotation.

Returns the patient's UUID (= auth.users.id = profiles.id) on success,
raises HTTP 401 on any failure.
"""

import logging

import httpx
from fastapi import Header, HTTPException, status

from utils.config import settings

logger = logging.getLogger(__name__)


async def get_current_patient(authorization: str = Header(...)) -> str:
    """Verify a Supabase access token and return the patient UUID.

    Usage in a route:
        @router.post("/")
        async def my_route(patient_id: str = Depends(get_current_patient)):
            ...
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be 'Bearer <token>'",
        )

    token = authorization.removeprefix("Bearer ").strip()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    # The anon key is required in the apikey header for all
                    # Supabase API calls, even authenticated ones.
                    "apikey": settings.supabase_anon_key,
                },
            )

        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        user_data: dict = resp.json()
        patient_id: str = user_data["id"]
        return patient_id

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Token verification error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed",
        )
