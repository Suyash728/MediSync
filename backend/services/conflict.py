"""
Drug-drug interaction (DDI) detection service.

Interaction detection uses a curated dataset of ~100 clinically
significant DDI pairs. Production deployment would integrate a
licensed clinical decision support API (e.g. First Databank,
Multum) for comprehensive coverage.

Detection pipeline:
  1. Load the patient's active medications from the DB.
  2. Normalise each drug name:
       a. Strip dose/route suffixes ("Brufen 400mg" → "Brufen").
       b. Alias lookup (brand → generic, e.g. "Brufen" → "Ibuprofen").
       c. Fuzzy match against known drug names if alias lookup misses.
       d. Groq confirmation when fuzzy confidence is uncertain (0.65–0.80).
  3. Check every medication pair against the curated DDI dataset.
     THE MATCH IS DETERMINISTIC (CSV lookup) — the LLM only generates
     the plain-language explanation after a match is confirmed.
  4. For each matched pair call Groq (llama-3.3-70b-versatile) to produce
     a 2-3 sentence patient-facing explanation and action guidance.
  5. Persist new conflicts to drug_conflicts (existing rows are preserved
     so that is_acknowledged status is not reset on re-check).

Entry point:
  run_conflict_check(patient_id)  — async, returns list[dict] of new rows
"""

import csv
import difflib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_GROQ_MODEL = "llama-3.3-70b-versatile"

# ── Data file paths ────────────────────────────────────────────────────────────

_BASE       = Path(__file__).parent.parent / "data"
_DDI_CSV    = _BASE / "drug_interactions.csv"
_ALIAS_JSON = _BASE / "drug_name_aliases.json"

# ── In-memory DDI store (loaded once at import) ────────────────────────────────

@dataclass
class _DDIPair:
    drug_a:      str   # normalised lowercase canonical name
    drug_b:      str   # normalised lowercase canonical name
    severity:    str
    mechanism:   str
    description: str


# Maps (drug_a_lower, drug_b_lower) → _DDIPair (both orderings stored).
_DDI_LOOKUP:     dict[tuple[str, str], _DDIPair] = {}
# Set of all normalised drug names that appear in any DDI row.
_DDI_DRUG_NAMES: set[str] = set()
# Brand/alias → canonical generic name (keys are already lowercase).
_ALIAS_MAP: dict[str, str] = {}


def _load_data() -> None:
    global _DDI_LOOKUP, _DDI_DRUG_NAMES, _ALIAS_MAP

    # Load alias map
    try:
        with open(_ALIAS_JSON, encoding="utf-8") as fh:
            raw = json.load(fh)
        _ALIAS_MAP = {k.lower(): v for k, v in raw.get("aliases", {}).items()}
        logger.info("conflict: loaded %d drug aliases.", len(_ALIAS_MAP))
    except Exception as exc:
        logger.warning("conflict: could not load aliases: %s", exc)

    # Load DDI dataset
    try:
        with open(_DDI_CSV, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            count = 0
            for row in reader:
                a = row.get("drug_a", "").strip()
                b = row.get("drug_b", "").strip()
                if not a or not b:
                    continue
                pair = _DDIPair(
                    drug_a=a.lower(),
                    drug_b=b.lower(),
                    severity=row.get("severity", "moderate").strip(),
                    mechanism=row.get("mechanism", "").strip(),
                    description=row.get("description", "").strip(),
                )
                # Store both orderings so lookup is always O(1)
                _DDI_LOOKUP[(a.lower(), b.lower())] = pair
                _DDI_LOOKUP[(b.lower(), a.lower())] = pair
                _DDI_DRUG_NAMES.add(a.lower())
                _DDI_DRUG_NAMES.add(b.lower())
                count += 1
        logger.info(
            "conflict: loaded %d DDI pairs (%d unique drug names).",
            count, len(_DDI_DRUG_NAMES),
        )
    except Exception as exc:
        logger.warning("conflict: could not load DDI CSV: %s", exc)


_load_data()

# ── Groq client (lazy) ─────────────────────────────────────────────────────────

_groq_async_client = None


def _get_groq() -> Optional[object]:
    global _groq_async_client
    if _groq_async_client is None:
        try:
            from utils.config import settings
            if settings.groq_api_key:
                from groq import AsyncGroq
                _groq_async_client = AsyncGroq(api_key=settings.groq_api_key)
        except Exception as exc:
            logger.warning("conflict: Groq init failed: %s", exc)
    return _groq_async_client


# ── Drug name normalisation ────────────────────────────────────────────────────
#
# Three-pass cleaning:
#   1. Salt/counter-ion suffixes — "Warfarin Sodium" → "Warfarin"
#   2. Dosage noise              — "500 mg"          → ""
#   3. Route/scheduling words   — "Tablet SR OD"    → ""
#
# Order matters: salts first, then dose, then route.

_SALT_RE = re.compile(
    r'\b(sodium|potassium|hydrochloride|hcl|maleate|tartrate|mesylate|acetate|'
    r'phosphate|sulfate|sulphate|bisulfate|bisulphate|citrate|gluconate|fumarate|'
    r'bromide|chloride|carbonate|nitrate|succinate|monohydrate|dihydrate|anhydrous|'
    r'calcium|magnesium|zinc)\b',
    re.IGNORECASE,
)

_DOSE_RE = re.compile(
    r'\b\d+(\.\d+)?\s*(mg|mcg|g|ml|iu|units?)\b', re.IGNORECASE,
)

_ROUTE_RE = re.compile(
    # Plurals handled with s?: tablets? capsules? etc.
    r'\b(tablets?|capsules?|caps|syrups?|injections?|cream|gel|ointment|drops|'
    r'solution|suspension|tab|cap|inj|sr|er|xr|cr|la|od|bd|tds|qid)\.?\b|'
    r'\b(delayed|extended|modified|immediate)[- ]release\b',
    re.IGNORECASE,
)


def _clean_drug_name(raw_name: str) -> str:
    """Strip salt suffixes, dosage, route, and scheduling noise.

    Examples:
      'Warfarin Sodium 5 mg Tablet'       → 'warfarin'
      'Metformin HCl 500 mg SR'           → 'metformin'
      'Aspirin 81'                         → 'aspirin 81'  (no unit; handled by alias)
      'Fluoxetine Hydrochloride Caps 20mg' → 'fluoxetine'
      'Lisinopril 10mg OD'                → 'lisinopril'
    """
    name = raw_name.lower()
    name = _SALT_RE.sub("", name)
    name = _DOSE_RE.sub("", name)
    name = _ROUTE_RE.sub("", name)
    return re.sub(r'\s+', ' ', name).strip()


async def _confirm_with_groq(raw: str, candidate: str) -> bool:
    """Ask Groq whether raw_name and candidate refer to the same drug.

    Called only when fuzzy match confidence is in the uncertain range
    (0.65–0.80) to prevent false-positive DDI alerts from similarly-named
    but pharmacologically distinct drugs.
    Returns False if Groq is unavailable — erring on the side of caution.
    """
    client = _get_groq()
    if client is None:
        return False
    try:
        resp = await client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[{
                "role": "user",
                "content": (
                    f'Is "{raw}" the same drug as "{candidate}"? '
                    f'Reply with only "yes" or "no".'
                ),
            }],
            temperature=0,
            max_tokens=5,
        )
        return resp.choices[0].message.content.strip().lower().startswith("yes")
    except Exception as exc:
        logger.warning("conflict: Groq name-confirmation failed: %s", exc)
        return False


async def normalise_drug_name(raw_name: str) -> str:
    """Normalise a raw drug name string to its canonical generic form.

    Steps (tried in order):
      1. Clean: lowercase → strip salts → strip dose → strip route/scheduling.
      2. Direct DDI exact match (set lookup — covers salt-stripped names like
         'warfarin sodium' → 'warfarin' which is in _DDI_DRUG_NAMES).
      3. Exact alias lookup (brand → generic, e.g. 'Crocin' → 'paracetamol').
      4. Confident fuzzy alias (ratio ≥ 0.80).
      5. Uncertain fuzzy alias (0.65–0.80) → Groq confirmation.
      6. Confident fuzzy DDI name match (ratio ≥ 0.80).
      7. Uncertain fuzzy DDI (0.65–0.80) → Groq confirmation.
      8. Return the cleaned name as-is if nothing matches.
    """
    cleaned = _clean_drug_name(raw_name)
    if not cleaned:
        return raw_name.lower()

    # 1. Direct exact match in DDI set — fastest path, handles salt-stripped names
    if cleaned in _DDI_DRUG_NAMES:
        return cleaned

    # 2. Exact alias match
    if cleaned in _ALIAS_MAP:
        return _ALIAS_MAP[cleaned].lower()

    # 3. Confident fuzzy alias
    alias_candidates = list(_ALIAS_MAP.keys())
    alias_close = difflib.get_close_matches(cleaned, alias_candidates, n=1, cutoff=0.80)
    if alias_close:
        return _ALIAS_MAP[alias_close[0]].lower()

    # 4. Uncertain fuzzy alias → Groq confirmation
    alias_uncertain = difflib.get_close_matches(cleaned, alias_candidates, n=1, cutoff=0.65)
    if alias_uncertain:
        canonical = _ALIAS_MAP[alias_uncertain[0]]
        if await _confirm_with_groq(raw_name, canonical):
            return canonical.lower()

    # 5. Confident fuzzy DDI name match
    ddi_candidates = list(_DDI_DRUG_NAMES)
    ddi_close = difflib.get_close_matches(cleaned, ddi_candidates, n=1, cutoff=0.80)
    if ddi_close:
        return ddi_close[0]

    # 6. Uncertain fuzzy DDI → Groq confirmation
    ddi_uncertain = difflib.get_close_matches(cleaned, ddi_candidates, n=1, cutoff=0.65)
    if ddi_uncertain:
        if await _confirm_with_groq(raw_name, ddi_uncertain[0]):
            return ddi_uncertain[0]

    return cleaned


def _find_interaction(norm_a: str, norm_b: str) -> Optional[_DDIPair]:
    """O(1) lookup — both orderings are pre-stored in _DDI_LOOKUP."""
    return _DDI_LOOKUP.get((norm_a, norm_b))


# ── LLM explanation generation ─────────────────────────────────────────────────

async def _generate_explanation(
    drug_a_raw: str,
    drug_b_raw: str,
    severity: str,
    mechanism: str,
    description: str,
) -> str:
    """Generate a patient-facing plain-language explanation via Groq.

    THE DDI MATCH IS ALREADY CONFIRMED from the deterministic CSV lookup.
    The LLM's only job is to write a clear, calm, actionable explanation.
    Falls back to the clinical description if Groq is unavailable.
    """
    client = _get_groq()
    if client is None:
        return description

    prompt = (
        f"You are explaining a drug interaction to a patient in plain language.\n\n"
        f"Drug A: {drug_a_raw}\n"
        f"Drug B: {drug_b_raw}\n"
        f"Severity: {severity}\n"
        f"Mechanism: {mechanism}\n"
        f"Clinical note: {description}\n\n"
        f"Write exactly 2-3 sentences:\n"
        f"1. What this interaction means — what could happen.\n"
        f"2. What the patient should do (e.g. speak to their doctor before "
        f"stopping or changing medication; do not stop without advice; "
        f"watch for specific symptoms).\n\n"
        f"Keep it factual, calm, and under 70 words. "
        f"Do not diagnose, prescribe, or alarm unnecessarily."
    )

    try:
        resp = await client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a patient-education clinical writer. "
                        "Be factual, calm, and concise."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=150,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("conflict: explanation generation failed: %s", exc)
        return description


# ── Main entry point ───────────────────────────────────────────────────────────

async def run_conflict_check(patient_id: str) -> list[dict]:
    """Detect DDI pairs for a patient's active medications and persist new ones.

    Existing conflict rows are NOT overwritten (is_acknowledged status is
    preserved). Only truly new pairs are inserted.

    Returns:
        List of newly-inserted conflict row dicts (may be empty).
    """
    from utils.db import get_supabase
    supabase = get_supabase()

    # Load all active medications for this patient
    med_result = (
        supabase.table("medications")
        .select("id, name")
        .eq("patient_id", patient_id)
        .eq("is_active", True)
        .execute()
    )
    meds: list[dict] = med_result.data or []

    if len(meds) < 2:
        # Need at least two medications to have an interaction
        return []

    # Normalise each medication name
    norm_pairs: list[tuple[dict, str]] = []
    for med in meds:
        norm = await normalise_drug_name(med["name"])
        norm_pairs.append((med, norm))
        logger.debug("conflict: '%s' → '%s'", med["name"], norm)

    # Fetch existing conflict pairs so we don't re-insert or reset acknowledgements
    existing_result = (
        supabase.table("drug_conflicts")
        .select("drug_a, drug_b")
        .eq("patient_id", patient_id)
        .execute()
    )
    existing_pairs: set[tuple[str, str]] = {
        tuple(sorted([r["drug_a"].lower(), r["drug_b"].lower()]))
        for r in (existing_result.data or [])
    }

    # Check all (i, j) medication pairs — O(n²) but n is small (active meds)
    conflicts_to_insert: list[dict] = []
    checked: set[tuple[str, str]] = set()

    for i, (med_a, norm_a) in enumerate(norm_pairs):
        for med_b, norm_b in norm_pairs[i + 1:]:
            if norm_a == norm_b:
                continue

            pair_key = tuple(sorted([norm_a, norm_b]))
            if pair_key in checked:
                continue
            checked.add(pair_key)

            ddi = _find_interaction(norm_a, norm_b)
            if ddi is None:
                continue

            # Sort display names alphabetically so (A, B) == (B, A) in the DB
            display_a, display_b = sorted([med_a["name"], med_b["name"]])
            db_key = tuple(sorted([display_a.lower(), display_b.lower()]))

            if db_key in existing_pairs:
                logger.debug(
                    "conflict: %s + %s already recorded, skipping.",
                    display_a, display_b,
                )
                continue

            logger.info(
                "conflict: NEW %s — %s + %s",
                ddi.severity.upper(), display_a, display_b,
            )

            explanation = await _generate_explanation(
                display_a, display_b,
                ddi.severity, ddi.mechanism, ddi.description,
            )

            conflicts_to_insert.append({
                "patient_id":    patient_id,
                "drug_a":        display_a,
                "drug_b":        display_b,
                "severity":      ddi.severity,
                "mechanism":     ddi.mechanism or None,
                "description":   ddi.description or None,
                "explanation":   explanation,
                "is_acknowledged": False,
            })

    if conflicts_to_insert:
        supabase.table("drug_conflicts").insert(conflicts_to_insert).execute()
        logger.info(
            "conflict: inserted %d new conflict row(s) for patient %s.",
            len(conflicts_to_insert), patient_id[:8],
        )

    return conflicts_to_insert
