"""
TTS Service — adapted from MedInsight.

MedInsight uses Sarvam AI Bulbul:v3 (11 Indian languages).
CLAUDE.md originally specified edge-tts; we keep Sarvam as the primary since
it provides broader Indian language support and is what MedInsight uses.

TTS is an optional feature (Phase 5).  The upload pipeline does NOT call this.
It is only invoked when the patient explicitly requests an audio summary.

Chunking + WAV-concatenation (synthesise_async) and the signed-URL cache
(cache_key / synthesise_cached) mirror frontend/app/api/tts/route.ts, which
already solved Sarvam's per-request character limit this way.
"""

import base64
import hashlib
import logging
import re

import httpx    # async-native; replaces requests from MedInsight
from storage3.exceptions import StorageApiError
from tenacity import retry, retry_if_exception, retry_if_exception_type, stop_after_attempt, wait_exponential

from utils.config import settings
from utils.db import get_supabase

logger = logging.getLogger(__name__)

SARVAM_TTS_URL   = "https://api.sarvam.ai/text-to-speech"
TTS_MODEL        = "bulbul:v3"
TTS_CHUNK_CHARS  = 450   # Sarvam bulbul:v3's per-request character limit

# WAV layout (see _concat_wav): 44-byte header, RIFF size at bytes 4-7,
# data sub-chunk size at bytes 40-43.
WAV_HEADER_SIZE = 44

TTS_CACHE_BUCKET = "tts-cache"

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


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=(
        retry_if_exception_type((httpx.TimeoutException,))
        | retry_if_exception(
            lambda e: isinstance(e, httpx.HTTPStatusError)
            and e.response.status_code in (429, 500, 502, 503, 504)
        )
    ),
    reraise=True,
)
async def _sarvam_post_async(text: str, language_code: str, api_key: str) -> dict:
    """Single Sarvam TTS POST; retried by tenacity on timeouts and 5xx/429.

    Uses raise_for_status() so httpx.HTTPStatusError propagates to the retry
    condition.  4xx errors other than 429 are NOT retried — a 401 bad-key or
    400 bad-payload will never succeed on retry.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            SARVAM_TTS_URL,
            json={
                "text": text,
                "target_language_code": language_code,
                "model": TTS_MODEL,
            },
            headers={
                "api-subscription-key": api_key,
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()   # → httpx.HTTPStatusError for 4xx/5xx
        return resp.json()


async def synthesise_async(text: str, language_code: str = "en-IN") -> bytes:
    """Convert text to WAV bytes using Sarvam AI Bulbul:v3.

    Text is split into <=TTS_CHUNK_CHARS chunks on sentence boundaries (Sarvam's
    per-request character limit), synthesised chunk-by-chunk, and the resulting
    WAV buffers are concatenated into a single file.

    Args:
        text:          Plain text to synthesise (markdown stripped internally).
        language_code: BCP-47 code from SUPPORTED_LANGUAGES.

    Returns:
        WAV audio bytes for streaming to the browser / uploading to cache.

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
    chunks = _split_into_chunks(clean, TTS_CHUNK_CHARS)

    logger.info(
        "TTS request: model=%s lang=%s chars=%d chunks=%d",
        TTS_MODEL, language_code, len(clean), len(chunks),
    )

    wav_chunks: list[bytes] = []
    for chunk in chunks:
        try:
            data = await _sarvam_post_async(chunk, language_code, settings.sarvam_api_key)
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Sarvam TTS API error {exc.response.status_code}: {exc.response.text}"
            ) from exc

        audio_b64: str = data["audios"][0]
        wav_chunks.append(base64.b64decode(audio_b64))

    audio_bytes = _concat_wav(wav_chunks)
    logger.info("TTS complete: %d bytes from %d chunk(s)", len(audio_bytes), len(wav_chunks))
    return audio_bytes


async def synthesise_cached(text: str, language_code: str) -> str:
    """Return a signed URL for this (text, language) pair, synthesising on a miss.

    Checks the "tts-cache" bucket for cache_key(text, language_code) first — a
    missing object surfaces as storage3's StorageApiError, which counts as a
    cache miss.  On a miss, runs the chunked synthesis + concatenation above,
    uploads the WAV to cache, then returns a fresh signed URL.

    Args:
        text:          Plain text to synthesise (same text used for the cache key).
        language_code: BCP-47 code from SUPPORTED_LANGUAGES.

    Returns:
        A signed URL (1-hour expiry) for the cached or newly-synthesised WAV.
    """
    supabase = get_supabase()
    key = cache_key(text, language_code)

    try:
        result = supabase.storage.from_(TTS_CACHE_BUCKET).create_signed_url(
            path=key, expires_in=3600,
        )
        logger.info("TTS cache hit: %s", key)
        return result["signedURL"]
    except StorageApiError:
        logger.info("TTS cache miss: %s", key)

    audio_bytes = await synthesise_async(text, language_code)

    supabase.storage.from_(TTS_CACHE_BUCKET).upload(
        path=key,
        file=audio_bytes,
        file_options={"content-type": "audio/wav"},
    )
    logger.info("TTS cached: %d bytes at %s", len(audio_bytes), key)

    result = supabase.storage.from_(TTS_CACHE_BUCKET).create_signed_url(
        path=key, expires_in=3600,
    )
    return result["signedURL"]


# ── Utilities ─────────────────────────────────────────────────────────────────

_SENTENCE_SPLIT_RE = re.compile(r"[^.!?।]+[.!?।]+|[^.!?।]+$")


def _split_into_chunks(text: str, max_len: int = TTS_CHUNK_CHARS) -> list[str]:
    """Split text into <=max_len chunks on sentence boundaries (.!?।).

    Ported from frontend/app/api/tts/route.ts's splitIntoChunks. A single
    sentence longer than max_len is kept as its own chunk — Sarvam handles
    long sentences gracefully.
    """
    sentences = _SENTENCE_SPLIT_RE.findall(text) or [text]

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        trimmed = sentence.strip()
        if not trimmed:
            continue

        if current and len(current) + 1 + len(trimmed) > max_len:
            chunks.append(current.strip())
            current = trimmed
        else:
            current = f"{current} {trimmed}" if current else trimmed

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text.strip()]


def _concat_wav(chunks: list[bytes]) -> bytes:
    """Concatenate WAV byte chunks, patching the RIFF/data size fields.

    Ported from frontend/app/api/tts/route.ts's concatWav. Keeps the full
    44-byte header from the first chunk, strips headers from chunks 2..N,
    then rewrites the RIFF chunk size (bytes 4-7) and data sub-chunk size
    (bytes 40-43) to match the combined length.
    """
    if len(chunks) == 1:
        return chunks[0]

    parts = [chunks[0]] + [chunk[WAV_HEADER_SIZE:] for chunk in chunks[1:]]
    combined = bytearray(b"".join(parts))

    data_size = len(combined) - WAV_HEADER_SIZE
    file_size = len(combined) - 8

    combined[4:8] = file_size.to_bytes(4, "little")
    combined[40:44] = data_size.to_bytes(4, "little")

    return bytes(combined)


def cache_key(text: str, language_code: str) -> str:
    """Deterministic cache path for a (spoken text, language) pair.

    Hashes the *cleaned* text — the same normalisation synthesise_async uses —
    so the cache key matches on what will actually be spoken, not raw markdown.
    """
    normalized = _clean_for_tts(text)
    digest = hashlib.sha256(f"{normalized}|{language_code}".encode("utf-8")).hexdigest()
    return f"tts/{digest}.wav"


def _clean_for_tts(text: str) -> str:
    """Strip markdown and normalise whitespace for clean speech synthesis."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*",     r"\1", text)
    text = re.sub(r"#{1,6}\s*",     "",    text)
    text = re.sub(r"\[(.+?)\]",     r"\1", text)
    text = re.sub(r"[•·–—]",        ",",   text)
    text = re.sub(r"\s+",           " ",   text)
    return text.strip()
