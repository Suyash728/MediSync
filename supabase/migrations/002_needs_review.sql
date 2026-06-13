-- ============================================================================
-- Migration 002: add 'needs_review' to health_records processing_status CHECK
--
-- needs_review is set when the pipeline completes but extracts no medications
-- AND no lab values.  It signals to the patient that the document was parsed
-- but the parser found nothing structured — they should verify it manually.
--
-- The existing CHECK constraint must be dropped before adding the new one
-- because PostgreSQL does not support ALTER … ADD VALUE for CHECK constraints
-- (unlike enums).  This is safe: the constraint is re-created immediately.
-- ============================================================================

ALTER TABLE public.health_records
    DROP CONSTRAINT IF EXISTS health_records_processing_status_check;

ALTER TABLE public.health_records
    ADD CONSTRAINT health_records_processing_status_check
    CHECK (processing_status IN (
        'pending',
        'processing',
        'done',
        'failed',
        'needs_review'    -- extraction completed; no structured data found
    ));
