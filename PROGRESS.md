Phase 0 — Summary
What changed (5 lines):

Bootstrapped frontend/ with Next.js 14 (App Router, TypeScript, Tailwind) and installed all shadcn/ui dependencies + Supabase client packages.
Implemented the full clinical theme — teal primary, amber warning, red destructive — via CSS variables in globals.css and tailwind.config.ts.
Created all 14 shadcn/ui components by hand (components/ui/), plus AppShell (sticky nav with logo, links, user avatar dropdown, mobile hamburger).
Scaffolded every route in the CLAUDE.md layout with Skeleton-state stubs: landing page, login/signup, all patient routes, clinician shared view.
Built out the FastAPI backend with CORS, /health, typed Pydantic schemas, 6 routers (all return 501 stubs), 7 service stubs, pydantic-settings config, and requirements.txt.
Manual steps
A — Install root + frontend packages (already done for you in this session, but do this after cloning):

npm install # root (installs concurrently)
cd frontend && npm install && cd ..
B — Python virtual environment (you must do this):

cd backend
python3 -m venv .venv
source .venv/bin/activate # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ..
C — Create env files:

cp frontend/.env.example frontend/.env.local
cp backend/.env.example backend/.env
Fill in NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY (frontend) and SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY, GROQ_API_KEY (backend).

D — Test the dev server:

npm run dev
Frontend → http://localhost:3000 (landing page, all routes accessible as stubs)
Backend → http://localhost:8000/health → {"status":"ok"} and http://localhost:8000/docs
E — Things to verify manually:
Landing page renders (teal logo, feature cards, CTA buttons)
/dashboard renders (AppShell nav, Skeleton cards)
/login and /signup show placeholder cards
/shared/test-token shows the read-only clinician stub
What to commit

git init
git add .
git commit -m "Phase 0: scaffold Next.js 14 + FastAPI + clinical theme + all route stubs"

# END OF PHASE 0 — SUMMARY 

Phase 1 — Summary
What changed (5 lines):

SQL schema (supabase/migrations/001_schema.sql): 7 tables with RLS ON — profiles, health_records (with vector(384) column), medications, lab_values, drug_conflicts, share_grants, access_log; auto-creates a profile row via trigger on signup.
Auth (frontend): Real email/password login + signup forms with Supabase; middleware protects all patient routes and redirects authenticated users away from /login/signup.
Services (adapted from MedInsight): ocr.py (PyMuPDF + Tesseract), ner.py (BioBERT + regex, with map_ner_to_schema() documented for live Q&A), llm.py (AsyncGroq + Gemini fallback, patient-facing summary), tts.py (Sarvam AI Bulbul:v3).
Upload pipeline (POST /upload): Full OCR → NER → LLM → DB flow; writes health_records, medications[], lab_values[] rows; marks records failed on error instead of hanging.
Upload UI: Drag-and-drop UploadZone with step-by-step progress, RecordCard with entity counts, dashboard client page that fetches/prepends records without reload.
Manual steps
A — Supabase setup (required before first run)
1. Enable the pgvector extension in the Supabase SQL Editor first:


CREATE EXTENSION IF NOT EXISTS "vector";
2. Run the full schema — paste supabase/migrations/001_schema.sql into the SQL Editor and execute it.

3. Create the private Storage bucket:

Dashboard → Storage → New bucket
Name: medical-docs
Set Private (uncheck "Public bucket")
Click Create
4. Disable email confirmation (for hackathon):

Dashboard → Authentication → Settings → Email → disable "Enable email confirmations"
B — Environment variables

# Frontend
cp frontend/.env.example frontend/.env.local
# Fill in: NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_BACKEND_URL

# Backend
cp backend/.env.example backend/.env
# Fill in: SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY, GROQ_API_KEY
C — Install tesseract (system package, not pip)

# Fedora/RHEL
sudo dnf install tesseract

# Ubuntu/Debian
sudo apt install tesseract-ocr
D — Python packages (if not already done)

cd backend && source .venv/bin/activate && pip install -r requirements.txt
E — Start dev servers

npm run dev   # from project root
F — Test this phase
Go to http://localhost:3000/signup → create an account
Should redirect to /dashboard
Upload a PDF prescription or lab report
Watch the processing steps label advance
On success: RecordCard appears with medication/lab counts and summary
Check Supabase table editor: confirm rows in health_records, medications, lab_values
Check GET http://localhost:8000/health → {"status":"ok"}
Check GET http://localhost:8000/docs → Swagger UI
What to commit

git add .
git commit -m "Phase 1: auth + Supabase schema + OCR/NER/LLM pipeline + upload UI"

# END OF PHASE 1 — SUMMARY 