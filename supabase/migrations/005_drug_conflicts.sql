-- Migration 005: drug_conflicts table.
--
-- Stores detected drug-drug interaction (DDI) alerts for each patient.
-- Detection is deterministic (curated CSV dataset); the LLM only generates
-- the patient-facing plain-language explanation after a match is confirmed.
--
-- Severity uses domain-specific values: minor | moderate | major.
-- (These differ from the general SeverityLevel enum used elsewhere.)
--
-- The UNIQUE constraint on (patient_id, drug_a, drug_b) prevents duplicate
-- alerts. drug_a and drug_b are stored sorted alphabetically so the pair
-- (Warfarin, Aspirin) and (Aspirin, Warfarin) resolve to the same row.

CREATE TABLE IF NOT EXISTS public.drug_conflicts (
    id               uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id       uuid         NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    drug_a           text         NOT NULL,
    drug_b           text         NOT NULL,
    severity         text         NOT NULL CHECK (severity IN ('minor', 'moderate', 'major')),
    mechanism        text,
    description      text,        -- Clinical description from the curated dataset
    explanation      text,        -- LLM-generated plain-language patient explanation
    is_acknowledged  boolean      NOT NULL DEFAULT false,
    detected_at      timestamptz  NOT NULL DEFAULT now(),

    -- Store the pair sorted so (A,B) and (B,A) resolve to the same unique row.
    CONSTRAINT uq_patient_drug_pair UNIQUE (patient_id, drug_a, drug_b)
);

-- ── Row-Level Security ────────────────────────────────────────────────────────

ALTER TABLE public.drug_conflicts ENABLE ROW LEVEL SECURITY;

-- Patients may read, update (acknowledge), and have rows inserted by the
-- service role on their behalf.  They cannot delete — the audit trail matters.
CREATE POLICY "patients_own_conflicts"
    ON public.drug_conflicts
    FOR ALL
    USING  (patient_id = auth.uid())
    WITH CHECK (patient_id = auth.uid());

-- ── Grants ────────────────────────────────────────────────────────────────────

GRANT SELECT, INSERT, UPDATE ON public.drug_conflicts TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.drug_conflicts TO service_role;
