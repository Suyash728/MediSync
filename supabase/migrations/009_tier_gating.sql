-- ============================================================================
-- Migration 009: tier gating — is_paid, trial_ends_at, has_active_access()
-- ============================================================================

-- 1. Add tier columns ─────────────────────────────────────────────────────────
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS is_paid       BOOLEAN     NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMPTZ;           -- NULL = no trial

-- 2. has_active_access() ──────────────────────────────────────────────────────
-- Returns true when the given user is on a paid plan OR inside an active trial.
-- Defaults to auth.uid() so RLS expressions can call it with no args.
-- STABLE: safe for RLS and repeated calls within a single transaction.
CREATE OR REPLACE FUNCTION public.has_active_access(p UUID DEFAULT auth.uid())
RETURNS BOOLEAN
LANGUAGE sql STABLE
SET search_path = public
AS $$
    SELECT COALESCE(
        (SELECT is_paid OR (trial_ends_at IS NOT NULL AND now() < trial_ends_at)
         FROM public.profiles WHERE id = p),
        false
    );
$$;

-- 3. SELECT policy ────────────────────────────────────────────────────────────
-- "patient_own_profile_select" FOR SELECT USING (id = auth.uid()) already exists
-- from 001_schema.sql — no action needed.

-- 4. Column-level privilege tightening ────────────────────────────────────────
-- ⚠️  EXISTING UPDATE POLICY CONCERN (001_schema.sql line 33–34):
--
--     "patient_own_profile_update" FOR UPDATE
--         USING      (id = auth.uid())
--         WITH CHECK (id = auth.uid())
--
-- RLS can only gate WHICH ROW is updated, not WHICH COLUMNS.  With the
-- blanket GRANT UPDATE ON ALL TABLES in 001_schema.sql, an authenticated
-- user can PostgREST-PATCH their own row with {"is_paid": true}.
--
-- Fix: revoke table-level UPDATE from authenticated, then re-grant it on
-- only the patient-editable columns.  service_role keeps GRANT ALL (from
-- 001_schema.sql) and bypasses RLS, so backend writes to is_paid /
-- trial_ends_at via the service-role client still work.
REVOKE UPDATE ON public.profiles FROM authenticated;

GRANT UPDATE (
    full_name,
    date_of_birth,
    abha_number,
    phone,
    email,
    preferred_language,
    has_onboarded
) ON public.profiles TO authenticated;
-- is_paid and trial_ends_at are intentionally excluded — service_role only.

-- 5. Function grants ──────────────────────────────────────────────────────────
GRANT EXECUTE ON FUNCTION public.has_active_access(UUID) TO authenticated, service_role;
