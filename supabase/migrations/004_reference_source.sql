-- Migration 004: Add reference_source to lab_values.
--
-- "lab_provided" = reference range was printed in the uploaded document.
-- "standard"     = range was filled in from the built-in WHO/ICMR lookup table.
-- NULL           = no reference range available from either source.
--
-- The frontend uses this to badge standard ranges with "Std" so patients
-- understand the range may not reflect their specific laboratory's equipment.

ALTER TABLE public.lab_values
    ADD COLUMN IF NOT EXISTS reference_source TEXT
        CHECK (reference_source IN ('lab_provided', 'standard'));
