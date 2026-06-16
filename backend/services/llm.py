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
# Summary is generated AFTER the reference range fallback so it can cite
# resolved ranges and flag abnormal values even when the document didn't
# include a reference column.
#
# Prompt structure differs by record_type — see _INSTRUCTIONS dict below.
# The resolved-lab block is only injected for lab_report and discharge_summary.

_SUMMARY_SYSTEM = (
    "You are a clinical documentation assistant producing concise, factual medical summaries."
)

# ── Per-type summary instructions ────────────────────────────────────────────
#
# Each entry is the "what to write" instructions block for that document type.
# _build_summary_prompt selects the right one and appends the data sections.
# Using a dict (not if/elif in the prompt) keeps each instruction self-contained
# and easy to update independently.

_INSTRUCTIONS: dict[str, str] = {
    "prescription": (
        "Write a concise clinical summary of this prescription document.\n\n"
        "Requirements:\n"
        "- State the document date, prescribing doctor, and facility if present.\n"
        "- List all medications prescribed with dosage, frequency, and duration.\n"
        "  If none identified, state \"No medications identified.\"\n"
        "- State the diagnosis or clinical indication if mentioned.\n"
        "- Note any special instructions (e.g. take with food, avoid alcohol,\n"
        "  complete the full course, monitor blood pressure).\n"
        "- Note any follow-up date or appointment if mentioned.\n"
        "- Do NOT include lab values, reference ranges, or laboratory parameter commentary.\n"
        "- Close with exactly this sentence:\n"
        "  \"Drug interactions across the full medication history are checked automatically.\"\n"
        "- Maximum 200 words. Clinical tone.\n"
    ),
    "lab_report": (
        "Write a concise clinical summary of this lab report.\n\n"
        "Requirements:\n"
        "- State the document date and facility if present.\n"
        "- For lab values use ONLY the resolved lab data provided below — not the raw text.\n"
        "  - ABNORMAL values lead: list every abnormal value explicitly with test name,\n"
        "    measured value with units, reference range, and whether it is HIGH or LOW.\n"
        "  - When the reference range comes from standard guidelines (not the document),\n"
        "    write \"based on standard reference range\" after citing it.\n"
        "  - If a value has no reference range, do not speculate about its normality.\n"
        "  - If no abnormal values found, state \"No abnormal lab values identified.\"\n"
        "  - Close the lab section with exactly ONE sentence listing parameters within range\n"
        "    (is_abnormal=false in the resolved data). Format:\n"
        "      Some abnormal, some normal → "
        "\"All other measured parameters — [names] — are within the reference range.\"\n"
        "      All values normal → "
        "\"All measured parameters are within the reference range — [names].\"\n"
        "      All values abnormal → omit this sentence entirely.\n"
        "    List test names only — no values, units, or ranges in the closing line.\n"
        "- Note any follow-up instructions mentioned in the document.\n"
        "- Do not speculate beyond the resolved data and source text.\n"
        "- Maximum 250 words. Clinical tone.\n"
    ),
    "discharge_summary": (
        "Write a concise clinical summary of this hospital discharge summary.\n\n"
        "Requirements:\n"
        "- State the date of discharge and treating facility if present.\n"
        "- State the primary diagnosis. List secondary diagnoses if present.\n"
        "- List procedures performed during the admission, if any.\n"
        "- List medications prescribed at discharge with dosage and frequency.\n"
        "  If none, state \"No medications listed at discharge.\"\n"
        "- Summarise key clinical findings during the admission. Mention lab values\n"
        "  only if clinically significant (abnormal or central to the diagnosis).\n"
        "- State the patient's condition at discharge (e.g. stable, improved, guarded).\n"
        "- Note follow-up instructions, appointment dates, and activity restrictions.\n"
        "- Do not speculate beyond what is stated in the source document.\n"
        "- Maximum 250 words. Clinical tone.\n"
    ),
    "imaging": (
        "Write a concise clinical summary of this radiology / imaging report.\n\n"
        "Requirements:\n"
        "- State the study type (X-Ray, USG, MRI, CT scan, etc.) and body part examined.\n"
        "- State the document date and the referring/reporting doctor or facility if present.\n"
        "- Quote key measurements or findings exactly as stated by the radiologist.\n"
        "- State the radiologist's impression or conclusion explicitly.\n"
        "- Flag any abnormal or significant findings prominently.\n"
        "- Do NOT mention lab values, blood test results, medications, or diagnoses\n"
        "  from other documents.\n"
        "- Do not speculate beyond what is stated in the imaging report.\n"
        "- Maximum 200 words. Clinical tone.\n"
    ),
    "vaccination": (
        "Write a concise clinical summary of this vaccination record.\n\n"
        "Requirements:\n"
        "- State the vaccine name and dose number (e.g. Dose 1 of 2) if mentioned.\n"
        "- State the date of administration.\n"
        "- State the next due date or booster schedule if mentioned.\n"
        "- State the administering facility or healthcare provider if present.\n"
        "- Mention the lot or batch number if present.\n"
        "- Do NOT use lab value language, medication dosage language, or reference ranges.\n"
        "- Maximum 150 words. Clinical tone.\n"
    ),
    "other": (
        "Write a concise clinical summary of this medical document.\n\n"
        "Requirements:\n"
        "- Identify and state the type of document based on its content.\n"
        "- Summarise the key clinical information present\n"
        "  (diagnoses, medications, findings, recommendations).\n"
        "- Do not assume a specific structure — follow what is actually in the document.\n"
        "- Do not speculate beyond what is present in the source text.\n"
        "- Maximum 200 words. Clinical tone.\n"
    ),
}

# Only these types receive the resolved-lab block in their summary prompt.
# For all other types the lab section is omitted — prescriptions, imaging reports,
# and vaccination records should never contain lab commentary.
_LAB_BLOCK_TYPES = frozenset({"lab_report", "discharge_summary"})

_MAX_SUMMARY_TOKENS = 500

# Maps BCP-47 language codes (used as preferred_language in profiles) to the
# plain English name appended to the summary prompt so the LLM knows which
# language to write in.  Structured extraction is always English — only the
# human-readable summary changes.
_LANGUAGE_NAMES: dict[str, str] = {
    "en-IN": "English",
    "hi-IN": "Hindi",
    "ta-IN": "Tamil",
    "bn-IN": "Bengali",
    "te-IN": "Telugu",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "gu-IN": "Gujarati",
    "pa-IN": "Punjabi",
    "or-IN": "Odia",
}


async def summarise_record_async(
    raw_text: str,
    entities: dict,
    resolved_lab_values: list[dict] | None = None,
    record_type: str = "other",
    language_code: str = "en-IN",
) -> str:
    """Generate a factual clinical summary.  Async (non-blocking I/O path).

    Must be called AFTER the reference range fallback so that resolved_lab_values
    contains complete reference ranges and is_abnormal flags.

    Tries Groq first; falls back to Gemini; falls back to a deterministic template
    if both APIs fail (e.g. during offline demo or API outage).

    Args:
        raw_text:             Raw OCR text (truncated to 3000 chars in the prompt).
        entities:             The structured extraction dict from extract_structured_async().
        resolved_lab_values:  The fully resolved lab_value DB rows after reference fallback.
                              Included in the prompt only for lab_report and discharge_summary
                              types; omitted for prescriptions, imaging, vaccinations, etc.
        record_type:          The document type (matches RecordType enum values).
                              Selects the type-specific prompt from _INSTRUCTIONS.
    """
    prompt = _build_summary_prompt(raw_text, entities, resolved_lab_values, record_type, language_code)
    result = await _try_groq_summary_async(prompt)
    if result is None:
        result = _try_gemini_summary_sync(prompt)
    if result is None:
        result = _fallback_summary(entities, resolved_lab_values, record_type)
    return result


def _build_summary_prompt(
    raw_text: str,
    entities: dict,
    resolved_lab_values: list[dict] | None = None,
    record_type: str = "other",
    language_code: str = "en-IN",
) -> str:
    instructions = _INSTRUCTIONS.get(record_type, _INSTRUCTIONS["other"])

    # Inject the resolved-lab block only for document types where lab values are
    # the primary content (lab_report) or useful context (discharge_summary).
    # For prescriptions, imaging, vaccinations, and other types the lab block is
    # omitted entirely — including it causes the LLM to add spurious lab commentary.
    if record_type in _LAB_BLOCK_TYPES:
        if record_type == "lab_report":
            lab_header = (
                "\nResolved lab values (reference ranges supplemented from "
                "WHO/ICMR standards where absent in document):\n"
            )
        else:  # discharge_summary
            lab_header = (
                "\nLab values from admission "
                "(context only — secondary to the discharge narrative):\n"
            )
        lab_section = lab_header + _format_resolved_labs(resolved_lab_values or [])
    else:
        lab_section = ""

    # Always strip raw lab_values from the entities block: the resolved list supersedes
    # them for lab/discharge types, and they're irrelevant for all other types.
    entities_for_summary = {k: v for k, v in entities.items() if k != "lab_values"}
    entities_str = json.dumps(entities_for_summary, indent=2, default=str)
    truncated    = raw_text[:3000] if len(raw_text) > 3000 else raw_text

    # Append a language instruction when the patient's preferred language is not English.
    # Only the human-readable summary changes — structured extraction always stays in English.
    lang_name = _LANGUAGE_NAMES.get(language_code, "English")
    if lang_name != "English":
        lang_instruction = (
            f"\n\nIMPORTANT: Write this entire summary in {lang_name}. "
            "Use clear, simple language appropriate for a patient reading their own medical record."
        )
        # The patient's metadata (document title, facility name, doctor name) may be written
        # in an Indian language script — alert the LLM to preserve them as-is.
        metadata_note = (
            "\n\nNote: the document title, facility name, and doctor name provided by the "
            "patient may be written in an Indian language — preserve them as-is and understand "
            "them in that language when generating the summary."
        )
    else:
        lang_instruction = ""
        metadata_note = ""

    return (
        instructions
        + lab_section
        + "\n\nExtracted structured data:\n"
        + entities_str
        + "\n\nRaw document text (first 3000 chars):\n"
        + truncated
        + metadata_note
        + lang_instruction
    )


def _format_resolved_labs(lab_rows: list[dict]) -> str:
    """Format resolved lab_value DB rows into a readable block for the summary prompt."""
    if not lab_rows:
        return "  (no lab values extracted)"

    lines = []
    for lab in lab_rows:
        name      = lab.get("test_name") or "?"
        value_str = str(lab.get("value") or "?")
        unit      = lab.get("unit") or ""
        ref_range = lab.get("reference_range") or ""
        ref_src   = lab.get("reference_source") or ""
        abnormal  = lab.get("is_abnormal")

        display_value = f"{value_str} {unit}".strip()

        if ref_range:
            src_note = " (standard reference range)" if ref_src == "standard" else " (document reference range)"
            ref_str  = f"ref {ref_range}{src_note}"
        else:
            ref_str = "no reference range available"

        if abnormal is True:
            direction = _compute_direction(value_str, ref_range)
            flag = f" — ABNORMAL {direction}".rstrip() if direction else " — ABNORMAL"
        elif abnormal is False:
            flag = " — within range"
        else:
            flag = " — abnormality unknown (no range)"

        lines.append(f"  • {name}: {display_value}, {ref_str}{flag}")

    return "\n".join(lines)


def _compute_direction(value_str: str, range_str: str) -> str:
    """Return 'HIGH', 'LOW', or '' for a value vs a reference range string."""
    import re as _re
    try:
        num_m = _re.search(r"-?[\d,]+\.?\d*", value_str)
        if not num_m:
            return ""
        num = float(num_m.group().replace(",", ""))
        rng = range_str.replace(",", "").strip()

        m = _re.match(r"^([\d.]+)\s*[-–—]\s*([\d.]+)$", rng)
        if m:
            low, high = float(m.group(1)), float(m.group(2))
            if num < low:
                return "LOW"
            if num > high:
                return "HIGH"
            return ""

        if _re.match(r"^<\s*[\d.]+$", rng):
            return "HIGH"   # value is above the upper-only threshold
        if _re.match(r"^>\s*[\d.]+$", rng):
            return "LOW"    # value is below the lower-only threshold
    except Exception:
        pass
    return ""


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


def _fallback_summary(
    entities: dict,
    resolved_lab_values: list[dict] | None = None,
    record_type: str = "other",
) -> str:
    """Deterministic template used when both LLM APIs are unavailable.

    Branches by record_type so the fallback text matches the document —
    prescriptions don't mention labs, imaging doesn't mention medications, etc.
    """
    logger.warning("Both LLM APIs failed — using template fallback summary.")
    parts: list[str] = []

    if record_type == "prescription":
        meds = entities.get("medications", [])
        if meds:
            names = ", ".join(
                m.get("drug_name") or m.get("name") or str(m) for m in meds[:5]
            )
            parts.append(f"Medications prescribed: {names}.")
        else:
            parts.append("No medications identified.")
        diag = entities.get("diagnoses", [])
        if diag:
            parts.append(f"Indication: {', '.join(str(d) for d in diag[:3])}.")
        parts.append(
            "Drug interactions across the full medication history are checked automatically."
        )

    elif record_type == "lab_report":
        # Full lab-report behaviour: abnormal callouts + normal-confirmation closing line.
        labs     = resolved_lab_values if resolved_lab_values is not None else entities.get("lab_values", [])
        abnormal = [lv for lv in labs if lv.get("is_abnormal") is True]
        normal   = [lv for lv in labs if lv.get("is_abnormal") is False]

        if abnormal:
            flagged = ", ".join(
                f"{lv.get('test_name', '?')} {lv.get('value', '?')}"
                for lv in abnormal[:3]
            )
            parts.append(f"Abnormal values: {flagged}.")
        else:
            parts.append("No abnormal lab values identified.")

        # Normal-confirmation closing line — mirrors the LLM prompt rule exactly
        if normal and abnormal:
            normal_names = ", ".join(lv.get("test_name", "?") for lv in normal)
            parts.append(
                f"All other measured parameters — {normal_names} — are within the reference range."
            )
        elif normal and not abnormal:
            normal_names = ", ".join(lv.get("test_name", "?") for lv in normal)
            parts.append(
                f"All measured parameters are within the reference range — {normal_names}."
            )
        # All abnormal → omit the closing line

    elif record_type == "discharge_summary":
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
            parts.append(f"Medications at discharge: {names}.")

    elif record_type == "imaging":
        parts.append(
            "Imaging study — findings could not be automatically summarised."
        )
        parts.append(
            "Please review the original report for the radiologist's findings and impression."
        )

    elif record_type == "vaccination":
        meds = entities.get("medications", [])
        if meds:
            vax_name = meds[0].get("drug_name") or meds[0].get("name") or "Vaccine"
            parts.append(f"Vaccination record: {vax_name}.")
        else:
            parts.append("Vaccination record.")

    else:  # "other" and any unknown types
        diag = entities.get("diagnoses", [])
        if diag:
            parts.append(f"Diagnoses: {', '.join(str(d) for d in diag[:5])}.")
        meds = entities.get("medications", [])
        if meds:
            names = ", ".join(
                m.get("drug_name") or m.get("name") or str(m) for m in meds[:5]
            )
            parts.append(f"Medications: {names}.")
        if not parts:
            parts.append("Document content could not be automatically summarised.")

    parts.append("Please share this document with your clinician for formal review.")
    return " ".join(parts)
