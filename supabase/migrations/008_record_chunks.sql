-- 008_record_chunks.sql
-- Stores embedding chunks for RAG retrieval over patient records.
-- Each row is a text fragment of a health_record with its 768-dim Gemini embedding.

create extension if not exists vector;

create table if not exists public.record_chunks (
    id          bigint      generated always as identity primary key,
    -- health_records.id is UUID (see 001_schema.sql); record_id must match.
    record_id   uuid        not null references public.health_records(id) on delete cascade,
    user_id     uuid        not null default auth.uid(),
    content     text        not null,
    embedding   vector(768),
    created_at  timestamptz default now()
);

-- RLS: owners only. auth.uid() wrapped in a subselect so Postgres caches the
-- value once per statement rather than re-evaluating it per row.
alter table public.record_chunks enable row level security;

create policy "chunks_select_own"
    on public.record_chunks for select
    using ((select auth.uid()) = user_id);

create policy "chunks_insert_own"
    on public.record_chunks for insert
    with check ((select auth.uid()) = user_id);

create policy "chunks_update_own"
    on public.record_chunks for update
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create policy "chunks_delete_own"
    on public.record_chunks for delete
    using ((select auth.uid()) = user_id);

-- Btree index for RLS row filtering. No vector index: at our scale
-- brute-force cosine scan is exact and requires no maintenance.
create index if not exists record_chunks_user_id_idx
    on public.record_chunks (user_id);

-- Explicit grants required even though service_role bypasses RLS.
grant select, insert, update, delete
    on public.record_chunks to service_role;
grant select, insert, update, delete
    on public.record_chunks to authenticated;
grant select
    on public.record_chunks to anon;

-- Grant usage on the identity sequence so service_role can insert rows.
grant usage, select
    on sequence public.record_chunks_id_seq to service_role;
grant usage, select
    on sequence public.record_chunks_id_seq to authenticated;

-- ---------------------------------------------------------------------------
-- match_record_chunks
-- Cosine-similarity search over the caller's visible chunks (RLS scopes rows).
-- Returns rows ordered closest-first; similarity = 1 − cosine_distance.
-- ---------------------------------------------------------------------------
create or replace function public.match_record_chunks(
    query_embedding vector(768),
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
    order by rc.embedding <=> query_embedding
    limit match_count;
$$;

-- Grant execute so authenticated callers (and service_role) can invoke it.
grant execute on function public.match_record_chunks(vector(768), int)
    to service_role, authenticated;
