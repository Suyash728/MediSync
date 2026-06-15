-- Migration 006: add recommendation column to drug_conflicts.
--
-- Splits the previous single explanation field into two:
--   explanation    — what this interaction means / what could happen (LLM)
--   recommendation — what the patient should do (LLM, separate sentence)
--
-- Idempotent:
--   • ADD COLUMN IF NOT EXISTS is a no-op when the column already exists.
--   • DROP NOT NULL is a no-op when the column is already nullable.
--   Together they handle both "column missing" (fresh DB) and "column present
--   as NOT NULL" (live DB where a previous draft migration added it that way).

ALTER TABLE public.drug_conflicts
    ADD COLUMN IF NOT EXISTS recommendation text;

-- In case the column was previously added with NOT NULL, relax it.
-- PostgreSQL does not error when the column is already nullable.
ALTER TABLE public.drug_conflicts
    ALTER COLUMN recommendation DROP NOT NULL;
