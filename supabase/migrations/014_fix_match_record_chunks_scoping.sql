-- 014_fix_match_record_chunks_scoping.sql
--
-- CRITICAL FIX: cross-patient data leak in match_record_chunks.
--
-- match_record_chunks (008_record_chunks.sql) had no ownership filter of its
-- own — it relied on RLS on record_chunks to scope results to the caller.
-- But every backend caller (services/rag.py search_records, used by both
-- /api/chat and checkup-suggestions generation) goes through the service-role
-- client (utils/db.py get_supabase), which BYPASSES RLS entirely by design.
-- With no RLS in effect and no WHERE clause in the function, the RPC ranked
-- and returned the closest chunks across ALL patients, not just the caller's.
--
-- Confirmed via a zero-record throwaway test user whose call to
-- /suggestions/refresh returned another patient's real lab results.
--
-- Fix: add a required p_user_id parameter and filter on it inside the SQL
-- function, before ranking/limiting — not as a PostgREST filter chained
-- after .rpc(), which would run after the function already ranked and
-- capped rows (corrupting top-k results, per the original function's now-
-- removed comment) and would still leak the mere existence of other
-- patients' chunks.
--
-- The old 2-arg signature is dropped outright (not left as a second
-- overload) so the insecure version is not silently still callable.

drop function if exists public.match_record_chunks(vector(768), int);

create or replace function public.match_record_chunks(
    query_embedding vector(768),
    p_user_id       uuid,
    match_count     int default 5
)
returns table (
    id          bigint,
    record_id   uuid,
    content     text,
    similarity  float
)
language sql
stable
as $$
    select
        rc.id,
        rc.record_id,
        rc.content,
        1 - (rc.embedding <=> query_embedding) as similarity
    from public.record_chunks rc
    where rc.user_id = p_user_id
    order by rc.embedding <=> query_embedding
    limit match_count;
$$;

-- Explicit grant required again — DROP FUNCTION also drops its grants.
grant execute on function public.match_record_chunks(vector(768), uuid, int)
    to service_role, authenticated;
