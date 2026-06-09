# MediSync — The Invisible Health Ledger

Patient-controlled medical records platform. Upload any medical document, get a
structured timeline, automatic drug-conflict detection, and secure time-limited
sharing with clinicians.

Built for **CodeFusion 2026** (Round 3 implementation).

---

## Prerequisites

| Tool | Version |
|------|---------|
| Node.js | ≥ 20 |
| Python | 3.11+ |
| npm | ≥ 9 |

---

## Quick start

### 1. Clone and install

```bash
# Root dependencies (concurrently)
npm install

# Frontend dependencies
cd frontend && npm install && cd ..

# Backend: create a virtual environment
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ..
```

### 2. Configure environment variables

```bash
# Frontend
cp frontend/.env.example frontend/.env.local

# Backend
cp backend/.env.example backend/.env
```

Fill in the values — see the comments in each `.env.example` file.

Required variables before first run:

| File | Variable | Where to get it |
|------|----------|-----------------|
| `frontend/.env.local` | `NEXT_PUBLIC_SUPABASE_URL` | Supabase project → Settings → API |
| `frontend/.env.local` | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase project → Settings → API |
| `backend/.env` | `SUPABASE_URL` | same as above |
| `backend/.env` | `SUPABASE_SERVICE_KEY` | Supabase project → Settings → API → service_role |
| `backend/.env` | `SUPABASE_ANON_KEY` | same as anon key |
| `backend/.env` | `GROQ_API_KEY` | console.groq.com |

### 3. Run Supabase migrations

```bash
# Apply the SQL schema (Phase 1 will add the migration files)
# supabase db push  (or run the SQL manually in the Supabase SQL editor)
```

### 4. Start both servers

```bash
npm run dev
```

This starts:
- `[backend]` FastAPI on http://localhost:8000 (coloured cyan)
- `[frontend]` Next.js on http://localhost:3000 (coloured green)

Visit http://localhost:3000 to see the landing page.

---

## DrugBank Open Data

The drug-interaction engine (Phase 4) requires the DrugBank Open Data CSV.

1. Register at https://go.drugbank.com/releases/latest (free for non-commercial use)
2. Download `drugbank_open_structures.csv`
3. Place it in `backend/data/drugbank_interactions.csv`

This file is `.gitignore`d (too large for the repo).

---

## Project structure

```
medisync/
├── frontend/           Next.js 14 App Router
│   ├── app/
│   │   ├── (auth)/     login, signup
│   │   ├── (patient)/  dashboard, timeline, record/[id], share, alerts, settings
│   │   └── (clinician)/shared/[token]   read-only clinician view
│   ├── components/ui/  shadcn/ui components
│   ├── components/     AppShell + feature components
│   └── lib/            api.ts, supabase.ts, types.ts, utils.ts
├── backend/            FastAPI (Python 3.11+)
│   ├── main.py
│   ├── routers/        upload, process, records, conflicts, share, abha
│   ├── services/       ocr, ner, llm, tts, conflict, rag, abha
│   ├── models/         schemas.py (Pydantic v2)
│   └── utils/          config.py
└── supabase/
    └── migrations/     SQL schema + RLS policies
```

---

## Security model

- **Row-Level Security** is ON for every Supabase table — patients see only their own rows.
- Share recipients see only records inside an active, non-expired, non-revoked grant.
- Groq/Gemini API keys live in `backend/.env` and are never sent to the browser.
- Every record access (view / download / share / revoke) writes a row to `access_log`.
- Share links use a 32-byte random hex token (not sequential IDs). Default expiry 7 days.
- Uploaded files are in a **private** Supabase Storage bucket, served via signed URLs.
