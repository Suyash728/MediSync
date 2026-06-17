"""
Seed demo data for MediSync — idempotent, safe to run multiple times.

Creates a demo patient and a representative set of health records so judges
can see the full feature set (timeline, drug conflict, abnormal lab values,
share link) without having to upload real documents.

Demo credentials:
    email:    demo@medisync.app
    password: Demo@2026

Run from the backend/ directory:
    python scripts/seed_demo.py

Requires a .env file (or env vars) with SUPABASE_URL and SUPABASE_SERVICE_KEY.
All inserts bypass RLS — the service-role key is used throughout.
"""

import os
import sys
import uuid
from datetime import date, timezone, datetime

import httpx
from dotenv import load_dotenv
from supabase import create_client, Client

# ── Config ────────────────────────────────────────────────────────────────────

load_dotenv()

SUPABASE_URL         = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

DEMO_EMAIL    = "demo@medisync.app"
DEMO_PASSWORD = "Demo@2026"
DEMO_NAME     = "Arjun Mehta"         # realistic Indian patient name
DEMO_DOB      = "1985-03-15"

# ── Supabase client (service role — bypasses RLS) ─────────────────────────────

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# ── Helpers ───────────────────────────────────────────────────────────────────

def admin_headers() -> dict:
    """Headers for the Supabase Auth admin REST API."""
    return {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey":        SUPABASE_SERVICE_KEY,
        "Content-Type":  "application/json",
    }


def get_existing_demo_user() -> str | None:
    """Return the existing demo user's UUID, or None if not found."""
    resp = httpx.get(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=admin_headers(),
        params={"page": 1, "per_page": 50},
        timeout=15,
    )
    resp.raise_for_status()
    users = resp.json().get("users", [])
    for user in users:
        if user.get("email") == DEMO_EMAIL:
            return user["id"]
    return None


def create_demo_user() -> str:
    """Create the demo auth user and return its UUID."""
    resp = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=admin_headers(),
        json={
            "email":            DEMO_EMAIL,
            "password":         DEMO_PASSWORD,
            "email_confirm":    True,           # skip email verification
            "user_metadata": {
                "full_name":    DEMO_NAME,
                "date_of_birth": DEMO_DOB,
            },
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def ensure_profile(patient_id: str) -> None:
    """Upsert a profiles row for the demo patient."""
    supabase.table("profiles").upsert({
        "id":                 patient_id,
        "full_name":          DEMO_NAME,
        "date_of_birth":      DEMO_DOB,
        "email":              DEMO_EMAIL,
        "preferred_language": "en-IN",
    }).execute()
    print(f"  ✓ profile row upserted for {patient_id}")


def insert_record(patient_id: str, record: dict) -> str:
    """Insert a health_record row and return its UUID."""
    record_id = str(uuid.uuid4())
    supabase.table("health_records").insert({
        "id":                record_id,
        "patient_id":        patient_id,
        "processing_status": "done",
        **record,
    }).execute()
    return record_id


# ── Seed data ─────────────────────────────────────────────────────────────────

def seed(patient_id: str) -> None:
    print("  Inserting demo health records…")

    # ── Record A: CBC lab report ───────────────────────────────────────────────
    rec_cbc = insert_record(patient_id, {
        "record_type":   "lab_report",
        "title":         "Complete Blood Count (CBC)",
        "document_date": "2026-06-10",
        "facility":      "City Diagnostic Centre, Mumbai",
        "doctor":        "Dr. Neha Kapoor",
        "summary": (
            "CBC report from June 2026. WBC is mildly elevated at 12.5 × 10³/μL "
            "(reference 4–11), suggesting a possible mild infection or inflammation. "
            "Haemoglobin is low at 10.2 g/dL (reference 12–17.5), indicating mild "
            "anaemia. Platelet count is slightly high at 452 × 10³/μL (reference "
            "150–400). Follow up with your doctor to discuss these findings."
        ),
    })
    print(f"  ✓ Record A — CBC (id: {rec_cbc})")

    # Lab values for CBC
    supabase.table("lab_values").insert([
        {
            "patient_id":      patient_id,
            "record_id":       rec_cbc,
            "test_name":       "WBC Count",
            "value":           "12.5",
            "unit":            "× 10³/μL",
            "reference_range": "4.0–11.0",
            "is_abnormal":     True,
            "document_date":   "2026-06-10",
        },
        {
            "patient_id":      patient_id,
            "record_id":       rec_cbc,
            "test_name":       "Haemoglobin",
            "value":           "10.2",
            "unit":            "g/dL",
            "reference_range": "12.0–17.5",
            "is_abnormal":     True,
            "document_date":   "2026-06-10",
        },
        {
            "patient_id":      patient_id,
            "record_id":       rec_cbc,
            "test_name":       "Platelet Count",
            "value":           "452",
            "unit":            "× 10³/μL",
            "reference_range": "150–400",
            "is_abnormal":     True,
            "document_date":   "2026-06-10",
        },
        {
            "patient_id":      patient_id,
            "record_id":       rec_cbc,
            "test_name":       "RBC Count",
            "value":           "4.5",
            "unit":            "× 10⁶/μL",
            "reference_range": "4.0–6.0",
            "is_abnormal":     False,
            "document_date":   "2026-06-10",
        },
    ]).execute()
    print("  ✓ Lab values for CBC inserted")

    # ── Record B: Warfarin prescription ───────────────────────────────────────
    rec_warfarin = insert_record(patient_id, {
        "record_type":   "prescription",
        "title":         "Warfarin 5mg Prescription",
        "document_date": "2026-06-12",
        "facility":      "Apollo Hospital, New Delhi",
        "doctor":        "Dr. Priya Sharma (Cardiologist)",
        "summary": (
            "Prescription for Warfarin 5mg once daily, issued for atrial "
            "fibrillation management. INR monitoring required every 2 weeks. "
            "Avoid foods high in Vitamin K. Report any unusual bleeding immediately."
        ),
    })
    print(f"  ✓ Record B — Warfarin Rx (id: {rec_warfarin})")

    supabase.table("medications").insert({
        "patient_id":      patient_id,
        "record_id":       rec_warfarin,
        "name":            "Warfarin",
        "dosage":          "5 mg",
        "frequency":       "once daily",
        "duration":        "ongoing",
        "document_date":   "2026-06-12",
        "is_active":       True,
        "low_confidence":  False,
        "confidence_score": 0.97,
    }).execute()
    print("  ✓ Warfarin medication row inserted")

    # ── Record C: Aspirin prescription (triggers conflict) ────────────────────
    rec_aspirin = insert_record(patient_id, {
        "record_type":   "prescription",
        "title":         "Aspirin 81mg Prescription",
        "document_date": "2026-06-14",
        "facility":      "Max Healthcare, Mumbai",
        "doctor":        "Dr. Amit Verma (General Physician)",
        "summary": (
            "Low-dose Aspirin 81mg prescribed once daily for cardiovascular "
            "prevention. Note: patient is currently on Warfarin — please review "
            "the combined anticoagulant/antiplatelet risk with your cardiologist "
            "before starting this medication."
        ),
    })
    print(f"  ✓ Record C — Aspirin Rx (id: {rec_aspirin})")

    supabase.table("medications").insert({
        "patient_id":      patient_id,
        "record_id":       rec_aspirin,
        "name":            "Aspirin",
        "dosage":          "81 mg",
        "frequency":       "once daily",
        "duration":        "ongoing",
        "document_date":   "2026-06-14",
        "is_active":       True,
        "low_confidence":  False,
        "confidence_score": 0.99,
    }).execute()
    print("  ✓ Aspirin medication row inserted")

    # ── Record D: Discharge summary ───────────────────────────────────────────
    rec_discharge = insert_record(patient_id, {
        "record_type":   "discharge_summary",
        "title":         "Discharge Summary — Kidney Stone Procedure",
        "document_date": "2026-05-20",
        "facility":      "Kokilaben Dhirubhai Ambani Hospital, Mumbai",
        "doctor":        "Dr. Suresh Nair (Urologist)",
        "summary": (
            "Patient admitted on 2026-05-18 for right-sided ureteric stone "
            "(8mm) causing renal colic. Ureteroscopy with laser lithotripsy "
            "performed successfully on 2026-05-19. Stent placed; scheduled "
            "for removal in 4 weeks. Discharged on 2026-05-20 in stable "
            "condition. Medications at discharge: Tamsulosin 0.4mg OD, "
            "Ibuprofen 400mg TDS (7 days). Follow-up scheduled for 2026-06-17."
        ),
    })
    print(f"  ✓ Record D — Discharge summary (id: {rec_discharge})")

    supabase.table("medications").insert([
        {
            "patient_id":      patient_id,
            "record_id":       rec_discharge,
            "name":            "Tamsulosin",
            "dosage":          "0.4 mg",
            "frequency":       "once daily",
            "duration":        "ongoing",
            "document_date":   "2026-05-20",
            "is_active":       True,
            "low_confidence":  False,
            "confidence_score": 0.95,
        },
        {
            "patient_id":      patient_id,
            "record_id":       rec_discharge,
            "name":            "Ibuprofen",
            "dosage":          "400 mg",
            "frequency":       "thrice daily",
            "duration":        "7 days",
            "document_date":   "2026-05-20",
            "is_active":       False,          # short course — now inactive
            "low_confidence":  False,
            "confidence_score": 0.98,
        },
    ]).execute()
    print("  ✓ Discharge medications inserted")

    # ── Conflict E: Warfarin + Aspirin (SEVERE) ───────────────────────────────
    supabase.table("drug_conflicts").insert({
        "patient_id":     patient_id,
        "drug_a":         "Warfarin",
        "drug_b":         "Aspirin",
        "severity":       "severe",
        "description": (
            "Concurrent use of Warfarin (anticoagulant) and Aspirin "
            "(antiplatelet) significantly increases the risk of serious or "
            "fatal bleeding, including gastrointestinal haemorrhage and "
            "intracranial bleeding. The antiplatelet effect of Aspirin "
            "combined with the anticoagulant effect of Warfarin creates a "
            "compounded bleeding risk."
        ),
        "recommendation": (
            "Consult your cardiologist immediately before taking both "
            "medications together. If dual therapy is necessary, your doctor "
            "will set a lower INR target and prescribe a proton-pump inhibitor "
            "to protect the stomach. Do not start or stop either medication "
            "without medical supervision."
        ),
        "is_acknowledged": False,
        "record_ids":      [rec_warfarin, rec_aspirin],
    }).execute()
    print("  ✓ Warfarin + Aspirin SEVERE conflict row inserted")

    print()
    print("  Demo data seeded successfully.")
    print(f"  Timeline: 4 records ({rec_cbc}, {rec_warfarin}, {rec_aspirin}, {rec_discharge})")
    print(f"  Conflicts: 1 SEVERE (Warfarin + Aspirin)")
    print(f"  Lab values: 4 rows (3 abnormal)")
    print(f"  Medications: 4 rows (3 active)")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("MediSync — seeding demo patient data")
    print(f"  Target: {SUPABASE_URL}")
    print()

    # Check if demo user already exists
    print("  Checking for existing demo user…")
    patient_id = get_existing_demo_user()

    if patient_id:
        print(f"  Demo user already exists (id: {patient_id}) — skipping auth creation.")
        print("  Checking if data already seeded…")
        result = supabase.table("health_records").select("id", count="exact").eq("patient_id", patient_id).execute()
        count = result.count if result.count is not None else 0
        if count >= 4:
            print(f"  Already have {count} records — nothing to do. Exiting.")
            return
        print(f"  Only {count} record(s) found — re-seeding missing data.")
    else:
        print("  Creating demo auth user…")
        patient_id = create_demo_user()
        print(f"  ✓ Demo user created (id: {patient_id})")

    ensure_profile(patient_id)
    seed(patient_id)

    print()
    print("━" * 60)
    print("Demo credentials:")
    print(f"  Email:    {DEMO_EMAIL}")
    print(f"  Password: {DEMO_PASSWORD}")
    print("━" * 60)


if __name__ == "__main__":
    main()
