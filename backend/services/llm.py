"""
LLM Summarizer Service — adapted from MedInsight for MediSync.

Primary:  Groq llama-3.3-70b-versatile (fast, generous free tier)
Fallback: Google Gemini 1.5 Flash

MediSync changes from MedInsight:
  1. Only the patient-facing summary is needed (no doctor/labworker roles).
  2. Updated model name to llama-3.3-70b-versatile (per CLAUDE.md).
  3. Added `summarise_record_async()` using AsyncGroq for non-blocking I/O.
  4. Prompt focuses on what the patient should know and do next.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Model names
_GROQ_MODEL  = "llama-3.3-70b-versatile"
_GEMINI_MODEL = "gemini-1.5-flash"

# Lazy-initialised clients
_groq_async_client = None
_groq_sync_client  = None


def _get_async_groq():
    global _groq_async_client
    if _groq_async_client is None:
        from utils.config import settings
        if settings.groq_api_key:
            from groq import AsyncGroq
            _groq_async_client = AsyncGroq(api_key=settings.groq_api_key)
    return _groq_async_client


def _get_sync_groq():
    global _groq_sync_client
    if _groq_sync_client is None:
        from utils.config import settings
        if settings.groq_api_key:
            from groq import Groq
            _groq_sync_client = Groq(api_key=settings.groq_api_key)
    return _groq_sync_client


# ── Prompt ────────────────────────────────────────────────────────────────────

_PATIENT_PROMPT = """
You are a compassionate medical translator helping a patient understand their
medical report.  Using the extracted information below, write a short summary
they can actually understand.

Rules:
- Use simple, everyday language.  No jargon.
- If any values are abnormal, explain what that means gently.
- Mention any medications found and what they are generally used for.
- Keep it under 150 words.
- End with ONE sentence telling the patient what to do next.
- Do NOT mention AI, BioBERT, NER, or any technical process.
- Do NOT invent information that isn't in the data below.

Extracted data:
{entities}

Raw report text (first 2000 characters):
{raw_text}
"""

_MAX_TOKENS = 300   # ~150 words with a little headroom


# ── Public API ────────────────────────────────────────────────────────────────

async def summarise_record_async(raw_text: str, entities: dict) -> str:
    """Generate a patient-facing summary.  Async (non-blocking I/O path).

    Tries Groq first; falls back to Gemini; falls back to a deterministic
    template if both API calls fail (e.g. during offline demo).
    """
    prompt = _build_prompt(raw_text, entities)
    result = await _try_groq_async(prompt)
    if result is None:
        result = _try_gemini_sync(prompt)
    if result is None:
        result = _fallback_summary(entities)
    return result


def summarise_record(raw_text: str, entities: dict) -> str:
    """Synchronous version kept for compatibility / testing."""
    prompt = _build_prompt(raw_text, entities)
    result = _try_groq_sync(prompt)
    if result is None:
        result = _try_gemini_sync(prompt)
    if result is None:
        result = _fallback_summary(entities)
    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_prompt(raw_text: str, entities: dict) -> str:
    truncated = raw_text[:2000] if len(raw_text) > 2000 else raw_text
    entities_str = json.dumps(entities, indent=2, default=str)
    return _PATIENT_PROMPT.format(entities=entities_str, raw_text=truncated)


async def _try_groq_async(prompt: str) -> Optional[str]:
    client = _get_async_groq()
    if client is None:
        logger.warning("Groq async client unavailable (key not set?).")
        return None
    try:
        resp = await client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are a medical report summarizer."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.3,
            max_tokens=_MAX_TOKENS,
        )
        logger.info("Summary generated via Groq (async).")
        return resp.choices[0].message.content
    except Exception as exc:
        logger.error("Groq async error: %s", exc)
        return None


def _try_groq_sync(prompt: str) -> Optional[str]:
    client = _get_sync_groq()
    if client is None:
        return None
    try:
        resp = client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are a medical report summarizer."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.3,
            max_tokens=_MAX_TOKENS,
        )
        return resp.choices[0].message.content
    except Exception as exc:
        logger.error("Groq sync error: %s", exc)
        return None


def _try_gemini_sync(prompt: str) -> Optional[str]:
    from utils.config import settings
    if not settings.gemini_api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(_GEMINI_MODEL)
        resp = model.generate_content(prompt)
        logger.info("Summary generated via Gemini (fallback).")
        return resp.text
    except Exception as exc:
        logger.error("Gemini error: %s", exc)
        return None


def _fallback_summary(entities: dict) -> str:
    """Deterministic template summary when both LLM APIs are unavailable."""
    logger.warning("Both LLM APIs failed — using template fallback.")
    parts: list[str] = ["Here is a summary of your medical report.\n"]

    meds = entities.get("medications", [])
    if meds:
        names = ", ".join(m.get("text", m.get("name", "")) for m in meds[:5])
        parts.append(f"Medications mentioned: {names}.")

    labs = entities.get("lab_values", [])
    if labs:
        parts.append(f"Lab tests found: {len(labs)} result(s).")

    flags = entities.get("abnormal_flags", [])
    if flags:
        flagged = ", ".join(f["name"] for f in flags[:3])
        parts.append(f"Some values may be outside normal range: {flagged}. Please discuss with your doctor.")
    else:
        parts.append("Please share these results with your doctor for proper interpretation.")

    return " ".join(parts)
