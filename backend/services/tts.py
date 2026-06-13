"""
TTS Service — adapted from MedInsight.

MedInsight uses Sarvam AI Bulbul:v3 (11 Indian languages).
CLAUDE.md originally specified edge-tts; we keep Sarvam as the primary since
it provides broader Indian language support and is what MedInsight uses.

TTS is an optional feature (Phase 5).  The upload pipeline does NOT call this.
It is only invoked when the patient explicitly requests an audio summary.
"""

import base64
import logging
import re
from typing import Optional

import httpx    # async-native; replaces requests from MedInsight

from utils.config import settings

logger = logging.getLogger(__name__)

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
TTS_MODEL      = "bulbul:v3"
MAX_TTS_CHARS  = 1500

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en-IN": "English (Indian)",
    "hi-IN": "हिंदी (Hindi)",
    "bn-IN": "বাংলা (Bengali)",
    "gu-IN": "ગુજરાતી (Gujarati)",
    "kn-IN": "ಕನ್ನಡ (Kannada)",
    "ml-IN": "മലയാളം (Malayalam)",
    "mr-IN": "मराठी (Marathi)",
    "od-IN": "ଓଡ଼ିଆ (Odia)",
    "pa-IN": "ਪੰਜਾਬੀ (Punjabi)",
    "ta-IN": "தமிழ் (Tamil)",
    "te-IN": "తెలుగు (Telugu)",
}


async def synthesise_async(text: str, language_code: str = "en-IN") -> bytes:
    """Convert text to MP3 bytes using Sarvam AI Bulbul:v3.

    Args:
        text:          Plain text to synthesise (markdown stripped, truncated).
        language_code: BCP-47 code from SUPPORTED_LANGUAGES.

    Returns:
        MP3 audio bytes for streaming to the browser.

    Raises:
        RuntimeError: SARVAM_API_KEY missing or API error.
        ValueError:   Unsupported language_code.
    """
    if not settings.sarvam_api_key:
        raise RuntimeError(
            "SARVAM_API_KEY is not configured.  Set it in backend/.env to enable TTS."
        )

    if language_code not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported language '{language_code}'. "
            f"Choose from: {list(SUPPORTED_LANGUAGES.keys())}"
        )

    clean = _clean_for_tts(text)
    if len(clean) > MAX_TTS_CHARS:
        clean = clean[:MAX_TTS_CHARS].rsplit(" ", 1)[0]

    logger.info("TTS request: model=%s lang=%s chars=%d", TTS_MODEL, language_code, len(clean))

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            SARVAM_TTS_URL,
            json={
                "text": clean,
                "target_language_code": language_code,
                "model": TTS_MODEL,
            },
            headers={
                "api-subscription-key": settings.sarvam_api_key,
                "Content-Type": "application/json",
            },
        )

    if not resp.is_success:
        raise RuntimeError(f"Sarvam TTS API error {resp.status_code}: {resp.text}")

    audio_b64: str = resp.json()["audios"][0]
    audio_bytes = base64.b64decode(audio_b64)
    logger.info("TTS complete: %d bytes", len(audio_bytes))
    return audio_bytes


# ── Utilities ─────────────────────────────────────────────────────────────────

def _clean_for_tts(text: str) -> str:
    """Strip markdown and normalise whitespace for clean speech synthesis."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*",     r"\1", text)
    text = re.sub(r"#{1,6}\s*",     "",    text)
    text = re.sub(r"\[(.+?)\]",     r"\1", text)
    text = re.sub(r"[•·–—]",        ",",   text)
    text = re.sub(r"\s+",           " ",   text)
    return text.strip()
