-- ============================================================================
-- Migration 012: add email to handle_new_user() INSERT
-- ============================================================================
--
-- Gap found during A3.3 verification: every signup since migration 007
-- (which added the email column) has profiles.email = null.  Migration 007
-- backfilled existing rows once, but neither handle_new_user() nor the
-- frontend upsert (signup/page.tsx:95) writes the email column for new users.
--
-- Fix: include email in the trigger's INSERT using NEW.email.
-- auth.users has a native `email` column; NEW.email is the correct reference
-- inside a trigger on that table (same as NEW.id already in use).
--
-- No backfill for rows created between migrations 007 and 012 — out of scope
-- and not requested.  The Settings page falls back to auth.getUser() for
-- display, so existing null rows are not user-visible.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    INSERT INTO public.profiles (id, full_name, date_of_birth, abha_number, email, trial_ends_at)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', 'Patient'),
        COALESCE(
            (NEW.raw_user_meta_data->>'date_of_birth')::DATE,
            '1990-01-01'::DATE
        ),
        NEW.raw_user_meta_data->>'abha_number',
        NEW.email,
        now() + interval '7 days'
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;
