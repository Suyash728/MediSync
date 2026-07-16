-- ============================================================================
-- Migration 011: fix profiles UPDATE permissions broken by migration 009
-- ============================================================================
--
-- Problem (discovered in A3.3 verification):
--   Migration 009 did:
--     REVOKE UPDATE ON public.profiles FROM authenticated;
--     GRANT UPDATE (full_name, date_of_birth, …) ON public.profiles TO authenticated;
--   PostgREST checks for TABLE-LEVEL UPDATE privilege before executing any
--   upsert (INSERT ON CONFLICT DO UPDATE) or PATCH request.  Column-level
--   grants are not visible to PostgREST's privilege gate, so it returns
--   HTTP 403 / pg code 42501 on every profile write from the browser client.
--   Affected flows: signup upsert (non-fatal), settings language save (user-visible),
--   WelcomeModal onboarding update (user-visible).
--
-- Fix:
--   1. Restore table-level UPDATE to authenticated so PostgREST allows profile
--      writes again.
--   2. Enforce the is_paid / trial_ends_at restriction at the Postgres trigger
--      level instead, where it cannot be bypassed by PostgREST at all.
--
-- Role-detection strategy:
--   The schema has no prior use of current_user / current_setting checks.
--   We use `current_user` (the PostgreSQL effective role within the current
--   transaction).  PostgREST sets this via SET LOCAL ROLE:
--     • service-role key request  → current_user = 'service_role'
--     • authenticated user JWT    → current_user = 'authenticated'
--   The trigger runs as SECURITY INVOKER (the default — not SECURITY DEFINER),
--   so current_user always reflects the PostgREST session role, not a fixed
--   owner.  This is the standard pattern for row-level enforcement in
--   PostgreSQL triggers on Supabase.
-- ============================================================================


-- 1. Restore table-level UPDATE ───────────────────────────────────────────────
-- Migration 009's REVOKE removed the table-level privilege that PostgREST
-- requires.  Column-level grants from 009 become redundant but are harmless;
-- they remain in place without any functional effect.
GRANT UPDATE ON public.profiles TO authenticated;


-- 2. Trigger function ─────────────────────────────────────────────────────────
-- SECURITY INVOKER (default): current_user reflects who called the UPDATE,
-- not the function owner.  That is the key invariant this trigger relies on.
CREATE OR REPLACE FUNCTION public.prevent_tier_self_upgrade()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    -- service_role (backend service key, Supabase dashboard, billing webhooks)
    -- must be able to set is_paid and trial_ends_at freely.
    IF current_user = 'service_role' THEN
        RETURN NEW;
    END IF;

    -- Every other role (authenticated, anon) is blocked from changing the
    -- tier columns, even on their own row.
    IF (NEW.is_paid      IS DISTINCT FROM OLD.is_paid     ) OR
       (NEW.trial_ends_at IS DISTINCT FROM OLD.trial_ends_at) THEN
        RAISE EXCEPTION
            'permission denied: is_paid and trial_ends_at may only be '
            'modified by the service role';
    END IF;

    RETURN NEW;
END;
$$;


-- 3. Attach trigger ───────────────────────────────────────────────────────────
DROP TRIGGER IF EXISTS prevent_tier_self_upgrade ON public.profiles;

CREATE TRIGGER prevent_tier_self_upgrade
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.prevent_tier_self_upgrade();


-- 4. GRANTs ───────────────────────────────────────────────────────────────────
-- Trigger functions are invoked by the database engine, not called directly,
-- so no GRANT EXECUTE is needed on prevent_tier_self_upgrade().
-- The GRANT UPDATE above is the only permission change in this migration.
