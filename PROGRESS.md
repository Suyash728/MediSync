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

# Phase 2 patch (summary pipeline fix) — Summary
Root cause: The clinical summary was generated at step 7 (inside the extraction try-block), before step 8 ran _build_lab_value_rows and _apply_reference_fallback. So the summary LLM received the raw extraction dict with empty reference_range fields, producing "no abnormal values — ranges not provided" even though the fallback later resolved ranges and flagged abnormal results in the database.

What changed (2 files, backend only):

backend/routers/upload.py — Removed summary generation from inside the try-block. Added step 7.5 between step 8 (reference fallback) and step 9 (DB insert): summarise_record_async(raw_text, extracted, lab_value_rows) — now passes the fully resolved rows. Summary failure is caught separately (non-fatal); the record is still saved without a summary rather than marked failed.

backend/services/llm.py — Four changes:

_SUMMARY_INSTRUCTIONS replaced by _SUMMARY_PREAMBLE + _SUMMARY_MID (split so the resolved lab block can be injected between them via concatenation).
New _format_resolved_labs(lab_rows) builds a bullet-point block like • Hemoglobin: 9.8 g/dL, ref 13.0 - 17.0 (standard reference range) — ABNORMAL LOW for each lab value.
New _compute_direction(value_str, range_str) returns "HIGH" / "LOW" / "" by re-parsing the same range formats as reference_lookup.compute_is_abnormal.
summarise_record_async and _build_summary_prompt updated to accept resolved_lab_values: list[dict] | None; raw lab_values is stripped from the entities block passed to the LLM (the resolved list supersedes it). _fallback_summary also updated to prefer resolved labs.
Manual steps
No SQL migrations, no package changes, no env vars. Restart the backend:


npm run dev
Test — CBC report with no reference range column:

Upload a CBC report where the document has no Reference Range column
Summary should now say: "Hemoglobin 9.8 g/dL is LOW (based on standard reference range 13.0–17.0 g/dL)" rather than "no abnormal values"
The lab values table in /record/[id] should show the amber row + Std badge + Abnormal status (this was fixed in the previous patch; now the summary catches up)
What to commit

git add backend/services/llm.py \
        backend/routers/upload.py
git commit -m "Phase 2 patch: generate summary after reference fallback so abnormal callouts use resolved ranges"

# Phase 2 patch (normal-values confirmation) — Summary
What the problem was: The summary only listed abnormal findings and was silent about all other lab values, giving an incomplete picture. A patient seeing "Hemoglobin is LOW" with no further mention of the remaining 7 CBC tests has no way to know those results were fine.

What changed (1 file, backend only):

backend/services/llm.py — three edits:

_SUMMARY_PREAMBLE — added a fifth bullet to the lab-values instruction block. The LLM is told to close the lab section with exactly one sentence listing the tests that were within range (is_abnormal=false), using one of three formats: mixed (some abnormal, some normal), all-normal, or all-abnormal (omit entirely). Test names only — no values or units in the normal-confirmation line.

_fallback_summary — mirrors the same logic deterministically. Computes normal = [lv for lv in labs if lv.get("is_abnormal") is False] and appends the appropriate closing sentence (or nothing, when all are abnormal).

_MAX_SUMMARY_TOKENS — raised from 400 → 500 to give the extra closing sentence room to breathe on reports with many normal tests.

Expected output for a CBC with Hb=LOW, rest normal:

Hemoglobin 9.8 g/dL is LOW (based on standard reference range 13.0–17.0 g/dL for adult male).
All other measured parameters — WBC, Platelet Count, MCV, MCH, MCHC, RBC — are within the reference range.

Manual steps
No migrations, no package changes, no env vars. Restart backend:


cd backend && uvicorn main:app --reload
Test — upload a CBC where only Hb is abnormal:

Summary should end with the normal-confirmation sentence listing the remaining test names.
Test — upload a report where everything is normal:

Summary should say "No abnormal lab values identified." then "All measured parameters are within the reference range — [names]."
Test — upload a report where multiple values are abnormal and none are normal (e.g., a severely abnormal panel):

Normal-confirmation sentence should be completely absent.
What to commit

git add backend/services/llm.py
git commit -m "Phase 2 patch: add normal-values closing confirmation to clinical summary"

# Phase 3 — Summary
What was built (8 new files, 7 modified):

New backend files
backend/data/drug_interactions.csv — 100 curated DDI pairs across anticoagulants, antibiotics, psychiatric, cardiovascular, diabetes, immunosuppressant, and analgesic classes. All 14 required pairs included.
backend/data/drug_name_aliases.json — 170+ brand-name mappings (Indian brands first: Crocin→Paracetamol, Ecosprin→Aspirin, Glycomet→Metformin, etc.) + international names.
backend/services/conflict.py — Full detection engine. Loads CSV at import; normalises drug names via alias → fuzzy match → Groq confirmation (0.65–0.80 confidence range); O(1) DDI lookup; LLM-generates patient-facing explanations only after a CSV match is confirmed (the determinism/LLM boundary is commented clearly).
supabase/migrations/005_drug_conflicts.sql — drug_conflicts table with minor/moderate/major severity, RLS (patients see only their own), and GRANT statements.
Modified backend files
backend/routers/conflicts.py — Replaced stub: GET /conflicts/, POST /conflicts/recheck, POST /conflicts/{id}/acknowledge.
backend/routers/upload.py — Step 11b: runs conflict_svc.run_conflict_check(patient_id) after medications are persisted; non-fatal; returns new_conflicts in the response.
backend/models/schemas.py — Added ConflictSeverity enum (minor/moderate/major); updated DrugConflict model to match the actual DB schema (mechanism, description, explanation).
New/modified frontend files
frontend/app/(patient)/alerts/page.tsx — Full implementation: active alerts (major→moderate→minor), Acknowledge button, collapsible Reviewed section, Re-run check button.
frontend/lib/types.ts — Added ConflictSeverity type; updated DrugConflict interface.
frontend/lib/api.ts — Added conflictsApi with list(), recheck(), acknowledge().
frontend/components/UploadZone.tsx — Fires toast.warning("⚠️ Drug interaction detected: A + B") for every major conflict in the upload response.
frontend/app/(patient)/dashboard/page.tsx — Fixed severity mapping for minor/moderate/major; dashboard conflict widget now shows explanation ?? description; new conflicts from upload prepend to the widget; "View all" link to /alerts.
Manual steps
1. Run the SQL migration (Supabase dashboard → SQL editor, or CLI):


# Via CLI:
supabase db push
# Or paste supabase/migrations/005_drug_conflicts.sql into the SQL editor
2. Restart the backend:


cd backend && uvicorn main:app --reload
3. Test:

Upload two documents that contain interacting drugs (e.g., a Warfarin prescription + an Aspirin prescription for the same patient).
After the second upload: a red toast should appear: ⚠️ Drug interaction detected: Aspirin + Warfarin.
Dashboard widget should show the conflict with a major/destructive badge.
Navigate to /alerts — the conflict appears under Active Alerts with mechanism, explanation, and Acknowledge button.
Click Acknowledge → conflict moves to Reviewed section.
Click Re-run check → "No new interactions detected."
What to commit

git add backend/data/drug_interactions.csv \
        backend/data/drug_name_aliases.json \
        backend/services/conflict.py \
        backend/routers/conflicts.py \
        backend/routers/upload.py \
        backend/models/schemas.py \
        supabase/migrations/005_drug_conflicts.sql \
        frontend/app/\(patient\)/alerts/page.tsx \
        frontend/lib/types.ts \
        frontend/lib/api.ts \
        frontend/components/UploadZone.tsx \
        frontend/app/\(patient\)/dashboard/page.tsx

git commit -m "Phase 3: drug-conflict detection engine, /alerts page, and dashboard widget"

# Phase 3 patch — Summary
Root causes confirmed:

BUG 1 — The conflict check call was present in step 11b, but the gate condition final_status == ProcessingStatus.done.value was unnecessary and fragile. Replaced with not error_msg — simpler, directly expresses intent, and can't be broken by enum serialisation differences.

BUG 2 — _strip_dose_route only removed dose numbers and route keywords. "Sodium" in "Warfarin Sodium" is a counter-ion salt suffix, not a route word — it was never stripped. The cleaned string "warfarin sodium" had difflib ratio ≈ 0.70 against "warfarin", below the 0.80 confident threshold, so it fell into the unreliable Groq-confirmation path.

What changed (3 files):

backend/services/conflict.py:

Added _SALT_RE — strips 25 pharmaceutical salt/counter-ion suffixes: sodium, hydrochloride, hcl, bisulfate, carbonate, tartrate, maleate, citrate, gluconate, etc.
Extended _ROUTE_RE — added plural forms (tablets?, capsules?), "caps", and scheduling abbreviations (od, bd, tds, qid).
Renamed _strip_dose_route → _clean_drug_name with the new three-pass order: lowercase → salt strip → dose strip → route strip → collapse whitespace.
Added step 0 in normalise_drug_name: direct exact set lookup against _DDI_DRUG_NAMES after cleaning. "Warfarin Sodium" → _clean_drug_name → "warfarin" → in _DDI_DRUG_NAMES → returns immediately, no fuzzy needed.
backend/data/drug_name_aliases.json:

Added "warfarin sodium" → Warfarin (belt-and-suspenders backup).
Added "aspirin 81" → Aspirin (handles bare-number dose form without unit).
backend/routers/upload.py:

Changed if medications_rows and final_status == ProcessingStatus.done.value: to if medications_rows and not error_msg:.
Manual steps
Restart the backend (no migrations, no npm changes):


cd backend && uvicorn main:app --reload
Test the exact pair:

Upload a Warfarin prescription for a patient (watch logs: "conflict check start" then "< 2 medications, skipping").
Upload an Aspirin prescription for the same patient.
Backend logs should show:

conflict: 'Warfarin Sodium' → 'warfarin'
conflict: 'Aspirin' → 'aspirin'
conflict: NEW MAJOR — Aspirin + Warfarin
conflict: inserted 1 new conflict row(s) for patient ...
A red toast fires: ⚠️ Drug interaction detected: Aspirin + Warfarin.
/alerts page shows the conflict under Active Alerts with a red Major badge.
What to commit

git add backend/services/conflict.py \
        backend/data/drug_name_aliases.json \
        backend/routers/upload.py

git commit -m "Phase 3 patch: fix salt-suffix normalization and simplify conflict-check gate"

# Phase 3 patch — Schema/insert reconciliation summary
Root cause: The committed 005_drug_conflicts.sql never had a recommendation column, but the live Supabase DB likely does (from a draft migration that diverged). The _generate_explanation function was also putting both "what happens" and "what to do" into a single explanation blob — never populating a separate recommendation key.

Final column set — what each stores:

Column	Source	NOT NULL?
description	CSV description field	No
mechanism	CSV mechanism field	No
explanation	LLM — what this interaction means / what could happen	No
recommendation	LLM — what the patient should do (new, separate LLM line)	No
What changed (6 files):

supabase/migrations/006_drug_conflicts_add_recommendation.sql — ADD COLUMN IF NOT EXISTS recommendation text + DROP NOT NULL (idempotent, handles both fresh and broken-NOT NULL-live-DB states)
backend/services/conflict.py — _generate_explanation now returns tuple[str, str]; prompts LLM with EXPLANATION: / RECOMMENDATION: labels; parses output; fallback is (description, generic_advice)
backend/models/schemas.py — DrugConflict.recommendation: str | None = None
frontend/lib/types.ts — DrugConflict.recommendation: string | null
frontend/app/(patient)/dashboard/page.tsx — local DrugConflict interface gets recommendation: string | null
frontend/app/(patient)/alerts/page.tsx — ConflictCard renders explanation and recommendation as separate paragraphs; "Action: " prefix on the recommendation line
SQL to run in Supabase
Paste this in the SQL Editor of your Supabase project:


ALTER TABLE public.drug_conflicts
    ADD COLUMN IF NOT EXISTS recommendation text;

ALTER TABLE public.drug_conflicts
    ALTER COLUMN recommendation DROP NOT NULL;
Manual steps

# Restart the backend (no pip changes needed)
cd backend && uvicorn main:app --reload

# Restart the frontend
cd frontend && npm run dev
After running the migration, upload a prescription to trigger a new conflict check. The drug_conflicts row will now have explanation and recommendation as separate columns. On /alerts the card will show the explanation paragraph first, then "Action: ..." on a second line.

What to commit

git add supabase/migrations/006_drug_conflicts_add_recommendation.sql \
        backend/services/conflict.py \
        backend/models/schemas.py \
        frontend/lib/types.ts \
        frontend/app/(patient)/dashboard/page.tsx \
        frontend/app/(patient)/alerts/page.tsx

git commit -m "Phase 3 patch: split explanation/recommendation columns in drug_conflicts"