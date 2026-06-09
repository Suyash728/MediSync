"""
Drug-conflict detection service — new in MediSync (not in MedInsight).

Algorithm:
  1. Pull all active medications for the patient from Supabase.
  2. For every pair (drug_a, drug_b), look up the DrugBank Open Data interaction CSV.
  3. If an interaction exists, create/update a DrugConflict row in Supabase.
  4. Severity levels: low | moderate | high | severe.
     Only "severe" uses the red destructive colour — see UI principles.

DrugBank data: loaded once at startup from a local CSV file.
The CSV is downloaded as part of setup (see README — DrugBank Open Data licence).

This stub will be replaced with the real implementation in Phase 4.
"""

# import csv
# from pathlib import Path
# from models.schemas import DrugConflict, SeverityLevel


async def scan_patient_conflicts(patient_id: str) -> list[dict]:
    """Detect drug interactions for all active medications of a patient.

    Args:
        patient_id: UUID of the patient whose records should be scanned.

    Returns:
        List of DrugConflict dicts (written to DB by the caller).
    """
    raise NotImplementedError("Conflict detection will be implemented in Phase 4.")


def lookup_interaction(drug_a: str, drug_b: str) -> dict | None:
    """Look up a pair of drugs in the DrugBank interaction table.

    Returns a dict with {severity, description, recommendation} or None if no
    known interaction exists.
    """
    raise NotImplementedError("DrugBank lookup will be implemented in Phase 4.")
