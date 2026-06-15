"""
Reference range fallback lookup for lab values.

When a lab report does not provide a reference range column, this module
provides standard ranges sourced from WHO/ICMR guidelines for common Indian
lab tests.

Matching strategy (tried in order):
  1. Exact normalised-alias match   — "SGPT" → SGPT entry
  2. difflib fuzzy match (≥ 0.72)  — "S. Creatinine" → Serum Creatinine
     difflib naturally handles "serum creatinine" → "creatinine" (ratio ≈ 0.91)
     and common prefix variations like "S. Sodium" → "Sodium" (≈ 0.73)

compute_is_abnormal() parses the range string and compares the numeric value,
with an order-of-magnitude unit-mismatch guard to avoid false positives when
the document value is in different units than the reference range (e.g. WBC
reported as 7800 cells/cmm vs our range "4000 - 11000").
"""

import difflib
import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).parent.parent / "data" / "reference_ranges.json"

# Loaded once at import time.
_DB: list[dict] = []
_ALIAS_MAP: dict[str, dict] = {}   # normalised_alias → test entry


def _normalise(s: str) -> str:
    """Lowercase, strip non-alphanumeric characters (except spaces), collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", s.lower())).strip()


def _load() -> None:
    global _DB, _ALIAS_MAP
    try:
        with open(_DATA_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        _DB = data.get("tests", [])
        for entry in _DB:
            key = _normalise(entry["canonical_name"])
            _ALIAS_MAP[key] = entry
            for alias in entry.get("aliases", []):
                alias_key = _normalise(alias)
                # First writer wins — canonical names take priority over aliases
                _ALIAS_MAP.setdefault(alias_key, entry)
        logger.info("reference_lookup: loaded %d test definitions.", len(_DB))
    except Exception as exc:
        logger.warning("reference_lookup: could not load reference_ranges.json: %s", exc)


_load()


def lookup(test_name: str, sex: Optional[str] = None) -> Optional[tuple[str, str]]:
    """Look up the standard reference range for a lab test.

    Args:
        test_name: Test name as extracted from the document (any casing/prefix).
        sex: "male" | "female" | None — used for sex-stratified tests (Hb, creatinine, etc.).
             If None, the default (union of male/female) range is used.

    Returns:
        (reference_range_string, "standard") if a match is found, else None.
    """
    if not _DB:
        return None

    key = _normalise(test_name)
    if not key:
        return None

    # 1. Exact alias match
    entry = _ALIAS_MAP.get(key)

    # 2. difflib fuzzy match — handles prefixes ("s creatinine" → "creatinine")
    #    and British/American spelling variants
    if entry is None:
        candidates = list(_ALIAS_MAP.keys())
        close = difflib.get_close_matches(key, candidates, n=1, cutoff=0.72)
        if close:
            entry = _ALIAS_MAP[close[0]]

    if entry is None:
        return None

    # Pick the sex-appropriate range, fall back to default
    if sex == "male" and entry.get("range_male"):
        range_str = entry["range_male"]
    elif sex == "female" and entry.get("range_female"):
        range_str = entry["range_female"]
    else:
        range_str = (
            entry.get("range_default")
            or entry.get("range_male")
            or entry.get("range_female")
        )

    if not range_str:
        return None

    return range_str, "standard"


def compute_is_abnormal(value_str: str, reference_range: str) -> Optional[bool]:
    """Compare a lab value string against a reference range string.

    Handles these range formats:
      "13.0 - 17.0"      → abnormal if value < 13.0 or > 17.0
      "< 200"            → abnormal if value >= 200
      "<= 5.7"           → abnormal if value > 5.7
      "> 40"             → abnormal if value <= 40
      ">= 4.5"           → abnormal if value < 4.5
      "150,000-400,000"  → commas stripped; treated as 150000 - 400000

    Returns True (abnormal), False (normal), or None when the value is not
    numeric or the units appear mismatched (order-of-magnitude guard).
    """
    # Extract the first numeric token from the value string
    num_match = re.search(r"-?[\d,]+\.?\d*", value_str)
    if not num_match:
        return None
    try:
        num = float(num_match.group().replace(",", ""))
    except ValueError:
        return None

    # Strip commas from range ("150,000 - 400,000" → "150000 - 400000")
    rng = reference_range.replace(",", "").strip()

    # "N - M" or "N – M" (en-dash)
    m = re.match(r"^([\d.]+)\s*[-–—]\s*([\d.]+)$", rng)
    if m:
        low, high = float(m.group(1)), float(m.group(2))
        if _unit_mismatch(num, low, high):
            return None
        return not (low <= num <= high)

    # "> N" → abnormal if value <= N
    m = re.match(r"^>\s*([\d.]+)$", rng)
    if m:
        threshold = float(m.group(1))
        if _unit_mismatch(num, threshold, threshold * 2):
            return None
        return num <= threshold

    # ">= N" → abnormal if value < N
    m = re.match(r"^>=\s*([\d.]+)$", rng)
    if m:
        threshold = float(m.group(1))
        if _unit_mismatch(num, threshold, threshold * 2):
            return None
        return num < threshold

    # "< N" → abnormal if value >= N
    m = re.match(r"^<\s*([\d.]+)$", rng)
    if m:
        threshold = float(m.group(1))
        if _unit_mismatch(num, 0.0, threshold):
            return None
        return num >= threshold

    # "<= N" → abnormal if value > N
    m = re.match(r"^<=\s*([\d.]+)$", rng)
    if m:
        threshold = float(m.group(1))
        if _unit_mismatch(num, 0.0, threshold):
            return None
        return num > threshold

    return None    # unrecognised range format


def _unit_mismatch(value: float, low: float, high: float) -> bool:
    """Return True when the value is orders of magnitude off from the range.

    This guards against comparing a value expressed in one unit (e.g. 7800
    cells/cmm) against a range expressed in another (e.g. 4.0 - 11.0 × 10³).
    A ratio > 100× or < 0.01× from the midpoint signals a mismatch.
    """
    mid = (low + high) / 2.0 if (low + high) > 0 else high
    if mid == 0:
        return False
    ratio = value / mid
    return ratio > 100.0 or ratio < 0.01
