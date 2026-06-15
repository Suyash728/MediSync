"""
LLM Service — adapted from MedInsight for MediSync.

Two distinct operations, both using Groq (Gemini fallback):

  1. extract_structured_async(raw_text)
       PRIMARY extraction path — replaces the BioBERT NER as the main source
       of structured data.  Sends raw OCR text to Groq with a strict JSON-mode
       prompt and returns a typed dict.  BioBERT NER output is merged in
       afterwards as a secondary signal only.

  2. summarise_record_async(raw_text, entities)
       Generates a concise, factual clinical summary for the patient record.
       Prompt is deliberately clinical and precise — not casual or reassuring.

Primary:  Groq llama-3.3-70b-versatile (fast, large context, JSON mode)
Fallback: Google Gemini (via google-genai SDK — new unified SDK, NOT google-generativeai)
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Groq model — used for both structured extraction (JSON mode) and summary generation.
# Gemini model is read from settings.gemini_model (configurable via GEMINI_MODEL env var).
_GROQ_MODEL = "llama-3.3-70b-versatile"

# Lazy-initialised clients
_groq_async_client = None
_groq_sync_client  = None
_gemini_client     = None


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


def _get_gemini_client():
    """Lazy-init the google-genai Client (new unified SDK).  Returns None if key not set."""
    global _gemini_client
    if _gemini_client is None:
        from utils.config import settings
        if not settings.gemini_api_key:
            return None
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=settings.gemini_api_key)
            logger.info("Gemini client initialised (model=%s).", settings.gemini_model)
        except ImportError:
            logger.warning("google-genai not installed — Gemini fallback unavailable.")
        except Exception as exc:
            logger.warning("Gemini client init failed: %s", exc)
    return _gemini_client


# ── Structured extraction ─────────────────────────────────────────────────────
#
# The extraction prompt is constructed via concatenation (not .format()) to avoid
# conflicts between Python's str.format() and the JSON literal braces in the schema.

_EXTRACTION_SYSTEM = (
    "You are a precise medical data extractor. "
    "Return ONLY valid JSON. No explanation, no markdown, no text outside the JSON object."
)

_EXTRACTION_SCHEMA = """{
  "record_type": "prescription | lab_report | discharge_summary | imaging | vaccination | other",
  "document_date": "YYYY-MM-DD or null",
  "source_facility": "string or null",
  "medications": [
    {"drug_name": "string", "dosage": "string or null", "frequency": "string or null"}
  ],
  "lab_values": [
    {
      "test_name": "string",
      "value": "string",
      "unit": "string or null",
      "reference_range": "string or null",
      "is_abnormal": true
    }
  ],
  "diagnoses": ["string"],
  "summary": "string"
}"""

_EXTRACTION_RULES = """
Strict rules:
- Extract ONLY information explicitly present in the text. Never infer or hallucinate.
- reference_range: MANDATORY when the document provides a "Reference Range",
  "Reference Interval", or "Normal Range" column or field for that test. Copy
  it EXACTLY as printed — do not reformat, round, or abbreviate. Set to null
  only when the document genuinely provides no range for that specific test.
- is_abnormal: determine by comparing the numeric value against the reference_range.
  Parse range formats correctly:
    "13.0 - 17.0"  → abnormal if value < 13.0 or > 17.0
    "> 4.5"        → abnormal if value <= 4.5
    "< 100"        → abnormal if value >= 100
    "150,000 - 400,000" → ignore commas, treat as 150000 - 400000
  Also set true when the document explicitly flags the value H, L, HIGH, LOW,
  ABNORMAL, or CRITICAL — even if you cannot parse the range.
  Set is_abnormal=null (NOT false) when no reference_range exists for that test.
- document_date: the date printed on the document, not today. Format YYYY-MM-DD.
- Include ALL medications — prescription drugs, OTC drugs, vitamins, and supplements.
- Null for missing string fields. Empty array [] for missing list fields.
- The summary must be factual and clinical. State diagnoses, medications, and abnormal
  lab values explicitly by name and value. If none are found, state that plainly.

Document text:
"""

# Empty structure returned when both LLM APIs fail or produce unparseable output.
_EMPTY_EXTRACTION: dict = {
    "record_type":    None,
    "document_date":  None,
    "source_facility": None,
    "medications":    [],
    "lab_values":     [],
    "diagnoses":      [],
    "summary":        None,
}


async def extract_structured_async(raw_text: str) -> dict:
    """Extract structured medical data from raw OCR text (PRIMARY extraction path).

    Sends the raw text to Groq with a strict JSON-mode prompt.  Falls back to
    Gemini if Groq fails.  Returns _EMPTY_EXTRACTION if both fail — the caller
    (upload router) will then mark the record as needs_review.

    Returns a dict with keys: record_type, document_date, source_facility,
    medications, lab_values, diagnoses, summary.
    """
    # Schema MUST come before the rules so the model knows the exact field names
    # expected.  Without it, Groq guesses names like "reference_interval" instead of
    # "reference_range" and those keys are silently dropped by the persistence code.
    prompt = (
        "Return a JSON object matching this schema exactly:\n"
        + _EXTRACTION_SCHEMA
        + "\n\n"
        + _EXTRACTION_RULES
        + raw_text[:4000]
    )

    raw = await _try_groq_extraction_async(prompt)
    if raw is None:
        logger.warning("Groq extraction failed — trying Gemini fallback.")
        raw = _try_gemini_extraction_sync(prompt)

    if raw is None:
        logger.warning("All extraction LLM calls failed — returning empty structure.")
        return dict(_EMPTY_EXTRACTION)

    result = _parse_extraction_response(raw)
    logger.debug(
        "[extraction] Parsed lab_values (%d rows): %s",
        len(result.get("lab_values", [])),
        result.get("lab_values", []),
    )
    return result


def _parse_extraction_response(raw: str) -> dict:
    """Parse the LLM's JSON response.  Handles markdown code-fence wrappers."""
    text = raw.strip()

    # Strip ```json ... ``` or ``` ... ``` wrappers some models still add
    if text.startswith("```"):
        lines = text.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Last attempt: extract the outermost {...} from the response
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
            except json.JSONDecodeError:
                logger.warning("LLM extraction: could not parse JSON from response.")
                return dict(_EMPTY_EXTRACTION)
        else:
            return dict(_EMPTY_EXTRACTION)

    if not isinstance(data, dict):
        return dict(_EMPTY_EXTRACTION)

    # Normalise: ensure expected types even if the model used wrong types
    result = dict(_EMPTY_EXTRACTION)
    result["record_type"]     = data.get("record_type") or None
    result["document_date"]   = data.get("document_date") or None
    result["source_facility"] = data.get("source_facility") or None
    result["medications"]     = data.get("medications")  if isinstance(data.get("medications"),  list) else []
    result["lab_values"]      = data.get("lab_values")   if isinstance(data.get("lab_values"),   list) else []
    result["diagnoses"]       = data.get("diagnoses")    if isinstance(data.get("diagnoses"),     list) else []
    result["summary"]         = data.get("summary") or None

    return result


async def _try_groq_extraction_async(prompt: str) -> Optional[str]:
    """Call Groq in JSON mode for structured data extraction."""
    client = _get_async_groq()
    if client is None:
        logger.warning("Groq client unavailable (key not set?).")
        return None
    try:
        resp = await client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[
                {"role": "system", "content": _EXTRACTION_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1,               # near-deterministic for data extraction
            max_tokens=2000,
            response_format={"type": "json_object"},   # Groq JSON mode — no markdown wrappers
        )
        raw_content = resp.choices[0].message.content
        logger.debug("[extraction] Groq raw JSON output:\n%s", raw_content)
        logger.info("Structured extraction via Groq: success.")
        return raw_content
    except Exception as exc:
        logger.error("Groq extraction error: %s", exc)
        return None


def _try_gemini_extraction_sync(prompt: str) -> Optional[str]:
    """Call Gemini for structured extraction (fallback, synchronous).

    Uses google-genai (new unified SDK).  JSON mode is requested via
    GenerateContentConfig(response_mime_type="application/json") so the
    response is always valid JSON without markdown wrappers.
    """
    from utils.config import settings
    client = _get_gemini_client()
    if client is None:
        return None
    try:
        from google.genai import types
        full_prompt = (
            _EXTRACTION_SYSTEM
            + "\n\nReturn this JSON schema:\n"
            + _EXTRACTION_SCHEMA
            + "\n\n"
            + prompt
        )
        resp = client.models.generate_content(
            model=settings.gemini_model,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        logger.info("Structured extraction via Gemini fallback: success.")
        return resp.text
    except Exception as exc:
        logger.error("Gemini extraction error: %s", exc)
        return None


# ── Clinical summary ─────────────────────────────────────────────────────────
#
# Prompt is deliberately clinical and factual.  No casual language, no "gentle"
# framing.  The patient wants clear information, not reassurance theatre.

_SUMMARY_SYSTEM = (
    "You are a clinical documentation assistant producing concise, factual medical summaries."
)

# Build the summary prompt via concatenation for the same reason as above.
_SUMMARY_INSTRUCTIONS = """Write a concise clinical summary of this medical document.

Requirements:
- State the document type and date if present.
- List confirmed diagnoses by name (if any). If none, state "No diagnoses identified."
- List all medications with dosage and frequency (if any). If none, state "No medications identified."
- State abnormal lab values with their result and reference range (if any).
  If none, state "No abnormal lab values identified."
- Note any follow-up instructions or clinical recommendations mentioned in the document.
- Do not speculate or add information not present in the source text.
- Maximum 200 words. Clinical tone throughout.

Extracted structured data:
"""

_MAX_SUMMARY_TOKENS = 400   # ~200 words with headroom


async def summarise_record_async(raw_text: str, entities: dict) -> str:
    """Generate a factual clinical summary.  Async (non-blocking I/O path).

    Tries Groq first; falls back to Gemini; falls back to deterministic template
    if both APIs fail (e.g. during offline demo or API outage).

    Args:
        raw_text:  Raw OCR text (truncated to 3000 chars in the prompt).
        entities:  The structured extraction dict from extract_structured_async().
    """
    prompt = _build_summary_prompt(raw_text, entities)
    result = await _try_groq_summary_async(prompt)
    if result is None:
        result = _try_gemini_summary_sync(prompt)
    if result is None:
        result = _fallback_summary(entities)
    return result


def _build_summary_prompt(raw_text: str, entities: dict) -> str:
    entities_str = json.dumps(entities, indent=2, default=str)
    truncated    = raw_text[:3000] if len(raw_text) > 3000 else raw_text
    return (
        _SUMMARY_INSTRUCTIONS
        + entities_str
        + "\n\nRaw text (first 3000 chars):\n"
        + truncated
    )


async def _try_groq_summary_async(prompt: str) -> Optional[str]:
    client = _get_async_groq()
    if client is None:
        return None
    try:
        resp = await client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.2,
            max_tokens=_MAX_SUMMARY_TOKENS,
        )
        logger.info("Summary generated via Groq.")
        return resp.choices[0].message.content
    except Exception as exc:
        logger.error("Groq summary error: %s", exc)
        return None


def _try_gemini_summary_sync(prompt: str) -> Optional[str]:
    """Generate a clinical summary via Gemini (fallback, synchronous).

    Uses google-genai (new unified SDK).
    """
    from utils.config import settings
    client = _get_gemini_client()
    if client is None:
        return None
    try:
        from google.genai import types
        resp = client.models.generate_content(
            model=settings.gemini_model,
            contents=_SUMMARY_SYSTEM + "\n\n" + prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=_MAX_SUMMARY_TOKENS,
            ),
        )
        logger.info("Summary generated via Gemini (fallback).")
        return resp.text
    except Exception as exc:
        logger.error("Gemini summary error: %s", exc)
        return None


def _fallback_summary(entities: dict) -> str:
    """Deterministic template used when both LLM APIs are unavailable."""
    logger.warning("Both LLM APIs failed — using template fallback summary.")
    parts: list[str] = []

    diag = entities.get("diagnoses", [])
    if diag:
        parts.append(f"Diagnoses: {', '.join(str(d) for d in diag[:5])}.")
    else:
        parts.append("No diagnoses identified.")

    meds = entities.get("medications", [])
    if meds:
        names = ", ".join(
            m.get("drug_name") or m.get("name") or str(m) for m in meds[:5]
        )
        parts.append(f"Medications: {names}.")
    else:
        parts.append("No medications identified.")

    labs = entities.get("lab_values", [])
    abnormal = [lv for lv in labs if lv.get("is_abnormal")]
    if abnormal:
        flagged = ", ".join(
            f"{lv.get('test_name', '?')} {lv.get('value', '?')}"
            for lv in abnormal[:3]
        )
        parts.append(f"Abnormal values: {flagged}.")
    else:
        parts.append("No abnormal lab values identified.")

    parts.append("Please share this document with your clinician for formal review.")
    return " ".join(parts)
