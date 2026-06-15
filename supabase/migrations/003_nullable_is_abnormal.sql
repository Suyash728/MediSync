-- Migration 003: Allow lab_values.is_abnormal to be NULL.
--
-- NULL semantics:
--   NULL  = unknown (no reference range was available to compare against)
--   false = confirmed within range
--   true  = confirmed outside range
--
-- Previously NOT NULL DEFAULT false, which silently treated "no data" as "normal".

ALTER TABLE public.lab_values
    ALTER COLUMN is_abnormal DROP NOT NULL;
