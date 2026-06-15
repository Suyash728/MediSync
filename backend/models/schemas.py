"""
Pydantic v2 request/response schemas for the MediSync API.

These mirror the TypeScript types in frontend/lib/types.ts.
Keep both files in sync when adding new fields.

Design rule: every endpoint uses a Pydantic model — no bare dict returns.
This makes the implicit API contract explicit and gives us free validation.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from typing import TypeVar, Generic
T = TypeVar('T')


# ─── Enums ────────────────────────────────────────────────────────────────────

class RecordType(str, Enum):
    prescription       = "prescription"
    lab_report         = "lab_report"
    discharge_summary  = "discharge_summary"
    imaging            = "imaging"
    vaccination        = "vaccination"
    other              = "other"


class SeverityLevel(str, Enum):
    low      = "low"
    moderate = "moderate"
    high     = "high"
    severe   = "severe"


class ConflictSeverity(str, Enum):
    """Severity values used specifically for drug-drug interaction alerts."""
    minor    = "minor"
    moderate = "moderate"
    major    = "major"


class ProcessingStatus(str, Enum):
    pending      = "pending"
    processing   = "processing"
    done         = "done"
    failed       = "failed"
    # needs_review: extraction completed but returned no medications AND no lab values.
    # Shown to the patient as "needs review" so they know the data may be incomplete.
    needs_review = "needs_review"


# ─── Parsed record content ────────────────────────────────────────────────────

class Medication(BaseModel):
    name:               str
    dosage:             str | None = None
    frequency:          str | None = None
    duration:           str | None = None
    prescribing_doctor: str | None = None
    start_date:         str | None = None
    end_date:           str | None = None
    active:             bool = True


class Diagnosis(BaseModel):
    name:             str
    icd_code:         str | None = None
    date:             str | None = None
    treating_doctor:  str | None = None


class LabResult(BaseModel):
    test_name:       str
    value:           str
    unit:            str | None = None
    reference_range: str | None = None
    is_abnormal:     bool | None = None   # None = unknown (no reference range to compare against)
    date:            str | None = None


class Vital(BaseModel):
    type:  str   # e.g. "blood_pressure", "heart_rate"
    value: str
    unit:  str | None = None
    date:  str | None = None


class ParsedRecordData(BaseModel):
    """Structured output produced by the OCR → BioBERT NER → LLM pipeline."""
    medications: list[Medication] = []
    diagnoses:   list[Diagnosis]  = []
    lab_results: list[LabResult]  = []
    vitals:      list[Vital]      = []
    summary:     str | None = None   # LLM plain-English summary


# ─── Medical record ───────────────────────────────────────────────────────────

class MedicalRecordBase(BaseModel):
    record_type:   RecordType
    title:         str
    document_date: str           # ISO 8601 date string from the physical document
    facility:      str | None = None
    doctor:        str | None = None


class MedicalRecordCreate(MedicalRecordBase):
    """Schema used when the client POSTs a new record (before file upload)."""
    pass


class MedicalRecord(MedicalRecordBase):
    """Full record returned from GET endpoints."""
    id:                UUID
    patient_id:        UUID
    file_path:         str | None = None  # Path in Supabase Storage bucket
    raw_text:          str | None = None
    parsed_data:       ParsedRecordData | None = None
    processing_status: ProcessingStatus = ProcessingStatus.pending
    created_at:        datetime
    updated_at:        datetime

    model_config = {"from_attributes": True}


class ProcessingStatusResponse(BaseModel):
    record_id: UUID
    status:    ProcessingStatus
    error:     str | None = None


# ─── Drug-conflict alert ──────────────────────────────────────────────────────

class DrugConflict(BaseModel):
    id:               UUID
    patient_id:       UUID
    drug_a:           str
    drug_b:           str
    severity:         ConflictSeverity
    mechanism:        str | None = None   # Pharmacological mechanism from the dataset
    description:      str | None = None   # Clinical description from the dataset
    explanation:      str | None = None   # LLM-generated plain-language patient explanation
    is_acknowledged:  bool = False
    detected_at:      datetime

    model_config = {"from_attributes": True}


# ─── Share grants ─────────────────────────────────────────────────────────────

class ShareGrantCreate(BaseModel):
    recipient_name:    str | None = None
    recipient_email:   str | None = None
    # If both are None → share all records (patient's explicit choice)
    scope_record_ids:  list[UUID] | None = None
    scope_record_types: list[RecordType] | None = None
    expires_in_days:   int = Field(default=7, ge=1, le=30)


class ShareGrant(BaseModel):
    id:                  UUID
    patient_id:          UUID
    token:               str        # Cryptographically random token (not sequential)
    recipient_name:      str | None = None
    recipient_email:     str | None = None
    scope_record_ids:    list[UUID] | None = None
    scope_record_types:  list[RecordType] | None = None
    expires_at:          datetime
    is_active:           bool
    created_at:          datetime

    model_config = {"from_attributes": True}


# ─── Access audit log ─────────────────────────────────────────────────────────

class AccessLog(BaseModel):
    """One row per auditable action. Written by the backend — never by clients."""
    id:         UUID
    patient_id: UUID
    record_id:  UUID | None = None
    action:     str   # view | download | share_create | share_revoke | share_view
    actor_type: str   # patient | clinician
    actor_id:   str | None = None
    metadata:   dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Pagination wrapper ───────────────────────────────────────────────────────

class PaginatedResponse(BaseModel, Generic[T]):
    items:     list[T]
    total:     int
    page:      int
    page_size: int
