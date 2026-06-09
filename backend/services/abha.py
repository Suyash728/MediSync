"""
ABDM / ABHA integration service — optional Phase 5.

Connects to the ABDM sandbox (sandbox.abdm.gov.in) to:
  1. Verify that a provided ABHA number belongs to the patient.
  2. Link the patient's MediSync profile to their national ABHA ID.

This stub will be replaced with the real implementation in Phase 5 (optional).
"""

# import httpx
# from utils.config import settings


async def verify_abha_number(abha_number: str) -> dict:
    """Verify an ABHA number via the ABDM sandbox API.

    Args:
        abha_number: 14-digit ABHA Health ID number.

    Returns:
        Patient demographic dict from ABDM if valid.

    Raises:
        ValueError: If the ABHA number is invalid or unverified.
    """
    raise NotImplementedError("ABHA verification will be implemented in Phase 5 (optional).")
