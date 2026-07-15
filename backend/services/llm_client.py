"""
Thin LLM helper for the /api/chat endpoint.

Exposes one function:

  complete(prompt, system, temperature) -> (answer_text, provider)

PRIMARY:  Groq openai/gpt-oss-120b via AsyncGroq.
FALLBACK: Gemini gemini-2.5-flash via client.aio.models.generate_content
          triggered on RateLimitError, APIConnectionError, or APIStatusError.

This module is intentionally standalone — it does not import from or alter
services/llm.py, which owns the extraction and summary pipelines.
"""

import logging
from typing import Optional

import groq as _groq_mod

logger = logging.getLogger(__name__)

_GROQ_MODEL   = "openai/gpt-oss-120b"
_GEMINI_MODEL = "gemini-2.5-flash"
_GROQ_TIMEOUT = 20.0   # seconds; chat completions for a focused RAG answer are short

# Lazy-initialised — created on first call, reused for the process lifetime.
_groq_client:   Optional[object] = None   # groq.AsyncGroq once initialised
_gemini_client: Optional[object] = None   # google.genai.Client once initialised

# Groq errors that trigger the Gemini fallback (per CLAUDE.md spec).
_GROQ_FALLBACK_ERRORS = (
    _groq_mod.RateLimitError,
    _groq_mod.APIConnectionError,
    _groq_mod.APIStatusError,
)


def _get_groq() -> Optional[object]:
    global _groq_client
    if _groq_client is None:
        from utils.config import settings
        if settings.groq_api_key:
            from groq import AsyncGroq
            _groq_client = AsyncGroq(api_key=settings.groq_api_key)
            logger.info("llm_client: Groq AsyncGroq initialised (model=%s).", _GROQ_MODEL)
        else:
            logger.warning("llm_client: GROQ_API_KEY not set — Groq unavailable.")
    return _groq_client


def _get_gemini() -> Optional[object]:
    global _gemini_client
    if _gemini_client is None:
        from utils.config import settings
        if not settings.gemini_api_key:
            logger.warning("llm_client: GEMINI_API_KEY not set — Gemini fallback unavailable.")
            return None
        try:
            from google import genai  # type: ignore[import-untyped]
            _gemini_client = genai.Client(api_key=settings.gemini_api_key)
            logger.info("llm_client: Gemini client initialised (model=%s).", _GEMINI_MODEL)
        except ImportError:
            logger.warning("llm_client: google-genai not installed — Gemini fallback unavailable.")
        except Exception as exc:
            logger.warning("llm_client: Gemini client init failed: %s", exc)
    return _gemini_client


async def _call_groq(prompt: str, system: str, temperature: float) -> str:
    """Attempt a Groq completion; raises on any error so the caller can fall back."""
    client = _get_groq()
    if client is None:
        raise RuntimeError("Groq client not available.")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = await client.chat.completions.create(
        model=_GROQ_MODEL,
        messages=messages,
        temperature=temperature,
        timeout=_GROQ_TIMEOUT,
    )
    return response.choices[0].message.content or ""


async def _call_gemini(prompt: str, system: str, temperature: float) -> str:
    """Gemini fallback via the async client.aio path (google-genai unified SDK)."""
    client = _get_gemini()
    if client is None:
        raise RuntimeError("Gemini client not available.")

    from google.genai import types  # type: ignore[import-untyped]

    config = types.GenerateContentConfig(
        temperature=temperature,
        # system_instruction is ignored when empty; pass only when set.
        **({"system_instruction": system} if system else {}),
    )

    response = await client.aio.models.generate_content(
        model=_GEMINI_MODEL,
        contents=prompt,
        config=config,
    )
    return response.text or ""


async def complete(
    prompt: str,
    system: str = "",
    temperature: float = 0.2,
) -> tuple[str, str]:
    """Generate a completion, returning (answer_text, provider).

    Tries Groq first (openai/gpt-oss-120b, 20 s timeout).
    Falls back to Gemini gemini-2.5-flash on RateLimitError,
    APIConnectionError, or APIStatusError — the three errors that indicate
    Groq is temporarily unavailable rather than a bug in our request.

    Args:
        prompt:      User-facing message text.
        system:      Optional system instruction (clinical persona, etc.).
        temperature: Sampling temperature; 0.2 is conservative for factual answers.

    Returns:
        (answer_text, provider) — provider is "groq" or "gemini".
    """
    # ── Primary: Groq ─────────────────────────────────────────────────────────
    try:
        answer = await _call_groq(prompt, system, temperature)
        return answer, "groq"

    except _GROQ_FALLBACK_ERRORS as exc:
        # These three error types signal a transient Groq-side problem.
        # Fall through to Gemini rather than surfacing the error to the user.
        logger.warning(
            "llm_client: Groq %s — falling back to Gemini. (%s)",
            type(exc).__name__, exc,
        )

    # ── Fallback: Gemini ──────────────────────────────────────────────────────
    answer = await _call_gemini(prompt, system, temperature)
    return answer, "gemini"
