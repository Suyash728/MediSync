-- Migration 007: add email and preferred_language to profiles
--
-- The profiles table was originally created without these columns; the settings
-- page SELECTs both, causing PostgREST to return a "column does not exist"
-- error on every load, which set profileState to "error" immediately.
--
-- preferred_language: BCP-47 locale tag, defaults to 'en-IN'.
-- email: copied from auth.users.email at signup; nullable because existing
--        rows pre-date this column.

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS email              TEXT,
    ADD COLUMN IF NOT EXISTS preferred_language TEXT NOT NULL DEFAULT 'en-IN';

-- Back-fill email from auth.users for any rows that already exist.
UPDATE public.profiles p
SET    email = u.email
FROM   auth.users u
WHERE  p.id = u.id
  AND  p.email IS NULL;

-- GRANTs: authenticated users already have UPDATE/SELECT on profiles via the
-- blanket grant in 001_schema.sql, so no new grants are needed here.
