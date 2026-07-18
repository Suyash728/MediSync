"""
POST /tts — text-to-speech, cached, paid feature.

Flow:
  1. Auth + tier gate: require_active_access verifies the Bearer token and
     confirms the patient has an active paid plan or trial (HTTP 402 otherwise).
     Mirrors the frontend's PaidGate around the TTS button — the old Next.js
     route.ts route had no server-side gating, so this is enforced here instead.
  2. Validate language against services.tts.SUPPORTED_LANGUAGES.
  3. services.tts.synthesise_cached() — signed-URL cache hit, or chunked
     Sarvam synthesis + WAV concatenation + cache upload on a miss.
  4. Return the signed URL for the browser to play directly.

NOTE: request field is "language_code" (default "en-IN").
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from services import tts as tts_svc
from utils.access import require_active_access
from utils.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────────────────────

class TtsRequest(BaseModel):
    text: str
    language_code: str = "en-IN"


class TtsResponse(BaseModel):
    audio_url: str


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=TtsResponse,
    status_code=status.HTTP_200_OK,
    summary="Synthesise (or fetch cached) audio for patient-facing text [paid]",
)
@limiter.limit("5/minute")
async def synthesise(
    request: Request,
    body: TtsRequest,
    patient_id: str = Depends(require_active_access),
) -> TtsResponse:
    """Text-to-speech over patient-facing text (e.g. an AI summary).

    Gated: requires an active paid plan or trial (HTTP 402 otherwise).
    Rate-limited to 5/minute per IP (slowapi) — Sarvam calls are cost-bearing
    on a cache miss.
    Returns a signed URL to a cached or newly-synthesised WAV file.
    """
    if body.language_code not in tts_svc.SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported language '{body.language_code}'. "
                f"Choose from: {list(tts_svc.SUPPORTED_LANGUAGES.keys())}"
            ),
        )

    logger.info("tts [%.8s]: lang=%s chars=%d", patient_id, body.language_code, len(body.text))

    try:
        audio_url = await tts_svc.synthesise_cached(body.text, body.language_code)
    except RuntimeError as exc:
        # Missing SARVAM_API_KEY or a Sarvam API error — degrade the same way
        # other optional integrations in this codebase surface unavailability.
        logger.warning("tts [%.8s]: unavailable — %s", patient_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Text-to-speech is currently unavailable. Please try again later.",
        ) from exc

    return TtsResponse(audio_url=audio_url)
