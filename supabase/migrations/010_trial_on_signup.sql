-- ============================================================================
-- Migration 010: auto-grant 7-day trial to new signups via handle_new_user()
-- ============================================================================
--
-- Change: adds trial_ends_at = now() + interval '7 days' to the INSERT in the
-- handle_new_user trigger so every new auth.users row automatically receives a
-- 7-day paid-feature trial without any manual Supabase dashboard edits.
--
-- ── ON CONFLICT flag ──────────────────────────────────────────────────────────
-- The trigger INSERT uses ON CONFLICT (id) DO NOTHING.  This is intentional
-- and safe:
--
--   1. The trigger fires AFTER INSERT ON auth.users, synchronously inside the
--      supabase.auth.signUp() database transaction.  The trigger therefore
--      always runs BEFORE the frontend's subsequent .upsert() call (which is a
--      separate HTTP request that can only start after signUp() returns).
--
--   2. The frontend upsert payload (signup/page.tsx:95) contains only
--      { id, full_name, date_of_birth, abha_number } — no trial_ends_at.
--      PostgREST's ON CONFLICT DO UPDATE only sets columns present in the
--      request body, so trial_ends_at written by the trigger is NOT overwritten.
--
--   3. DO NOTHING cannot skip the trial_ends_at write in the normal flow
--      because no profile row can exist before the auth.users INSERT (profiles.id
--      is a FK to auth.users.id with ON DELETE CASCADE).
--
-- If you ever want belt-and-suspenders protection against a pre-seeded profile
-- row that has trial_ends_at = null, replace DO NOTHING with:
--
--   ON CONFLICT (id) DO UPDATE
--       SET trial_ends_at = COALESCE(
--           public.profiles.trial_ends_at,
--           EXCLUDED.trial_ends_at
--       )
--
-- That patches trial_ends_at only when null on the existing row, without
-- touching any other column.  Not needed for the current schema but safe to
-- add if you want the trigger to be self-healing.
-- =============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    INSERT INTO public.profiles (id, full_name, date_of_birth, abha_number, trial_ends_at)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', 'Patient'),
        COALESCE(
            (NEW.raw_user_meta_data->>'date_of_birth')::DATE,
            '1990-01-01'::DATE
        ),
        NEW.raw_user_meta_data->>'abha_number',
        now() + interval '7 days'   -- auto-grant 7-day paid-feature trial
    )
    ON CONFLICT (id) DO NOTHING;   -- trigger always runs first; frontend upsert is safe
    RETURN NEW;
END;
$$;

-- No GRANT needed: handle_new_user() is a trigger function called by the
-- database engine, not invoked directly by any role.
-- The trigger itself was created in 001_schema.sql and is unchanged.
