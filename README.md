# MediSync — The Invisible Health Ledger

**A patient-controlled personal health record (PHR) platform that unifies fragmented medical documents into one structured, searchable, multilingual health timeline — with automatic drug-conflict detection and consent-based sharing.**

Built for CodeFusion 2026 by **Team Error404**.

🔗 **Live App:** https://medi-sync-livid.vercel.app

🔑 **Demo login:** `demo@medisync.app` / `Demo@2026`

---

## Table of Contents

1. [The Problem](#the-problem)
2. [Our Solution](#our-solution)
3. [Key Features](#key-features)
4. [Tech Stack](#tech-stack)
5. [System Architecture](#system-architecture)
6. [How It Works](#how-it-works)
7. [Innovation Highlights](#innovation-highlights)
8. [Setup & Installation](#setup--installation)
9. [Known Limitations & Honest Disclosures](#known-limitations--honest-disclosures)
10. [Roadmap](#roadmap)
11. [Team](#team)
12. [Acknowledgements & Attribution](#acknowledgements--attribution)
13. [License](#license)

---

## The Problem

A typical Indian patient's health history is scattered across paper prescriptions, lab PDFs emailed by diagnostic labs, discharge summaries photographed on a phone, and vaccination cards tucked into a drawer. Nobody — not the patient, not the next doctor they see — has the full picture. Critical information like drug interactions across prescriptions from different doctors is invisible. Most patients can't read their own lab reports without searching the internet. And language is a real barrier: most PHR tools are English-only, locking out a huge population that's more comfortable in their regional language.

## Our Solution

MediSync lets a patient photograph or upload **any** medical document — typed or handwritten, PDF or photo — and automatically:

- Extracts structured data (medications, lab values, diagnoses) using OCR + LLM extraction, with a vision-model fallback for handwritten and scanned content
- Generates a clear, factual, patient-friendly summary in the patient's **own selected Indian language**, with on-demand text-to-speech
- Checks new medications against the patient's full medication history for dangerous drug-drug interactions, with severity-ranked alerts
- Builds a chronological, searchable health timeline across all of the patient's records
- Lets the patient create **time-limited, revocable share links** so a clinician can view specific records — including the original document — without creating an account
- Lets the patient correct any AI extraction error directly, with a "Verified" marker, rather than blindly trusting AI output

The patient stays in control of their own data at every step — nothing is shared, summarized, or interpreted without their initiation.

## Key Features

### 📄 Universal document ingestion
Upload a photo, scan, or PDF of any medical document. The pipeline automatically decides the right extraction path: native text extraction for typed PDFs, and a vision-model path for handwritten prescriptions or photographed scans where OCR alone fails.

### 🧠 AI-structured extraction, not just text dump
Every document is parsed into medications, lab values (with reference ranges), diagnoses, and a clinical summary — branching by document type (prescription, lab report, discharge summary, imaging, vaccination) so the language and structure actually fit what was uploaded.

### 🌐 11 Indian languages, end to end
English, Hindi, Tamil, Bengali, Telugu, Kannada, Malayalam, Marathi, Gujarati, Punjabi, and Odia — covering the app UI, AI-generated summaries, drug conflict explanations, and on-demand audio narration (via Sarvam AI's Bulbul TTS model). Set once at signup, changeable anytime in Settings.

### 💊 Drug-conflict detection
Every new medication is checked against the patient's active medication list using a curated clinically-significant interaction dataset. Conflicts are severity-ranked (minor/moderate/major), explained in plain language in the patient's own language, and surfaced immediately via toast notification and a dedicated Alerts page.

### 🔗 Granular, time-limited sharing
Patients select one or more records, set an expiry, optionally label a recipient, and generate a read-only link. The clinician view shows the **original document** alongside the AI summary — not just a text blurb. Every link can be revoked instantly, and a full access log shows who viewed what, when.

### ✏️ Human-in-the-loop correction
AI extraction can be wrong. Rather than hide that risk, every extracted medication and lab value can be directly edited by the patient, with a "✓ Verified" badge marking human-confirmed data — building real trust instead of false confidence.

### 📱 Installable PWA
Add to home screen on iPhone, Android, or desktop (Chrome/Edge/Safari) for an app-like experience with offline app-shell loading.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui |
| Backend | FastAPI (Python 3.11/3.12), Uvicorn |
| Database | Supabase (PostgreSQL + pgvector, Row-Level Security) |
| Auth | Supabase Auth |
| File storage | Supabase Storage (private buckets, signed URLs) |
| OCR | PyMuPDF (native text), Tesseract (fallback) |
| Vision / scanned & handwritten docs | Google Gemini Vision (`gemini-3.5-flash`, `google-genai` SDK) |
| LLM (structured extraction, summaries, conflict explanations) | Groq (`llama-3.3-70b-versatile`) |
| Secondary NER signal | BioBERT (`dmis-lab/biobert-base-cased-v1.2`) |
| Drug interaction detection | Curated clinical dataset + LLM-generated explanations |
| Internationalization | next-intl (11 Indian languages) |
| Text-to-speech | Sarvam AI Bulbul v3 (speaker: Suhani) |
| Deployment | Vercel (frontend), Railway (backend) |
| CI/CD | Native GitHub auto-deploy on Vercel + Railway (push to `main`) |

## System Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Next.js PWA    │ ◄─────► │   FastAPI Backend │ ◄─────► │    Supabase      │
│  (Vercel, React)  │  REST   │   (Railway)        │         │  Postgres + RLS   │
│                   │         │                    │         │  Auth + Storage   │
└─────────────────┘         └──────────────────┘         └─────────────────┘
                                      │
                  ┌───────────────────┼───────────────────┐
                  ▼                   ▼                   ▼
           ┌─────────────┐   ┌────────────────┐   ┌──────────────┐
           │  Groq LLM    │   │  Gemini Vision  │   │  Sarvam TTS   │
           │ (extraction, │   │ (handwritten /   │   │ (audio       │
           │  summaries,  │   │  scanned docs)   │   │  narration)   │
           │  conflicts)  │   └────────────────┘   └──────────────┘
           └─────────────┘
```

**Document processing pipeline:**

```
Upload → Content-type decision
            ├─ Typed PDF → native text extraction (PyMuPDF)
            └─ Image / scanned PDF → Gemini Vision extraction
                        ↓
         LLM structured extraction (Groq) — JSON: medications,
         lab values, diagnoses, document-type-aware summary
                        ↓
         Reference range fallback (document-provided → else
         curated standard ranges, clearly labeled by source)
                        ↓
         Drug-conflict check against active medications
                        ↓
         Persist to Supabase (RLS-scoped to the patient)
                        ↓
         Patient can review, correct (✓ Verified), share, or
         listen via on-demand TTS — all in their chosen language
```

## How It Works — A Walkthrough

1. **Sign up** → choose a preferred language from 11 Indian languages in the onboarding modal (changeable anytime in Settings).
2. **Upload a document** — a photo of a prescription, a lab report PDF, a discharge summary, anything.
3. The system extracts structured data and generates a summary **in the chosen language**, tailored to the document type.
4. If the new document introduces a medication that conflicts with an existing one, an alert fires immediately with severity and a plain-language explanation.
5. The document appears on the **Timeline**, alongside all previous records, in chronological order.
6. The patient can listen to the summary via the **TTS button**, correct any wrong extraction with the inline edit tool, or **share** the record (or several at once) with a doctor via a time-limited link.
7. The doctor opens the link — no account needed — and sees the **original document** plus the structured summary, read-only, until the link expires or is revoked.

## Innovation Highlights

- **Source-transparent reference ranges.** Most PHR tools either silently fail to flag abnormal values when a lab doesn't print a reference range, or quietly apply a "standard" range without telling the patient. MediSync does both correctly: it uses the document's own range when present, falls back to a curated standard range when absent, and **visibly labels which one is being used** — a real clinical-safety distinction most consumer apps skip.
- **Document-type-aware AI summaries.** A prescription summary and a lab report summary read completely differently — by design — instead of every document being forced into one generic "summary" template.
- **Deterministic interaction matching, generative explanation.** Drug conflicts are matched against a curated, auditable interaction dataset (not an LLM guessing about drug pairs), while the LLM is only used to explain the match in plain, localized language — keeping the safety-critical matching deterministic while the communication stays human-friendly.
- **Manual correction over blind trust.** Rather than presenting AI-extracted medical data as fact, MediSync gives the patient direct editing power with a verified-status indicator — addressing AI hallucination risk honestly instead of hiding it.
- **True multilingual depth, not just UI translation.** Language support extends through the AI-generated content itself (summaries, conflict explanations) and audio narration, not just static interface text.

## Setup & Installation

```bash
git clone https://github.com/Suyash728/MediSync.git
cd MediSync

# Backend
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in Supabase, Groq, Gemini keys

# Frontend
cd ../frontend
npm install
cp .env.local.example .env.local   # fill in Supabase + backend URL + Sarvam key

# From project root
npm run dev   # runs both servers concurrently
```

Required environment variables are documented in `backend/.env.example` and `frontend/.env.local.example`.

To seed demo data into your own Supabase instance:
```bash
python backend/scripts/seed_demo.py
```

## Known Limitations & Honest Disclosures

We believe transparency about limitations is part of building a trustworthy health product.

- **Handwriting OCR accuracy.** Even with a vision-model fallback, doctors' handwriting remains genuinely difficult to parse with full accuracy. We mitigate this with the manual-edit/Verified flow rather than claiming perfect extraction.
- **Drug interaction coverage.** Our interaction dataset covers ~100 clinically significant pairs across major drug classes, curated for demonstration. A production deployment would integrate a licensed clinical decision support API (e.g., First Databank, Multum) for comprehensive coverage.
- **ABDM/ABHA integration.** We registered on the ABDM Sandbox to pursue Milestone 1 (ABHA creation/verification) integration. Despite multiple registration attempts and direct correspondence with NHA's integration support team, sandbox approval was still pending at submission time — a known multi-week process even under normal circumstances. The app is built to degrade gracefully without ABHA: all core functionality works fully independent of ABDM, and ABHA number storage/verification is a planned drop-in addition once sandbox access is granted.
- **AI-generated translations.** Our 11 language UI translations were generated with LLM assistance and may benefit from native-speaker review before a production launch.

## Roadmap

- **ABDM M1/M3 integration** once sandbox access is approved
- **RAG-based "Ask your records"** — natural-language Q&A grounded strictly in the patient's own uploaded records (pgvector-based retrieval already scaffolded)
- **Licensed clinical decision support API** for comprehensive drug interaction coverage
- **Native mobile app** (React Native) for the patient-facing experience, complementing the web clinician view
- **Family/dependent profiles** for managing a household's records under one account

## Team

**Team Error404**
- Suyash Kerkar — Full-stack development, AI pipeline, deployment
- Arya Jadhav — Team lead

Built on top of and extending our earlier project, **MedInsight** (https://github.com/Suyash728/MedInsight) — a multilingual medical report summarizer that served as the foundation for MediSync's OCR/NER/LLM pipeline.

## Acknowledgements & Attribution

- Document parsing and summarization pipeline adapted from our own prior project, [MedInsight](https://github.com/Suyash728/MedInsight)
- Drug interaction and reference range datasets independently curated for this project
- All third-party APIs and models used are disclosed in the [Tech Stack](#tech-stack) section above

## License

This project is licensed under the **PolyForm Noncommercial License 1.0.0** — free to use, study, and build upon for personal, educational, research, and noncommercial purposes (this explicitly includes evaluation by hackathon judges and educational institutions). Commercial use requires separate permission. See [`LICENSE`](./LICENSE) for full terms.
