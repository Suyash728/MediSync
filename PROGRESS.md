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

# Phase 1 Patch — Summary
What changed (5 lines):

backend/services/ocr.py — new content-based routing: digital PDFs use PyMuPDF text layer; scanned PDFs rasterize pages via PyMuPDF and send to Gemini Vision; JPEG/PNG images go straight to Gemini Vision; Tesseract is now a last-resort fallback only when GEMINI_API_KEY is not set. Preprocessing (grayscale/contrast) is applied to Tesseract input only — Gemini receives the unprocessed color image.

backend/services/llm.py — added extract_structured_async(): sends raw OCR text to Groq in JSON mode (response_format: json_object) with a strict schema returning {record_type, document_date, source_facility, medications, lab_values, diagnoses, summary}; Gemini fallback uses response_mime_type: application/json; summary prompt is now clinical/factual, not casual.

backend/routers/upload.py — new pipeline: OCR → LLM structured extraction (primary) → NER merge (secondary, NER-only additions tagged low_confidence=True) → persist → determine status; introduces needs_review when extraction yields no medications AND no lab values.

backend/models/schemas.py + supabase/migrations/002_needs_review.sql — ProcessingStatus.needs_review added to the Python enum and the Postgres CHECK constraint.

frontend/ — types.ts union includes needs_review; RecordCard.tsx shows an amber warning for needs_review records instead of silently showing empty counts.

Manual steps
A — Run the new SQL migration
Paste supabase/migrations/002_needs_review.sql into the Supabase SQL Editor and execute it. This drops and re-creates the processing_status CHECK constraint to add needs_review.

B — Add GEMINI_API_KEY to your backend .env
The vision path requires it. Without it, Tesseract is the fallback (works for digital PDFs; poor on handwriting).


# In backend/.env:
GEMINI_API_KEY=AIza...
GEMINI_VISION_MODEL=gemini-1.5-flash   # optional, this is the default
C — No new Python packages needed
google-generativeai was already in requirements.txt (used by the Gemini fallback in the old llm.py). Groq JSON mode uses the existing groq package.

D — Test the patch
Upload a scanned PDF (e.g. a photographed prescription) — should now extract correctly via Gemini Vision
Upload a clear digital lab report PDF — should still use fast native text path
Upload a document with no structured content (e.g. a photo of text notes) — record should show "Needs review" amber warning in the dashboard
Check Supabase health_records table: processing_status should be done or needs_review, never stuck in processing
What to commit

git add backend/services/ocr.py backend/services/llm.py backend/routers/upload.py \
        backend/models/schemas.py backend/utils/config.py backend/.env.example \
        supabase/migrations/002_needs_review.sql \
        frontend/lib/types.ts frontend/components/RecordCard.tsx
git commit -m "Phase 1 patch: LLM-primary extraction, Gemini Vision OCR, needs_review status"

# END OF PHASE 1 Patch — SUMMARY 

# Phase 1 Patch Round 2 — Summary
What changed (5 lines):

backend/requirements.txt — removed google-generativeai==0.7.2 (EOL Nov 2025); added google-genai (new unified SDK, installed as 2.8.0); bumped httpx to 0.28.1 (pulled in transitively).

backend/services/ocr.py — _get_gemini_client() now creates genai.Client(api_key=...) from the new SDK; _gemini_vision_extract() signature changed from PIL Image to (image_bytes: bytes, mime_type: str) and uses types.Part.from_bytes(data=image_bytes, mime_type=mime_type) in the contents list; both PDF rasterization and image upload paths now pass raw bytes directly (no PIL conversion for the Gemini path).

backend/services/llm.py — removed the _GEMINI_MODEL constant and both old genai.configure() / GenerativeModel() patterns; added _get_gemini_client() singleton; _try_gemini_extraction_sync() and _try_gemini_summary_sync() now call client.models.generate_content(model=settings.gemini_model, contents=..., config=types.GenerateContentConfig(...)).

backend/utils/config.py — renamed gemini_vision_model → gemini_model (default "gemini-3.5-flash"); added extra="ignore" to SettingsConfigDict so stale env vars (like the old GEMINI_VISION_MODEL) don't crash startup.

backend/.env.example — GEMINI_VISION_MODEL → GEMINI_MODEL.

Manual steps
A — Install packages (if not done in this session)

cd backend && source .venv/bin/activate
pip uninstall google-generativeai -y
pip install google-genai
B — Update your .env file

# In backend/.env, rename the key:
# Old (remove):  GEMINI_VISION_MODEL=gemini-1.5-flash
# New (add):     GEMINI_MODEL=gemini-3.5-flash
The app won't crash if you leave the old key in — extra="ignore" swallows it — but the new key won't be active until you add it.

C — Verify

cd backend && source .venv/bin/activate
python -c "from services import ocr, llm; from utils.config import settings; print(settings.gemini_model)"
# Should print: gemini-3.5-flash
What to commit

git add backend/requirements.txt backend/utils/config.py \
        backend/services/ocr.py backend/services/llm.py \
        backend/.env.example
git commit -m "Phase 1 patch r2: migrate Gemini to google-genai SDK, use gemini-3.5-flash"

# END OF PHASE 1 Round 2 — SUMMARY 

# Phase 2 — Summary
What changed (5 lines):

/dashboard — replaced the minimal stub with a full health overview: 3 stat cards (total records, active medications, open drug-conflict alerts) fetched in parallel; active drug-conflict alerts surfaced above the fold with severity-coloured Alert components; recent 5 records; "View all N records" link to Timeline when record count > 5.

/timeline — new page with full reverse-chronological list of all records; collapsible filter panel (type dropdown, text search over title+summary, date-range from/to inputs); client-side filtering with active-filter counter badge; two empty states (no records, no matches); TimelineItem component with date column, coloured dot, type badge, one-line summary.

/record/[id] — new detail view: document preview (PDF <iframe> or <img> for images, inferred from file extension); signed-URL expiry note and reload button; LLM summary card; record metadata card; medications <Table> with Verified/Unverified confidence badges; lab values <Table> with full amber row highlight for abnormal results; Share button placeholder (disabled, wired Phase 4); Delete button with confirm dialog.

All pages — Skeleton loading on every async view; empty states with clear next action; fully responsive; all data fetched via lib/api.ts with Bearer token forwarded.

No backend changes — GET /records/ and GET /records/{id} already returned everything needed; the delete endpoint was already in place.

Manual steps
No new SQL, no new packages, no new env vars. Just run the servers:


npm run dev
Test this phase:

/dashboard — confirm stat cards show real counts after uploading a record
/timeline — confirm all records appear; try each filter; confirm "no matches" state
Click a timeline item → /record/[id] — confirm document preview, summary, tables load
Upload a lab report with abnormal values → open its detail page → confirm amber row highlighting
Click Delete on a record → confirm redirect to dashboard and record disappears
What to commit

git add frontend/app/(patient)/dashboard/page.tsx \
        frontend/app/(patient)/timeline/page.tsx \
        frontend/app/(patient)/record/[id]/page.tsx
git commit -m "Phase 2: dashboard stats + timeline feed + record detail view"

# END OF PHASE 2 — SUMMARY 

# Phase 2 patch (fix reference range extraction) — Summary
What changed (1 file, backend/services/llm.py):

_EXTRACTION_SCHEMA — reference_range field — changed from the vague hint "e.g. 70-100 or null" to an explicit instruction that the field is REQUIRED when a reference column is present in the document; tells the model to copy the value verbatim in any format (13.0 - 17.0, 150,000 - 400,000, > 4.5, < 100), and to emit null only when the document genuinely provides no range.

_EXTRACTION_SCHEMA — is_abnormal field — changed from true or false to a description that explains the three-state logic: true (out of range), false (in range), or null (no reference range provided — not false).

_EXTRACTION_RULES — replaced the old is_abnormal rule — the old rule only triggered on explicit document markers (H/L/HIGH/LOW). The new rule instructs the model to: (a) make reference_range mandatory whenever the column exists, (b) parse four common range formats and compare numerically, (c) fall back to explicit markers, and (d) use null rather than false when there is no range to compare against.

Manual steps
No SQL migrations, no package changes, no env vars. The backend server picks up the new prompt on restart.


# Restart the backend to load the new prompt strings:
# If already running via npm run dev, Ctrl+C and re-run:
npm run dev
Test:

Upload a lab report PDF with a Reference Range column → open /record/[id] → verify amber rows appear for out-of-range values and the reference_range column is populated.
Upload a lab report with no reference range column → verify is_abnormal is not blindly set to false (record detail page shows no amber rows, not phantom amber rows).
What to commit

git add backend/services/llm.py
git commit -m "Phase 2 patch: fix reference range extraction and is_abnormal null semantics"

# Phase 2 patch (reference_range fix) — Summary
Root cause: _EXTRACTION_SCHEMA was only passed to the Gemini fallback path. Groq never saw the schema, so it invented its own field names (reference_interval, ref_range, etc.). lab.get("reference_range") always returned None for those — reference ranges were read by the LLM but silently dropped at the mapping step.

What changed (6 files):

backend/services/llm.py — Schema is now prepended to the Groq prompt (schema → rules → document text). Cleaned up _EXTRACTION_SCHEMA to use unambiguous type hints (string or null, true) instead of verbose description strings (which could be mistaken for the values to produce). Added logger.debug of raw Groq JSON output and of parsed lab_values list.

backend/routers/upload.py — _build_lab_value_rows now tries four key aliases (reference_range, reference_interval, ref_range, normal_range) before falling back to None. is_abnormal is passed through as None when the LLM returns null instead of being silently coerced to False. NER-merged labs use is_abnormal: None (not False). Debug log of lab_value_rows added before DB insertion.

supabase/migrations/003_nullable_is_abnormal.sql — lab_values.is_abnormal column drops NOT NULL. Null now means "unknown" (no range to compare against), distinct from false ("confirmed within range").

backend/models/schemas.py — LabResult.is_abnormal: bool | None = None.

frontend/lib/types.ts — LabResult.is_abnormal: boolean | null.

frontend/app/(patient)/record/[id]/page.tsx — LabValueRow.is_abnormal: boolean | null. All three usages (className, count badge, status cell) use strict === true / === false. Status cell now has three states: Abnormal badge / Normal text / — (no range).

Manual steps
A — Run the SQL migration:


-- Paste into Supabase SQL Editor:
ALTER TABLE public.lab_values ALTER COLUMN is_abnormal DROP NOT NULL;
(Same content as supabase/migrations/003_nullable_is_abnormal.sql)

B — Enable DEBUG logging temporarily to see the raw LLM output:


# In backend/.env, add:
LOG_LEVEL=DEBUG
Then upload a lab report and tail the FastAPI logs. Look for lines prefixed [extraction].

C — Restart servers:


npm run dev
Test:

Upload a lab report with a Reference Range column → open /record/[id] → reference_range column should now be populated, amber rows appear for out-of-range values
Upload a report with no reference ranges → is_abnormal shows — (not "Normal") in the Status column
What to commit

git add backend/services/llm.py \
        backend/routers/upload.py \
        backend/models/schemas.py \
        supabase/migrations/003_nullable_is_abnormal.sql \
        frontend/lib/types.ts \
        frontend/app/(patient)/record/[id]/page.tsx
git commit -m "Phase 2 patch: fix reference_range extraction (schema now sent to Groq) and nullable is_abnormal"

# Phase 2 patch (reference range fallback) — Summary
What changed (6 files):

backend/data/reference_ranges.json (new) — 46 test definitions covering CBC (Hb/RBC/WBC/platelets/HCT/MCV/MCH/MCHC/differential), basic metabolic (glucose/HbA1c/creatinine/urea/uric acid), liver function (SGPT/SGOT/bilirubin/ALP/total protein/albumin), lipid profile (cholesterol/LDL/HDL/TG/VLDL), thyroid (TSH/fT3/fT4/T3/T4), electrolytes (Na/K/Cl/HCO3/Ca/P/Mg), plus Vit D, B12, Iron, Ferritin, CRP, ESR. Sex-stratified where clinically significant (Hb, RBC, HCT, creatinine, SGPT, uric acid, HDL, iron, ferritin, ESR). Each test has 10-15 aliases covering Indian lab report conventions ("S. Creatinine", "Total Leucocyte Count", "T. Bilirubin", etc.).

backend/services/reference_lookup.py (new) — lookup(test_name, sex) with exact alias match then difflib fuzzy (≥ 0.72 cutoff). compute_is_abnormal(value, range) parses five range formats (N–M, < N, > N, <= N, >= N) with an order-of-magnitude mismatch guard (returns None when value/midpoint ratio > 100× or < 0.01×) to avoid false positives when lab units differ from the reference range units.

backend/routers/upload.py — _build_lab_value_rows now sets reference_source = "lab_provided" when range comes from the document. New _apply_reference_fallback(rows) fills missing ranges from the lookup, sets reference_source = "standard", and computes is_abnormal via compute_is_abnormal for any row that has a range but no verdict (covers both fallback rows and lab-provided rows where the LLM returned is_abnormal=null).

supabase/migrations/004_reference_source.sql (new) — adds reference_source TEXT CHECK (...IN ('lab_provided', 'standard')) to lab_values.

frontend/app/(patient)/record/[id]/page.tsx — LabValueRow gains reference_source. The Reference Range column renders {range} [Std] when reference_source === "standard", where [Std] is a tiny bordered badge with title tooltip: "General reference range — not specific to this laboratory's equipment."

Manual steps
A — Run the SQL migration:


-- Paste into Supabase SQL Editor:
ALTER TABLE public.lab_values
    ADD COLUMN IF NOT EXISTS reference_source TEXT
        CHECK (reference_source IN ('lab_provided', 'standard'));
B — No new pip packages — difflib is Python stdlib, json and re already used.

C — Restart backend:


npm run dev
Test:

Upload a CBC lab report that has no Reference Range column → open /record/[id] → Hemoglobin row should show 12.0 - 17.0 [Std] with the Std badge
Upload a report WITH a reference column → ranges show with no badge
Hover the Std badge → tooltip should appear
A result with value outside the standard range should still show amber row + Abnormal badge
What to commit

git add backend/data/reference_ranges.json \
        backend/services/reference_lookup.py \
        backend/routers/upload.py \
        supabase/migrations/004_reference_source.sql \
        frontend/app/(patient)/record/[id]/page.tsx
git commit -m "Phase 2 patch: built-in reference range fallback with WHO/ICMR standard ranges"