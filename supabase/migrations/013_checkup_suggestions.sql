-- ============================================================================
-- Migration 013: checkup_suggestions cache on profiles
-- ============================================================================
--
-- Adds two nullable columns to profiles so the upload pipeline can cache
-- the LLM-generated checkup suggestions alongside a generation timestamp.
-- These are server-side only — patients must not modify them directly.
--
-- Permission model:
--   service_role (backend) writes via the existing GRANT ALL (001_schema.sql).
--   authenticated users are blocked from writing these columns by extending the
--   prevent_tier_self_upgrade trigger that was installed in migration 011.
--   No new GRANT statements are needed; the existing table-level UPDATE for
--   authenticated (restored in migration 011) remains in place, and the trigger
--   below enforces the column-level restriction.
-- ============================================================================

-- 1. Add columns ──────────────────────────────────────────────────────────────
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS checkup_suggestions      JSONB,        -- NULL until first generation
    ADD COLUMN IF NOT EXISTS suggestions_generated_at TIMESTAMPTZ;  -- NULL until first generation


-- 2. Extend prevent_tier_self_upgrade to cover the new columns ────────────────
-- Rationale: checkup_suggestions and suggestions_generated_at are populated
-- exclusively by the backend service (service_role) at upload time.  Letting
-- an authenticated user overwrite them via a direct PostgREST PATCH would let
-- them inject arbitrary suggestion text visible in the dashboard.
CREATE OR REPLACE FUNCTION public.prevent_tier_self_upgrade()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    -- service_role (backend service key, Supabase dashboard) may change any column.
    IF current_user = 'service_role' THEN
        RETURN NEW;
    END IF;

    -- All other roles (authenticated, anon) are blocked from changing these
    -- server-managed columns, even on their own row.
    IF (NEW.is_paid IS DISTINCT FROM OLD.is_paid)
    OR (NEW.trial_ends_at IS DISTINCT FROM OLD.trial_ends_at)
    OR (NEW.checkup_suggestions IS DISTINCT FROM OLD.checkup_suggestions)
    OR (NEW.suggestions_generated_at IS DISTINCT FROM OLD.suggestions_generated_at)
    THEN
        RAISE EXCEPTION
            'permission denied: tier and suggestion columns may only be '
            'modified by the service role';
    END IF;

    RETURN NEW;
END;
$$;
-- The trigger itself (prevent_tier_self_upgrade BEFORE UPDATE) was created in
-- migration 011 with DROP TRIGGER IF EXISTS + CREATE TRIGGER.  The trigger row
-- already points to this function name, so replacing the function body here is
-- sufficient — no need to recreate the trigger object.
