# MediSync — The Invisible Health Ledger

## What this is

A patient-controlled health-records platform. Patients upload medical documents from
any source (prescriptions, lab reports, discharge summaries). The system parses them
into structured data, builds a chronological timeline, flags drug conflicts across the
full medication history, and lets patients share scoped, time-limited views with clinicians.

This is the production evolution of MedInsight (our 6th-sem mini-project). MedInsight's
OCR → BioBERT NER → LLM pipeline is reused as the parsing core; everything else is new.

## Hackathon context

Judges score: technical implementation,
innovation, real-world impact, UI/UX & functionality, presentation. They WILL ask us to
defend the code live. Keep logic readable and commented. No clever one-liners.

## Tech stack (do not deviate without asking)

- Frontend: Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui, lucide-react
- Backend: FastAPI (Python 3.11)
- DB/Auth: Supabase (Postgres + pgvector + Auth + Row-Level Security)
- OCR: PyMuPDF + pytesseract + Pillow  (reused from MedInsight)
- NER: HuggingFace BioBERT `dmis-lab/biobert-base-cased-v1.2`  (reused)
- LLM: Groq `openai/gpt-oss-120b` (primary) with automatic fallback to Gemini
  `gemini-2.5-flash` on RateLimitError/APIConnectionError/APIStatusError. NOTE:
  llama-3.3-70b-versatile was deprecated by Groq on 2026-06-17 and is shut down by
  August 2026 — do not use it or suggest reverting to it.
- Embeddings (RAG, MediSync 2.0): Gemini `gemini-embedding-001` via the same
  google-genai client used for vision, output_dimensionality=768,
  task_type=RETRIEVAL_DOCUMENT for stored chunks / RETRIEVAL_QUERY for search queries.
  Do NOT add sentence-transformers, transformers, or torch as dependencies — see
  Railway constraint below.
- TTS: Sarvam AI Bulbul v3 (see services/tts.py) — the edge-tts entry was stale
  and never matched the shipped implementation.

## Architecture

Next.js client → FastAPI backend → { Doc parser (OCR+NER), Conflict engine,
Sharing service } → { BioBERT NER, RAG, Groq } → Supabase (Postgres + pgvector).

External: ABDM sandbox (ABHA verification), DrugBank Open Data (interaction reference).

## Repo layout

```
medisync/
  frontend/                  # Next.js 14 app
    app/
      (auth)/login, signup
      (patient)/dashboard, timeline, record/[id], share, alerts, settings
      (clinician)/shared/[token]   # read-only scoped view via share link
      layout.tsx, page.tsx         # landing
    components/ui/           # shadcn components
    components/              # app components (Timeline, RecordCard, ConflictAlert, ShareDialog, ...)
    lib/                     # api.ts, supabase.ts, types.ts, utils.ts
  backend/
    main.py
    routers/                 # upload, process, records, conflicts, share, abha
    services/                # ocr.py, ner.py, llm.py, tts.py (reused) + conflict.py, rag.py, abha.py
    models/schemas.py
    utils/
  supabase/migrations/       # SQL schema + RLS
```

## Security requirements (this is a medical app — non-negotiable)

- All Supabase tables have Row-Level Security ON. Patients see ONLY their own rows.
- Share recipients see ONLY records inside an active, non-expired, non-revoked grant scope.
- Never ship API keys to the client. Groq/Gemini calls happen server-side in FastAPI only.
- Every record access (view/download/share/revoke) writes a row to `access_log`.
- Share links use a long random token (not sequential IDs). Default expiry 7 days, revocable.
- Uploaded files stored in a private Supabase Storage bucket, served via signed URLs.

## Coding conventions

- TypeScript strict. No `any` unless justified with a comment.
- Components small and single-purpose. Server components by default; "use client" only when needed.
- API calls go through `lib/api.ts`, never inline fetch in components.
- Python: type hints everywhere, Pydantic models for all request/response shapes.
- Comment the non-obvious logic: conflict-detection rules, share-grant authorization, NER→schema mapping.

## UI principles (professional clinical aesthetic)

- Calm, trustworthy palette: slate/white base, teal/blue primary, amber for warnings,
  red ONLY for severe drug-conflict alerts. Generous whitespace. No gradients/neon.
- shadcn/ui components throughout (Card, Button, Dialog, Badge, Table, Tabs, Alert, Skeleton).
- Loading states (Skeleton) on every async view. Empty states with a clear next action.
- Fully responsive (patients are on phones). Accessible: labels, focus rings, ARIA on icon buttons.
- Severity encoded by color AND text, never color alone.

## Reuse policy

backend/services/ocr.py, ner.py, llm.py, tts.py are adapted from MedInsight and may be
copied with light edits. Everything in the "new" list below is built fresh this phase.

## Python version note

Backend venv is Python 3.11. Do NOT use PEP 695 generic syntax (class Foo[T]).
Use typing.TypeVar + Generic[T] instead.

## Supabase SQL note

Always include GRANT statements after CREATE TABLE + RLS.
service_role, authenticated, and anon all need explicit GRANT
even when service_role bypasses RLS.

## Gemini SDK

Use the new google-genai SDK (from google import genai; genai.Client()).
NOT the deprecated google.generativeai package (EOL Nov 30 2025).
Models: gemini-3.5-flash (vision/OCR), gemini-2.5-flash (LLM fallback from Groq),
gemini-embedding-001 (embeddings for RAG).

## Deployment constraint (Railway free tier — non-negotiable)

Railway Free plan: 0.5 GB RAM / 1 vCPU / 0.5 GB volume. Hard constraints:

- No torch, no transformers, no sentence-transformers — too large for the container.
- No Redis, no second Railway service.
- All embedding and secondary-LLM calls go through hosted APIs (Gemini), never local models.
- BioBERT NER (services/ner.py) stays as-is only because it is already deployed and
  working — do not add any NEW heavy local model dependency during MediSync 2.0.

## MediSync 2.0 — hackathon update context

This is a 5-day scoped update (14–18 July 2026) for simultaneous submission to
HackVenture and Build in AI for India. It is NOT a rewrite. Git commit timestamps
must stay inside that window for both hackathons' eligibility.

**Team and branch model:** Two people, two coding agents, working in parallel:
- `backend-dev`: Claude Code (Suyash) — backend features, RAG, tier gating, rate limiting
- `frontend-dev`: Antigravity/Gemini (teammate) — UI overhaul, chat panel, dashboard

Both branches merge into `main` at defined phase checkpoints. Both agents should
assume the other branch is moving concurrently and avoid assumptions about files
only the other track owns.

**Conflict-avoidance notes:** `frontend/app/(patient)/record/[id]/page.tsx` is an
exception to the backend/** vs frontend/** split — both tracks touched it this
phase (A5's TTS integration, B3's access-layer gating). Check it explicitly at
every merge checkpoint from here on, not just this file.

**Locked scope (dependency order):**
1. Embedding-on-upload pipeline
2. RAG retrieval + chat endpoint with citations and refusal
3. Floating chat panel UI
4. Tier gating + 7-day trial
5. Full UI overhaul to sidebar (desktop) + hamburger drawer (mobile)
6. Dashboard checkup suggestions (cached, reuses RAG retrieval)
7. TTS caching + slowapi rate limiting on public routes

Diet/lifestyle/workout advice was explicitly considered and cut — do not add it.

**Tier model:**
- Free: document upload, timeline, drug-conflict detection, multilingual UI
- Paid: AI summaries, TTS, RAG chatbot, checkup suggestions, sharing
- New signups get a 7-day trial of paid features
- Gating: `profiles.is_paid` boolean + `profiles.trial_ends_at` timestamp, toggled
  manually in Supabase table editor for demo — no real payment integration this phase

**Respect API_CONTRACT.md** This file has the temprorary mock infrastructure plan, has this project's upcoming work in split between two developers working remotely on different git branches.

**CLAUDE.md updates:** This file gets a short "Phase N update" append after every
phase completes, so both agents always have current context without re-reading
conversation history.

### Phase A1 complete (embedding pipeline)
`record_chunks` table (768-dim pgvector, RLS-scoped) + `match_record_chunks` RPC landed in
migration 008. `services/embeddings.py` wraps `gemini-embedding-001` with asymmetric task types
(RETRIEVAL_DOCUMENT for stored chunks, RETRIEVAL_QUERY for search). Chunking + embedding is wired
inline into `routers/upload.py` (non-blocking try/except after structured-data persist).
`scripts/backfill_embeddings.py` handles existing records. RAG retrieval + `/api/chat` (A2) depends on this.

### Phase A2 complete (RAG chat)
`/api/chat` endpoint (`routers/chat.py`) grounded on `record_chunks` via `rag.search_records`.
Deterministic refusal gate (`rag.is_relevant`, `SIMILARITY_FLOOR=0.58`) blocks LLM calls when no
chunk clears the threshold — verified empirically against medical vs. adversarial queries.
Groq `openai/gpt-oss-120b` → Gemini `gemini-2.5-flash` fallback via `services/llm_client.py`.
Sources (`record_id`, `snippet`) returned per API contract. Frontend chat panel (B2) can now wire
to the real endpoint; the dev bypass in `chat.py` must be replaced with `get_current_patient` before merge.

### Phase B1 complete (UI shell)
Left sidebar (desktop) + hamburger left-drawer (mobile) adopted app-wide, legacy top nav removed.
Note the shared nav-link list location so future links go in one place.

### Phase A3 complete (tier gating)
- `profiles.is_paid` + `trial_ends_at` (migration 009), `has_active_access()` function
- `require_active_access` FastAPI dependency (402 on paid routes), `GET /me/access` (ungated)
- Gated: `/api/chat`, share-link creation. Free: upload, timeline, drug-conflict, upload/OCR/NER.
- 7-day trial auto-granted via `handle_new_user()` trigger on signup (migration 010)
- Migration 009's column-level UPDATE grant broke PostgREST upserts (42501 on signup);
  fixed in 011 via table-level GRANT + BEFORE UPDATE trigger (`prevent_tier_self_upgrade`)
  enforcing `is_paid`/`trial_ends_at` lockdown at the trigger level instead of the grant level
- Migration 012: `profiles.email` now set from `NEW.email` on signup (was null since 007)
- Demo: toggle `is_paid` / `trial_ends_at` via service-role only (dashboard or backend)

### SECURITY FIX (16 July 2026): cross-patient data leak in match_record_chunks
`match_record_chunks` (008) had no ownership filter, relying on RLS which the backend's
service-role client (`utils/db.py` `get_supabase`) bypasses entirely. Every caller of
`search_records()` — both `/api/chat` (A2) and `/suggestions/refresh` (A4) — could retrieve
and act on OTHER patients' record chunks. Confirmed via zero-record throwaway user
receiving another patient's real lab data.

Fixed in migration 014: `match_record_chunks` now requires `p_user_id` (no default, old
2-arg signature dropped not overloaded), filters inside the SQL function before
ranking/limit. `rag.py`'s `search_records()` updated to pass it. Both call sites inherited
the fix with zero code changes of their own (single shared call site).

Re-verified: zero-record user → `suggestions: []` and chat `refused: true` (previously
returned another patient's data in both). Demo account's legitimate retrieval confirmed
unaffected (positive control).

### Phase B2 complete (floating chat panel)
Floating chat panel UI implemented and wired live against backend `/chat/` endpoint (FastAPI RAG). Renders source citations linking to `/record/[record_id]`, formats refusal states in warning style, handles 402 tier gating via a lock placeholder upgrading overlay card, and displays the underlying LLM provider under assistant messages.

### Phase B3 complete (Access Layer & Billing Gating)
Client-side access controls landed: `useAccess` context hook queries `GET /profile/access/` with active trial mock fallbacks for local dev.
Gated paid surfaces: AI clinical summaries, TTS play button, Share link creation (`ShareDialog`), dashboard Checkup Suggestions (Phase B4 placeholder), and Floating Chat entry/panel.
Ungated free surfaces: Document uploads, timeline/record viewing, drug-conflict alerts, language switching. Free workflows fail-open on fetch delays or route failures.

### Phase A5 complete (TTS caching + rate limiting)
- TTS ported from dead backend/services/tts.py + ungated frontend/app/api/tts/route.ts into
  a real, gated POST /tts/ endpoint (require_active_access), chunked Sarvam synthesis, and a
  sha256(text|language_code)-keyed cache in the tts-cache Supabase Storage bucket.
- slowapi per-IP limits (5/min TTS, 10/min share view) via a shared utils/limiter.py — no
  middleware, no Redis.
- frontend/app/api/tts/route.ts removed; record page now calls the backend via a new
  ttsApi.synthesise() helper in lib/api.ts and plays audio_url directly (no blob/object-URL).
- KNOWN DEVIATION: the 402 (trial expired) handling in record/[id]/page.tsx does NOT use
  PaidGate/useAccess — that access-layer stack (AccessControl.tsx, AccessContext.tsx,
  FloatingChat.tsx's 402 handler) only exists on frontend-dev, unmerged as of this branch.
  Used a self-contained `err instanceof APIError && err.status === 402` toast + "Upgrade"
  button instead, marked with a TODO comment in the handleTts() catch block. This MUST be
  swapped for <PaidGate>/useAccess once frontend-dev merges — do not let the TODO survive
  past that merge.
- EXPECTED MERGE CONFLICT: frontend-dev has independently modified this same
  record/[id]/page.tsx (145-line B3 change touching the same TTS handler region). At the
  M3 merge checkpoint, resolve by keeping backend-dev's ttsApi.synthesise() call + audio_url
  playback logic (the actual backend integration) but taking frontend-dev's PaidGate/useAccess
  version of the 402 branch, deleting the toast-based TODO fallback entirely rather than
  merging both.

### Phase B4 complete (dashboard suggestions)
Live "Suggested check-ups" card wired to GET /suggestions/ + POST /suggestions/refresh,
replacing the static Phase B3 placeholder. Gated via the now-real useAccess/PaidGate — the
access-endpoint fix (frontend now calls the real GET /me/access instead of the missing
/profile/access/) means this gating is genuinely enforced, not the old fail-open mock.
Each suggestion shows a "Why?" link to its source record when based_on_record_id is set;
Skeleton loading state and an empty state ("Upload records to get personalised check-up
suggestions") are included.

### Phase B5 complete (timeline export)
Existing multi-select + "Share selected" retained; added a documents-only "Export / Print PDF"
action to the same bar, via window.print() + @media print CSS (no jsPDF/html2canvas — those
taint on cross-origin Supabase signed URLs), fetching a fresh signed URL per selected record
(no batch endpoint) and rendering one document per printed page. PDFs are embedded via
`<iframe>` (shipped over the link-list fallback — iframe rendering isn't subject to canvas
taint). Free feature, not gated — only share-link creation is paid.
