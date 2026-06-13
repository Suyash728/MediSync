"""
NER Service — adapted from MedInsight.

Uses BioBERT (dmis-lab/biobert-base-cased-v1.2) for biomedical named-entity
recognition, with robust regex fallback for lab values.

MediSync additions over MedInsight:
  1. `extract_entities_async()` — runs in a thread pool (model inference is
     CPU-bound and takes ~1–5 s per chunk).
  2. `map_ner_to_schema()` — converts raw NER output into the medications[] and
     lab_values[] rows that the DB schema expects.  See detailed comments below
     — this mapping is a common point of interest in Q&A.

BioBERT note: dmis-lab/biobert-base-cased-v1.2 is a BERT-base model fine-tuned
on biomedical text.  It recognises CHEMICAL/DRUG entities well but does NOT
output dosage or frequency — those come from the regex context search below.
"""

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# BioBERT NER pipeline — loaded once, then reused across requests.
# Loading takes ~10 s on first call (downloads ~400 MB from HuggingFace Hub).
_ner_pipeline = None


# ── Pipeline loading ──────────────────────────────────────────────────────────

def _get_pipeline():
    global _ner_pipeline
    if _ner_pipeline is None:
        logger.info("Loading BioBERT NER model (~400 MB first time)...")
        from transformers import pipeline

        model_name = "dmis-lab/biobert-base-cased-v1.2"
        try:
            _ner_pipeline = pipeline(
                "ner",
                model=model_name,
                aggregation_strategy="simple",
            )
            logger.info("BioBERT loaded successfully.")
        except Exception as exc:
            # biobert-base-cased-v1.2 may not have a NER head in all versions.
            # The regex extraction below handles lab values reliably without it.
            logger.warning("BioBERT NER unavailable (%s) — regex fallback only.", exc)
            _ner_pipeline = None
    return _ner_pipeline


# ── Public API ────────────────────────────────────────────────────────────────

def extract_entities(text: str) -> dict[str, list[Any]]:
    """Extract medical entities from OCR text.  Synchronous (from MedInsight)."""
    entities: dict[str, list] = {
        "diagnoses":      [],
        "medications":    [],
        "lab_values":     [],
        "abnormal_flags": [],
        "biomarkers":     [],
    }

    ner = _get_pipeline()
    if ner is not None:
        try:
            ner_results = _run_ner_chunked(ner, text)
            _classify_ner_entities(ner_results, entities)
        except Exception as exc:
            logger.warning("BioBERT NER failed (%s), using regex only.", exc)

    # Regex extraction is always run — more reliable for structured lab data
    _extract_lab_values_regex(text, entities)
    _extract_abnormal_flags(text, entities)
    _deduplicate(entities)
    return entities


async def extract_entities_async(text: str) -> dict[str, list[Any]]:
    """Async wrapper — NER model inference in a thread pool."""
    return await asyncio.to_thread(extract_entities, text)


# ── NER → DB schema mapping ───────────────────────────────────────────────────

# Regex patterns for dosage, frequency, and duration.
# These are applied to a ±200-char window around each medication mention.

# Dosage: "500 mg", "0.5 ml", "10 units", "100 IU", "1 tablet", "2 capsules"
_DOSAGE_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*"
    r"(mg|mcg|μg|ml|mL|g|units?|iu|IU|tablets?|caps?|capsules?)\b",
    re.IGNORECASE,
)

# Frequency: clinical abbreviations and plain English
_FREQUENCY_RE = re.compile(
    r"\b(once\s+(?:a\s+)?daily|twice\s+(?:a\s+)?daily|thrice\s+(?:a\s+)?daily"
    r"|OD|BD|TDS|QID|q\.?d\.?"
    r"|every\s+\d+\s+hours?"
    r"|q\d+h"
    r"|every\s+(?:morning|night|evening)"
    r"|at\s+bedtime"
    r"|as\s+needed|SOS|PRN)\b",
    re.IGNORECASE,
)

# Duration: "7 days", "2 weeks", "1 month", "3 months"
_DURATION_RE = re.compile(
    r"\b(\d+)\s+(days?|weeks?|months?)\b",
    re.IGNORECASE,
)

# NER confidence threshold below which we mark a result low_confidence.
_CONFIDENCE_THRESHOLD = 0.70


def map_ner_to_schema(
    entities: dict[str, list],
    raw_text: str,
    document_date: str | None,
    patient_id: str,
    record_id: str,
) -> tuple[list[dict], list[dict]]:
    """Convert NER output into medications[] and lab_values[] DB rows.

    ── How the medication mapping works ─────────────────────────────────────
    BioBERT identifies drug/chemical entity NAMES only (e.g. "Metformin").
    Dosage, frequency, and duration are NOT in the NER output — we extract
    them by searching a ±200-char context window around each drug mention in
    the raw OCR text using the regex patterns above.

    low_confidence is set to True when:
      a) NER confidence score < 0.70 (model was uncertain about the entity)
      b) The drug name could not be found in raw_text (possible OCR artefact)
    We keep all low-confidence entries rather than dropping them so patients
    can review uncertain extractions.

    ── How the lab-value mapping works ──────────────────────────────────────
    The regex extraction in ner.py already gives name/value/unit.  We merge
    with abnormal_flags (which contains both explicit H/L markers and
    out-of-range results from the common reference ranges check) to populate
    is_abnormal and reference_range.

    Args:
        entities:      Output from extract_entities().
        raw_text:      OCR text (used for dosage/frequency context search).
        document_date: ISO date string from the source record, or None.
        patient_id:    UUID from the verified JWT.
        record_id:     UUID of the newly-created health_records row.

    Returns:
        (medications_rows, lab_value_rows) — lists of dicts ready for DB insert.
    """
    meds = _map_medications(entities["medications"], raw_text, document_date, patient_id, record_id)
    labs = _map_lab_values(entities["lab_values"], entities["abnormal_flags"], document_date, patient_id, record_id)
    return meds, labs


# ── Internal helpers ──────────────────────────────────────────────────────────

def _run_ner_chunked(ner, text: str, chunk_size: int = 100) -> list:
    """Split text into word chunks to stay within BioBERT's 512-token limit."""
    words = text.split()
    results = []
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            try:
                results.extend(ner(chunk))
            except Exception as exc:
                logger.warning("NER chunk %d failed: %s", i, exc)
    return results


def _classify_ner_entities(ner_entities: list, entities: dict):
    """Route NER entities into the appropriate category bucket."""
    for ent in ner_entities:
        word  = ent.get("word", "").strip()
        group = ent.get("entity_group", ent.get("entity", "")).upper()
        score = ent.get("score", 0)

        if score < 0.5 or len(word) < 2:
            continue

        entry = {"text": word, "score": round(float(score), 3), "type": group}

        if "DISEASE" in group or "DIAG" in group:
            entities["diagnoses"].append(entry)
        elif "CHEMICAL" in group or "DRUG" in group or "MED" in group:
            entities["medications"].append(entry)
        elif "GENE" in group or "PROTEIN" in group:
            entities["biomarkers"].append(entry)
        else:
            entities["biomarkers"].append(entry)


def _extract_lab_values_regex(text: str, entities: dict):
    """Extract lab values using multi-line and inline regex strategies.
    Reused verbatim from MedInsight — reliable for tabular PDF lab reports."""

    KNOWN_TESTS = {
        "hemoglobin", "hgb", "hb", "rbc count", "rbc", "wbc count", "wbc",
        "platelet count", "platelets", "plt", "hematocrit", "hct",
        "mcv", "mch", "mchc", "rdw", "mpv",
        "neutrophils", "lymphocytes", "monocytes", "eosinophils", "basophils",
        "esr", "crp", "glucose", "fasting glucose", "random glucose",
        "creatinine", "bun", "urea", "uric acid",
        "cholesterol", "total cholesterol", "triglycerides", "hdl", "ldl", "vldl",
        "sgot", "sgpt", "ast", "alt", "alp", "bilirubin", "total bilirubin",
        "albumin", "total protein", "globulin",
        "sodium", "potassium", "calcium", "chloride", "phosphorus", "magnesium",
        "tsh", "t3", "t4", "free t3", "free t4", "hba1c",
        "iron", "ferritin", "tibc", "transferrin",
        "vitamin d", "vitamin b12", "folate", "folic acid",
    }

    EXCLUDE_NAMES = {
        "page", "date", "time", "age", "name", "sex", "male", "female",
        "test", "result", "unit", "flag", "ref range", "reference range",
        "report", "patient", "doctor", "lab", "total", "count",
        "interpretation", "recommendation", "pathologist",
    }

    # Strategy 1: multi-line column format (most PDFs extracted via PyMuPDF)
    lines = text.split("\n")
    i = 0
    while i < len(lines) - 1:
        line = lines[i].strip()
        if (
            line
            and re.match(r"^[A-Za-z]", line)
            and not re.match(r"^\d", line)
            and len(line) < 40
            and line.lower() not in EXCLUDE_NAMES
            and "_" not in line
        ):
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if re.match(r"^\d+\.?\d*$", next_line):
                value = next_line
                unit = ""
                if i + 2 < len(lines):
                    candidate = lines[i + 2].strip()
                    if (
                        candidate
                        and re.match(r"^[a-zA-Z/%µμ]", candidate)
                        and len(candidate) < 20
                        and not re.match(r"^\d", candidate)
                    ):
                        unit = candidate
                entities["lab_values"].append({"name": line, "value": value, "unit": unit})
                i += 3 if unit else 2
                continue
        i += 1

    # Strategy 2: inline format — only if strategy 1 found nothing
    if not entities["lab_values"]:
        patterns = [
            r"([A-Za-z][\w\s\(\)\.]{2,30}?)\s*[:=]\s*(\d+\.?\d*)\s*([a-zA-Z/%µμ][a-zA-Z/\s%µμ\d]*)",
            r"([A-Za-z][\w\s]{2,25}?)\s+(\d+\.?\d*)\s+([a-zA-Z/%µμ][a-zA-Z/\s%µμ]*)",
        ]
        for pattern in patterns:
            for m in re.finditer(pattern, text):
                name, value, unit = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
                if len(name) < 2 or name.lower() in EXCLUDE_NAMES:
                    continue
                try:
                    float(value)
                except ValueError:
                    continue
                entities["lab_values"].append({"name": name, "value": value, "unit": unit})


def _extract_abnormal_flags(text: str, entities: dict):
    """Flag abnormal values from explicit markers and common reference ranges."""
    for pattern in [r"(HIGH|LOW)\s+(.+?)(?=\n)", r"(.+?)\s+(?:HIGH|LOW|ABNORMAL|CRITICAL)"]:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            name = m.group(1).strip()
            if len(name) > 2 and name.lower() not in ("page", "date", "the"):
                entities["abnormal_flags"].append({
                    "name": name,
                    "flag": "ABNORMAL",
                    "context": m.group(0).strip()[:100],
                })
    _check_common_ranges(entities)


def _check_common_ranges(entities: dict):
    """Mark values outside commonly-accepted reference ranges as abnormal."""
    RANGES: dict[str, tuple[float, float]] = {
        "hemoglobin": (12.0, 17.5), "hgb": (12.0, 17.5), "hb": (12.0, 17.5),
        "wbc": (4000, 11000), "rbc": (4.0, 6.0),
        "platelet": (150000, 400000), "plt": (150000, 400000),
        "glucose": (70, 100), "fasting glucose": (70, 100),
        "creatinine": (0.6, 1.2), "bun": (7, 20),
        "cholesterol": (0, 200), "total cholesterol": (0, 200),
        "triglyceride": (0, 150), "hdl": (40, 60), "ldl": (0, 100),
        "hba1c": (4.0, 5.7), "tsh": (0.4, 4.0),
        "sodium": (135, 145), "potassium": (3.5, 5.0), "calcium": (8.5, 10.5),
    }

    for lab in entities["lab_values"]:
        name_lower = lab["name"].lower().strip()
        try:
            val = float(lab["value"])
        except (ValueError, TypeError):
            continue
        for range_name, (lo, hi) in RANGES.items():
            if range_name in name_lower:
                if val < lo or val > hi:
                    entities["abnormal_flags"].append({
                        "name":            lab["name"],
                        "value":           lab["value"],
                        "unit":            lab.get("unit", ""),
                        "flag":            "LOW" if val < lo else "HIGH",
                        "reference_range": f"{lo}–{hi}",
                    })
                break


def _deduplicate(entities: dict):
    for key in entities:
        seen, unique = set(), []
        for item in entities[key]:
            s = str(item)
            if s not in seen:
                seen.add(s)
                unique.append(item)
        entities[key] = unique


# ── Medication mapping ─────────────────────────────────────────────────────────

def _first_match(pattern: re.Pattern, text: str) -> str | None:
    """Return the full text of the first regex match, or None."""
    m = pattern.search(text)
    return m.group(0).strip() if m else None


def _map_medications(
    ner_meds: list[dict],
    raw_text: str,
    document_date: str | None,
    patient_id: str,
    record_id: str,
) -> list[dict]:
    """Map BioBERT medication entities to the medications table schema.

    For each entity the NER model found:
      1. Locate the drug name in the OCR text (case-insensitive).
      2. Extract a ±200-char context window around the match.
      3. Apply dosage/frequency/duration regex patterns to that window.
      4. Set low_confidence=True if NER score < threshold OR name not in text.
    """
    rows: list[dict] = []

    for med in ner_meds:
        name  = med.get("text", "").strip()
        score = float(med.get("score", 1.0))

        if not name or len(name) < 2:
            continue

        # Find the first occurrence of this drug name in the raw text
        idx = raw_text.lower().find(name.lower())
        if idx >= 0:
            # Window: 100 chars before, 200 chars after the mention
            context = raw_text[max(0, idx - 100) : idx + 200]
        else:
            # Couldn't locate the name — may be an OCR artefact
            context = ""

        dosage    = _first_match(_DOSAGE_RE,    context)
        frequency = _first_match(_FREQUENCY_RE, context)
        duration  = _first_match(_DURATION_RE,  context)

        # low_confidence: NER model was uncertain OR name absent from raw text
        low_conf = score < _CONFIDENCE_THRESHOLD or idx < 0

        rows.append({
            "patient_id":      patient_id,
            "record_id":       record_id,
            "name":            name,
            "dosage":          dosage,
            "frequency":       frequency,
            "duration":        duration,
            "document_date":   document_date,
            "is_active":       True,          # assume active; Phase 4 refines this
            "low_confidence":  low_conf,
            "confidence_score": round(score, 3),
        })

    return rows


# ── Lab value mapping ─────────────────────────────────────────────────────────

def _map_lab_values(
    ner_labs: list[dict],
    abnormal_flags: list[dict],
    document_date: str | None,
    patient_id: str,
    record_id: str,
) -> list[dict]:
    """Map regex-extracted lab values to the lab_values table schema.

    Merges with abnormal_flags to set is_abnormal and reference_range.
    Deduplicates by test name (keeps the first occurrence per test).
    """
    # Build a lowercase lookup from the abnormal_flags list
    abnormal_lookup: dict[str, dict] = {}
    for flag in abnormal_flags:
        key = flag["name"].lower().strip()
        abnormal_lookup.setdefault(key, flag)

    rows:      list[dict] = []
    seen_tests: set[str]  = set()

    for lab in ner_labs:
        name  = lab.get("name", "").strip()
        value = lab.get("value", "").strip()
        unit  = lab.get("unit", "").strip() or None

        if not name or not value:
            continue

        # Deduplicate: first occurrence of each test name wins
        key = name.lower()
        if key in seen_tests:
            continue
        seen_tests.add(key)

        # Check abnormal status by matching the test name (full or first word)
        flag_entry = (
            abnormal_lookup.get(key)
            or abnormal_lookup.get(key.split()[0])
        )
        is_abnormal     = flag_entry is not None
        reference_range = flag_entry.get("reference_range") if flag_entry else None

        rows.append({
            "patient_id":      patient_id,
            "record_id":       record_id,
            "test_name":       name,
            "value":           value,
            "unit":            unit,
            "reference_range": reference_range,
            "is_abnormal":     is_abnormal,
            "document_date":   document_date,
        })

    return rows
