~~***\# MediSync — The Invisible Health Ledger**


~~***\#\# What this is**


~~***A patient-controlled health-records platform. Patients upload medical documents from**


~~***any source (prescriptions, lab reports, discharge summaries). The system parses them**


~~***into structured data, builds a chronological timeline, flags drug conflicts across the**


~~***full medication history, and lets patients share scoped, time-limited views with clinicians.**


~~***This is the production evolution of MedInsight (our 6th-sem mini-project). MedInsight's**


~~***OCR → BioBERT NER → LLM pipeline is reused as the parsing core; everything else is new.**


~~***\#\# Hackathon context**


~~***CodeFusion 2026, Round 3 (implementation). Judges score: technical implementation,**


~~***innovation, real-world impact, UI/UX & functionality, presentation. They WILL ask us to**


~~***defend the code live. Keep logic readable and commented. No clever one-liners.**


~~***\#\# Tech stack (do not deviate without asking)**


~~***- Frontend: Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui, lucide-react**


~~***- Backend: FastAPI (Python 3.11)**


~~***- DB/Auth: Supabase (Postgres + pgvector + Auth + Row-Level Security)**


~~***- OCR: PyMuPDF + pytesseract + Pillow  (reused from MedInsight)**


~~***- NER: HuggingFace BioBERT \`dmis-lab/biobert-base-cased-v1.2\`  (reused)**


~~***- LLM: Groq \`llama-3.1-70b-versatile\`, Gemini fallback  (reused)**


~~***- Embeddings (RAG, optional phase): sentence-transformers \`all-MiniLM-L6-v2\` (384-dim)**


~~***- TTS: edge-tts \`en-IN-NeerjaNeural\`  (reused, optional)**


~~***\#\# Architecture**


~~***Next.js client  →  FastAPI backend  →  \{ Doc parser (OCR+NER), Conflict engine,**


~~***Sharing service \}  →  \{ BioBERT NER, RAG, Groq \}  →  Supabase (Postgres + pgvector).**


~~***External: ABDM sandbox (ABHA verification), DrugBank Open Data (interaction reference).**


~~***\#\# Repo layout**


~~***medisync/ frontend/                 \# Next.js 14 app app/ (auth)/login, signup (patient)/dashboard, timeline, record/\[id\], share, alerts, settings (clinician)/shared/\[token\]      \# read-only scoped view via share link layout.tsx, page.tsx            \# landing components/ui/          \# shadcn components components/             \# app components (Timeline, RecordCard, ConflictAlert, ShareDialog, ...) lib/                    \# api.ts, supabase.ts, types.ts, utils.ts backend/ main.py routers/                \# upload, process, records, conflicts, share, abha services/               \# ocr.py, ner.py, llm.py, tts.py (reused) + conflict.py, rag.py, abha.py models/schemas.py utils/ supabase/migrations/      \# SQL schema + RLS**


~~***\#\# Security requirements (this is a medical app — non-negotiable)**


~~***- All Supabase tables have Row-Level Security ON. Patients see ONLY their own rows.**


~~***- Share recipients see ONLY records inside an active, non-expired, non-revoked grant scope.**


~~***- Never ship API keys to the client. Groq/Gemini calls happen server-side in FastAPI only.**


~~***- Every record access (view/download/share/revoke) writes a row to \`access\_log\`.**


~~***- Share links use a long random token (not sequential IDs). Default expiry 7 days, revocable.**


~~***- Uploaded files stored in a private Supabase Storage bucket, served via signed URLs.**


~~***\#\# Coding conventions**


~~***- TypeScript strict. No \`any\` unless justified with a comment.**


~~***- Components small and single-purpose. Server components by default; "use client" only when needed.**


~~***- API calls go through \`lib/api.ts\`, never inline fetch in components.**


~~***- Python: type hints everywhere, Pydantic models for all request/response shapes.**


~~***- Comment the non-obvious logic: conflict-detection rules, share-grant authorization, NER→schema mapping.**


~~***\#\# UI principles (professional clinical aesthetic)sandbox.abdm.gov.in**


~~***- Calm, trustworthy palette: slate/white base, teal/blue primary, amber for warnings,**


~~  ***red ONLY for severe drug-conflict alerts. Generous whitespace. No gradients/neon.**


~~***- shadcn/ui components throughout (Card, Button, Dialog, Badge, Table, Tabs, Alert, Skeleton).**


~~***- Loading states (Skeleton) on every async view. Empty states with a clear next action.**


~~***- Fully responsive (patients are on phones). Accessible: labels, focus rings, ARIA on icon buttons.**


~~***- Severity encoded by color AND text, never color alone.**


~~***\#\# Reuse policy**


~~***backend/services/ocr.py, ner.py, llm.py, tts.py are adapted from MedInsight and may be**


~~***copied with light edits. Everything in the "new" list below is built fresh this phase.**

## Python version note
Backend venv is Python 3.11. Do NOT use PEP 695 generic syntax (class Foo[T]).
Use typing.TypeVar + Generic[T] instead.

## Supabase SQL note
Always include GRANT statements after CREATE TABLE + RLS. 
service_role, authenticated, and anon all need explicit GRANT 
even when service_role bypasses RLS.

## Groq model
Use llama-3.3-70b-versatile (llama-3.1-70b-versatile is decommissioned).

## Gemini SDK
Use the new google-genai SDK (from google import genai; genai.Client()).
NOT the deprecated google.generativeai package (EOL Nov 30 2025).
Model: gemini-3.5-flash (text + vision).

Manual steps summary across Phase 5A → 6B

After Phase 5A:


Add SARVAM_API_KEY to frontend/.env.local
Run SQL: ALTER TABLE profiles ADD COLUMN IF NOT EXISTS preferred_language text DEFAULT 'en-IN';
npm install next-intl sarvamai in frontend/
Test language switch in settings, test TTS button on a record with text summary


After Phase 5B:


Run python backend/scripts/seed_demo.py to seed demo data
Follow the exact deployment checklist Claude Code generates
Key: set USE_LOCAL_NER=false in Railway env vars
Update Supabase Auth redirect URLs to include Vercel domain
Update CORS in backend/main.py to include Vercel domain


After Phase 6A:


Run SQL for is_manually_verified columns on medications and lab_values
Test: select 3 records, create share link, open in incognito
Test: edit a wrong medication name, verify "✓ Verified" badge appears
Test: timeline month grouping, collapse, search


After Phase 6B (if done):


Run the pgvector index SQL
Test: ask "do I have any kidney issues?" — should cite the kidney report
Test: ask a question with no relevant records — should say so clearly