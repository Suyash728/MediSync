/**
 * Shared TypeScript types for MediSync.
 * These mirror the Pydantic schemas in backend/models/schemas.py.
 * Keep both files in sync when adding new fields.
 */

// ─── Enums ────────────────────────────────────────────────────────────────────

export type RecordType =
  | "prescription"
  | "lab_report"
  | "discharge_summary"
  | "imaging"
  | "vaccination"
  | "other";

// Severity used for drug-conflict alerts.
// Color mapping: low → slate, moderate → amber, high → orange, severe → red.
export type SeverityLevel = "low" | "moderate" | "high" | "severe";

// Severity values used specifically for drug-drug interaction (DDI) alerts.
// Color mapping: major → red (destructive), moderate → amber, minor → slate.
export type ConflictSeverity = "minor" | "moderate" | "major";

// ─── Domain models ────────────────────────────────────────────────────────────

export interface Patient {
  id: string;
  user_id: string;        // Supabase auth.users FK
  full_name: string;
  date_of_birth: string;  // ISO 8601 date
  abha_number?: string;   // ABDM Health ID
  phone?: string;
  created_at: string;
}

export interface MedicalRecord {
  id: string;
  patient_id: string;
  record_type: RecordType;
  title: string;
  document_date: string;  // Date on the physical document
  facility?: string;
  doctor?: string;
  file_path?: string;     // Path in Supabase Storage (not a public URL)
  raw_text?: string;      // OCR output stored for audit / re-processing
  parsed_data?: ParsedRecordData;
  processing_status: "pending" | "processing" | "done" | "failed" | "needs_review";
  created_at: string;
  updated_at: string;
}

// Structured output produced by the OCR → NER → LLM pipeline.
export interface ParsedRecordData {
  medications?: Medication[];
  diagnoses?: Diagnosis[];
  lab_results?: LabResult[];
  vitals?: Vital[];
  summary?: string;       // LLM-generated plain-English summary
}

export interface Medication {
  name: string;
  dosage?: string;
  frequency?: string;
  duration?: string;
  prescribing_doctor?: string;
  start_date?: string;
  end_date?: string;
  active: boolean;        // Derived: no end_date or end_date in future
}

export interface Diagnosis {
  name: string;
  icd_code?: string;
  date?: string;
  treating_doctor?: string;
}

export interface LabResult {
  test_name: string;
  value: string;
  unit?: string;
  reference_range?: string;
  is_abnormal: boolean | null;  // null = unknown (no reference range in document)
  date?: string;
}

export interface Vital {
  type: string;           // e.g. "blood_pressure", "heart_rate"
  value: string;
  unit?: string;
  date?: string;
}

// ─── Drug-conflict alert ──────────────────────────────────────────────────────

export interface DrugConflict {
  id: string;
  patient_id: string;
  drug_a: string;
  drug_b: string;
  severity: ConflictSeverity;
  mechanism: string | null;
  description: string | null;    // Clinical description from the curated dataset
  explanation: string | null;    // LLM: what this interaction means / what could happen
  recommendation: string | null; // LLM: what the patient should do
  is_acknowledged: boolean;
  detected_at: string;
}

// ─── Share grants ─────────────────────────────────────────────────────────────

export interface ShareGrant {
  id: string;
  patient_id: string;
  token: string;            // Cryptographically random, not guessable
  recipient_name?: string;
  recipient_email?: string;
  // null scope = share ALL records (patient chose to share everything)
  scope_record_ids?: string[];
  scope_record_types?: RecordType[];
  expires_at: string;
  is_active: boolean;       // Can be manually revoked by the patient
  created_at: string;
}

// ─── Access audit log ─────────────────────────────────────────────────────────

// Every view / download / share creation / share revocation writes one row.
export interface AccessLog {
  id: string;
  patient_id: string;
  record_id?: string;
  action:
    | "view"
    | "download"
    | "share_create"
    | "share_revoke"
    | "share_view";
  actor_type: "patient" | "clinician";
  actor_id?: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

// ─── API response wrappers ────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProcessingStatusResponse {
  record_id: string;
  status: MedicalRecord["processing_status"];
  error?: string;
}
