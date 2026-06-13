-- ============================================================================
-- MediSync — Full Schema + Row-Level Security
-- Run this entire script in the Supabase SQL Editor (Settings → SQL Editor).
-- Order matters: referenced tables must exist before FKs are added.
-- ============================================================================

-- ── Extensions ───────────────────────────────────────────────────────────────
-- pgvector: stores 384-dim embeddings for RAG search (Phase 3)
-- uuid-ossp: gen_random_uuid() and uuid_generate_v4() helpers
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── 1. profiles ───────────────────────────────────────────────────────────────
-- One row per patient; id mirrors auth.users.id so auth.uid() works in RLS.
-- abha_number: the 14-digit ABDM Health ID (stored as-is; verified in Phase 5).
CREATE TABLE IF NOT EXISTS public.profiles (
    id              UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name       TEXT        NOT NULL,
    date_of_birth   DATE        NOT NULL,
    abha_number     VARCHAR(17),            -- 14 digits, stored with optional dashes
    phone           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "patient_own_profile_select" ON public.profiles
    FOR SELECT USING (id = auth.uid());

CREATE POLICY "patient_own_profile_insert" ON public.profiles
    FOR INSERT WITH CHECK (id = auth.uid());

CREATE POLICY "patient_own_profile_update" ON public.profiles
    FOR UPDATE USING (id = auth.uid()) WITH CHECK (id = auth.uid());


-- ── Auto-create profile from auth metadata when a new user signs up ──────────
-- The frontend also creates the profile explicitly, but this trigger is a
-- safety net in case the frontend call fails (e.g. tab closed mid-signup).
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    INSERT INTO public.profiles (id, full_name, date_of_birth, abha_number)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', 'Patient'),
        COALESCE(
            (NEW.raw_user_meta_data->>'date_of_birth')::DATE,
            '1990-01-01'::DATE
        ),
        NEW.raw_user_meta_data->>'abha_number'
    )
    ON CONFLICT (id) DO NOTHING;   -- frontend upsert wins; this is just a fallback
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- ── 2. health_records ─────────────────────────────────────────────────────────
-- One row per uploaded document.  The full pipeline writes to this table.
-- embedding: 384-dim vector from sentence-transformers all-MiniLM-L6-v2 (Phase 3).
CREATE TABLE IF NOT EXISTS public.health_records (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id          UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    record_type         TEXT        NOT NULL CHECK (record_type IN (
                            'prescription','lab_report','discharge_summary',
                            'imaging','vaccination','other')),
    title               TEXT        NOT NULL,
    document_date       DATE,
    facility            TEXT,
    doctor              TEXT,
    -- file_path is the path inside the 'medical-docs' private Storage bucket.
    -- Never stored as a public URL; signed URLs are generated on demand.
    file_path           TEXT,
    raw_text            TEXT,               -- OCR output (stored for audit / re-processing)
    summary             TEXT,               -- LLM-generated patient-facing summary
    processing_status   TEXT        NOT NULL DEFAULT 'pending'
                            CHECK (processing_status IN ('pending','processing','done','failed')),
    processing_error    TEXT,               -- populated when status = 'failed'
    embedding           vector(384),        -- for pgvector RAG search (Phase 3)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.health_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY "patient_own_records" ON public.health_records
    USING (patient_id = auth.uid())
    WITH CHECK (patient_id = auth.uid());

-- Automatically bump updated_at on every UPDATE
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER health_records_updated_at
    BEFORE UPDATE ON public.health_records
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ── 3. medications ────────────────────────────────────────────────────────────
-- One row per extracted medication per record.
-- low_confidence: true when the NER model scored < 0.7 OR the drug name could
-- not be located in the raw text (possible OCR artefact).  We surface these
-- rather than silently dropping them so the patient can review.
CREATE TABLE IF NOT EXISTS public.medications (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    record_id       UUID        NOT NULL REFERENCES public.health_records(id) ON DELETE CASCADE,
    name            TEXT        NOT NULL,
    dosage          TEXT,
    frequency       TEXT,
    duration        TEXT,
    document_date   DATE,           -- denormalised from health_records for fast queries
    is_active       BOOLEAN     NOT NULL DEFAULT true,
    low_confidence  BOOLEAN     NOT NULL DEFAULT false,
    confidence_score FLOAT,         -- raw NER score (0–1); NULL for regex-only extractions
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.medications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "patient_own_medications" ON public.medications
    USING (patient_id = auth.uid())
    WITH CHECK (patient_id = auth.uid());


-- ── 4. lab_values ─────────────────────────────────────────────────────────────
-- One row per extracted lab test result per record.
CREATE TABLE IF NOT EXISTS public.lab_values (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    record_id       UUID        NOT NULL REFERENCES public.health_records(id) ON DELETE CASCADE,
    test_name       TEXT        NOT NULL,
    value           TEXT        NOT NULL,
    unit            TEXT,
    reference_range TEXT,
    is_abnormal     BOOLEAN     NOT NULL DEFAULT false,
    document_date   DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.lab_values ENABLE ROW LEVEL SECURITY;

CREATE POLICY "patient_own_lab_values" ON public.lab_values
    USING (patient_id = auth.uid())
    WITH CHECK (patient_id = auth.uid());


-- ── 5. drug_conflicts ─────────────────────────────────────────────────────────
-- Populated by the conflict detection engine (Phase 4).
-- severity + color mapping: low=slate, moderate=amber, high=orange, severe=red.
CREATE TABLE IF NOT EXISTS public.drug_conflicts (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    drug_a          TEXT        NOT NULL,
    drug_b          TEXT        NOT NULL,
    severity        TEXT        NOT NULL CHECK (severity IN ('low','moderate','high','severe')),
    description     TEXT        NOT NULL,   -- plain-English explanation of the interaction
    recommendation  TEXT        NOT NULL,   -- what the patient/clinician should do
    is_acknowledged BOOLEAN     NOT NULL DEFAULT false,
    record_ids      UUID[]      NOT NULL DEFAULT '{}',  -- records containing these drugs
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.drug_conflicts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "patient_own_conflicts" ON public.drug_conflicts
    USING (patient_id = auth.uid())
    WITH CHECK (patient_id = auth.uid());


-- ── 6. share_grants ───────────────────────────────────────────────────────────
-- Each row represents a time-limited, revocable access grant for a clinician.
-- token: 32-byte hex string (secrets.token_hex(32)) — NOT sequential IDs.
-- scope_record_ids/scope_record_types: NULL means share all records.
-- The backend uses the service-role key to look up grants by token (bypasses RLS).
CREATE TABLE IF NOT EXISTS public.share_grants (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id          UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    token               TEXT        NOT NULL UNIQUE,
    recipient_name      TEXT,
    recipient_email     TEXT,
    scope_record_ids    UUID[],
    scope_record_types  TEXT[],
    expires_at          TIMESTAMPTZ NOT NULL,
    is_active           BOOLEAN     NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.share_grants ENABLE ROW LEVEL SECURITY;

-- Patients can read, create, and deactivate their own grants
CREATE POLICY "patient_own_grants" ON public.share_grants
    USING (patient_id = auth.uid())
    WITH CHECK (patient_id = auth.uid());


-- ── 7. access_log ─────────────────────────────────────────────────────────────
-- Append-only audit trail.  Every view/download/share event writes one row.
-- Patients can read their own log.  INSERT is allowed for patient actions.
-- Backend writes clinician rows using the service-role key (bypasses RLS).
CREATE TABLE IF NOT EXISTS public.access_log (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id  UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    record_id   UUID        REFERENCES public.health_records(id) ON DELETE SET NULL,
    action      TEXT        NOT NULL CHECK (action IN (
                    'view','download','share_create','share_revoke','share_view')),
    actor_type  TEXT        NOT NULL CHECK (actor_type IN ('patient','clinician')),
    actor_id    TEXT,               -- patient UUID or clinician identifier
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.access_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "patient_own_log_select" ON public.access_log
    FOR SELECT USING (patient_id = auth.uid());

CREATE POLICY "patient_own_log_insert" ON public.access_log
    FOR INSERT WITH CHECK (patient_id = auth.uid());


-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_health_records_patient_date
    ON public.health_records(patient_id, document_date DESC);

CREATE INDEX IF NOT EXISTS idx_medications_patient_id
    ON public.medications(patient_id);

CREATE INDEX IF NOT EXISTS idx_medications_record_id
    ON public.medications(record_id);

CREATE INDEX IF NOT EXISTS idx_lab_values_patient_id
    ON public.lab_values(patient_id);

CREATE INDEX IF NOT EXISTS idx_lab_values_record_id
    ON public.lab_values(record_id);

CREATE INDEX IF NOT EXISTS idx_share_grants_token
    ON public.share_grants(token);

CREATE INDEX IF NOT EXISTS idx_access_log_patient_id
    ON public.access_log(patient_id, created_at DESC);

-- pgvector cosine similarity index (for Phase 3 RAG)
-- Uncomment when embedding population begins.
-- CREATE INDEX idx_health_records_embedding
--     ON public.health_records USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);

-- Grant table access to all roles
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon;