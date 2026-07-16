"""
POST /upload — Document ingestion pipeline (refactored Phase 1 patch).

Pipeline (in order):
  1.  Verify JWT → get patient_id
  2.  Validate file type (PDF / JPEG / PNG) and size (≤ 20 MB)
  3.  Save raw bytes to a temp file → upload to Supabase Storage
  4.  Create health_records row (status=processing)
  5.  OCR → raw_text
        PDF with native text layer → PyMuPDF
        Scanned PDF / images → Gemini Vision (Tesseract fallback)
  6.  LLM structured extraction (PRIMARY) → extract_structured_async()
        Groq llama-3.3-70b-versatile in JSON mode → typed dict
        {medications, lab_values, diagnoses, document_date, summary, …}
  7.  BioBERT NER (SECONDARY) → extract_entities_async()
        Merge NER-found drugs / lab values not already in LLM output;
        those additions are flagged low_confidence=True.
  8.  Map merged extraction dict → medications[] and lab_values[] DB rows
  9.  Insert extracted rows
  10. Determine final status:
        failed       — pipeline error
        needs_review — no medications AND no lab values found (empty extraction)
        done         — at least one medication or lab value extracted
  11. Update health_records row (status, summary, raw_text)
  12. Write access_log row (audit trail)
  13. Return the full record + extracted rows

Error handling: any unhandled exception in steps 5–9 marks the record as
'failed' with processing_error populated.  We never leave a record stuck in
'processing' state permanently.

Async notes:
  - OCR (PyMuPDF + Gemini Vision / Tesseract) is CPU-bound/blocking → to_thread().
  - NER (BioBERT model inference) is CPU-bound → to_thread().
  - LLM extraction (AsyncGroq) is I/O-bound → truly async.
"""

import logging
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, status

from models.schemas import ProcessingStatus, RecordType
from services import ocr, ner, llm, reference_lookup
from services import conflict as conflict_svc
from services import rag as rag_svc
from utils.access import check_access
from utils.auth import get_current_patient
from utils.db import get_supabase
from utils.storage import upload_file, ALLOWED_TYPES

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024   # 20 MB


@router.post(
    "/",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process a medical document",
)
async def upload_document(
    file:          UploadFile,
    record_type:   str = Form(...),
    title:         str = Form(...),
    document_date: str = Form(...),
    facility:      str = Form(""),
    doctor:        str = Form(""),
    patient_id:    str = Depends(get_current_patient),
) -> dict:
    """Accept a medical document, run the full parsing pipeline, persist results.

    Authorization: Bearer <supabase_access_token>
    Body: multipart/form-data (file + metadata fields above)
    Returns: The newly-created health_record with extracted medications and lab values.
    """

    # ── 1. Validate inputs ────────────────────────────────────────────────────

    if record_type not in [r.value for r in RecordType]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid record_type. Choose from: {[r.value for r in RecordType]}",
        )

    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{content_type}'. Allowed: PDF, JPEG, PNG.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 20 MB limit.",
        )

    # ── 2. Upload to Supabase Storage ─────────────────────────────────────────

    record_id = str(uuid.uuid4())
    supabase  = get_supabase()

    try:
        storage_path = upload_file(
            file_bytes=file_bytes,
            patient_id=patient_id,
            record_id=record_id,
            content_type=content_type,
        )
    except Exception as exc:
        logger.error("Storage upload failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to store file. Please try again.",
        )

    # ── 3. Create health_records row (status=processing) ─────────────────────

    record_row = {
        "id":                record_id,
        "patient_id":        patient_id,
        "record_type":       record_type,
        "title":             title,
        "document_date":     document_date or None,
        "facility":          facility or None,
        "doctor":            doctor or None,
        "file_path":         storage_path,
        "processing_status": ProcessingStatus.processing.value,
    }
    supabase.table("health_records").insert(record_row).execute()

    # ── 4–9. Pipeline ─────────────────────────────────────────────────────────
    # Everything inside the try block is wrapped so failures mark the record
    # as 'failed' instead of leaving it in 'processing' forever.

    raw_text:       str  = ""
    extracted:      dict = {}
    summary:        str  = ""
    error_msg:      str | None = None
    new_conflicts:  list[dict] = []

    suffix = Path(file.filename or "doc").suffix or ALLOWED_TYPES.get(content_type, ".bin")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        # ── 4. OCR ───────────────────────────────────────────────────────────
        # Enhanced routing: native PDF text → Gemini Vision → Tesseract.
        # The decision is made inside ocr.extract_text(); we just call it here.
        logger.info("[%s] OCR start (type=%s)", record_id[:8], content_type)
        raw_text = await ocr.extract_text_async(tmp_path, content_type)
        logger.info("[%s] OCR done: %d chars", record_id[:8], len(raw_text))

        # ── 5. LLM structured extraction (PRIMARY) ───────────────────────────
        # Groq receives the raw OCR text and returns a structured JSON dict.
        # This replaces BioBERT NER as the primary data source because LLMs
        # understand clinical context and can extract dosage/frequency/abnormality
        # without needing separate regex passes over a context window.
        logger.info("[%s] LLM extraction start", record_id[:8])
        extracted = await llm.extract_structured_async(raw_text)
        logger.info(
            "[%s] LLM extraction done: %d meds, %d labs, %d diagnoses",
            record_id[:8],
            len(extracted.get("medications", [])),
            len(extracted.get("lab_values", [])),
            len(extracted.get("diagnoses", [])),
        )

        # ── 6. BioBERT NER (SECONDARY) ───────────────────────────────────────
        # Run NER and merge any drug/lab names it found that the LLM missed.
        # NER-only additions are marked low_confidence=True to signal they were
        # not confirmed by the structured extraction step.
        logger.info("[%s] NER start (secondary signal)", record_id[:8])
        ner_entities = await ner.extract_entities_async(raw_text)
        _merge_ner_secondary(extracted, ner_entities)
        logger.info("[%s] NER merge done", record_id[:8])

        # NOTE: summary is generated AFTER step 8 (reference fallback) so that
        # abnormal-value callouts can include ranges resolved from the standard
        # lookup table, not just ranges printed in the document.

    except Exception as exc:
        error_msg = str(exc)
        logger.error("[%s] Pipeline error: %s", record_id[:8], exc, exc_info=True)
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass

    # ── 8. Map extraction output → DB rows ────────────────────────────────────

    medications_rows: list[dict] = []
    lab_value_rows:   list[dict] = []

    if extracted and not error_msg:
        medications_rows = _build_medication_rows(
            extracted.get("medications", []), patient_id, record_id, document_date or None,
        )
        lab_value_rows = _build_lab_value_rows(
            extracted.get("lab_values", []), patient_id, record_id, document_date or None,
        )
        _apply_reference_fallback(lab_value_rows)

    # ── 7.5. Clinical summary — must run AFTER reference fallback ─────────────
    # Fetch the patient's preferred_language so the summary is generated in
    # their chosen script (only the summary text changes — extraction stays English).
    preferred_language = "en-IN"
    try:
        lang_result = (
            supabase.table("profiles")
            .select("preferred_language")
            .eq("id", patient_id)
            .single()
            .execute()
        )
        fetched = (lang_result.data or {}).get("preferred_language")
        if fetched:
            preferred_language = fetched
    except Exception as exc:
        logger.warning("[%s] Could not fetch preferred_language: %s", record_id[:8], exc)

    # AI summary is a paid feature — skip silently for free/expired accounts.
    # The upload itself (OCR, NER, conflict detection) is always free.
    if not error_msg:
        if check_access(patient_id):
            logger.info("[%s] Summary start (lang=%s)", record_id[:8], preferred_language)
            try:
                summary = await llm.summarise_record_async(
                    raw_text, extracted, lab_value_rows, record_type, preferred_language,
                )
                logger.info("[%s] Summary done", record_id[:8])
            except Exception as exc:
                # Non-fatal: record is still saved; patient can re-process later.
                logger.error("[%s] Summary generation failed: %s", record_id[:8], exc)
        else:
            logger.info("[%s] Summary skipped — patient not on active plan", record_id[:8])

    # ── 9. Persist extracted rows ─────────────────────────────────────────────

    if medications_rows:
        supabase.table("medications").insert(medications_rows).execute()
        logger.info("[%s] Inserted %d medication rows.", record_id[:8], len(medications_rows))

    logger.debug(
        "[%s] Lab value rows before insert (%d): %s",
        record_id[:8], len(lab_value_rows), lab_value_rows,
    )
    if lab_value_rows:
        supabase.table("lab_values").insert(lab_value_rows).execute()
        logger.info("[%s] Inserted %d lab_value rows.", record_id[:8], len(lab_value_rows))

    # ── 10. Determine final status ─────────────────────────────────────────────
    # needs_review: extraction completed with no structured output at all.
    # This signals the patient that they should check the document manually —
    # not that processing failed, just that the parser found nothing to extract.

    if error_msg:
        final_status = ProcessingStatus.failed.value
    elif not medications_rows and not lab_value_rows:
        final_status = ProcessingStatus.needs_review.value
        logger.info("[%s] No meds or labs extracted — marking needs_review.", record_id[:8])
    else:
        final_status = ProcessingStatus.done.value

    # ── 11. Update health_records ─────────────────────────────────────────────

    update_payload: dict = {
        "raw_text":          raw_text or None,
        "summary":           summary or None,
        "processing_status": final_status,
        "processing_error":  error_msg,
    }
    supabase.table("health_records").update(update_payload).eq("id", record_id).execute()

    # ── 11b. Drug-conflict detection ─────────────────────────────────────────
    # Run only when new medications were added and the pipeline succeeded.
    # Checked AFTER the medications INSERT is committed (step 9) so that
    # run_conflict_check sees the new rows when it queries the DB.
    # Non-fatal: a conflict-check failure never marks the record as failed.
    if medications_rows and not error_msg:
        logger.info("[%s] Conflict check start", record_id[:8])
        try:
            new_conflicts = await conflict_svc.run_conflict_check(patient_id)
            if new_conflicts:
                logger.info(
                    "[%s] Conflict check: %d new interaction(s) detected.",
                    record_id[:8], len(new_conflicts),
                )
        except Exception as exc:
            logger.error("[%s] Conflict check failed: %s", record_id[:8], exc)

    # ── 11c. RAG — embed and store record chunks ──────────────────────────────
    # Build natural-language sentences from extracted data and store their
    # 768-dim embeddings in record_chunks for later /api/chat retrieval.
    # Non-fatal: a Gemini API error must never block the upload response.
    if not error_msg:
        try:
            record_data = {
                "medications": medications_rows,
                "lab_values":  lab_value_rows,
                "diagnoses":   extracted.get("diagnoses", []) if extracted else [],
                "summary":     summary,
            }
            chunks = rag_svc.build_chunks(record_data)
            if chunks:
                await rag_svc.embed_and_store_chunks(record_id, patient_id, chunks)
                logger.info("[%s] RAG: stored %d chunk(s).", record_id[:8], len(chunks))
        except Exception as exc:
            logger.warning("[%s] RAG embedding skipped (non-fatal): %s", record_id[:8], exc)

    # ── 12. Write access_log ──────────────────────────────────────────────────

    supabase.table("access_log").insert({
        "patient_id": patient_id,
        "record_id":  record_id,
        "action":     "view",
        "actor_type": "patient",
        "actor_id":   patient_id,
        "metadata": {
            "event":       "upload",
            "record_type": record_type,
            "file_name":   file.filename,
            "status":      final_status,
        },
    }).execute()

    # ── 13. Build and return response ─────────────────────────────────────────

    return {
        "record": {
            **record_row,
            "raw_text":          raw_text or None,
            "summary":           summary or None,
            "processing_status": final_status,
            "processing_error":  error_msg,
        },
        "medications":   medications_rows,
        "lab_values":    lab_value_rows,
        "diagnoses":     extracted.get("diagnoses", []) if extracted else [],
        "new_conflicts": new_conflicts,
    }


# ── Helpers: NER secondary merge ──────────────────────────────────────────────

def _merge_ner_secondary(extracted: dict, ner_entities: dict) -> None:
    """Merge BioBERT NER findings into the LLM-extracted dict (in-place).

    Only adds entries the LLM missed — it never overwrites LLM data.
    NER additions are marked with '_from_ner': True so they can be stored
    as low_confidence in the DB (see _build_medication_rows / _build_lab_value_rows).
    """
    # ── Medications: add drug names found by NER but absent from LLM output ──
    existing_drugs = {
        (m.get("drug_name") or "").lower()
        for m in extracted.get("medications", [])
        if m.get("drug_name")
    }
    for ner_med in ner_entities.get("medications", []):
        name = (ner_med.get("text") or "").strip()
        if name and name.lower() not in existing_drugs:
            extracted.setdefault("medications", []).append({
                "drug_name":  name,
                "dosage":     None,
                "frequency":  None,
                "_from_ner":  True,
                "_ner_score": round(float(ner_med.get("score", 0.0)), 3),
            })
            existing_drugs.add(name.lower())

    # ── Lab values: add tests found by NER regex but absent from LLM output ──
    existing_tests = {
        (lv.get("test_name") or "").lower()
        for lv in extracted.get("lab_values", [])
        if lv.get("test_name")
    }
    for ner_lab in ner_entities.get("lab_values", []):
        name = (ner_lab.get("name") or "").strip()
        if name and name.lower() not in existing_tests:
            extracted.setdefault("lab_values", []).append({
                "test_name":       name,
                "value":           ner_lab.get("value", ""),
                "unit":            ner_lab.get("unit") or None,
                "reference_range": None,
                "is_abnormal":     None,    # no reference range from NER — unknown, not confirmed normal
                "_from_ner":       True,
            })
            existing_tests.add(name.lower())


# ── Helpers: map extraction dicts → DB row dicts ──────────────────────────────

def _build_medication_rows(
    medications: list[dict],
    patient_id: str,
    record_id: str,
    document_date: str | None,
) -> list[dict]:
    """Convert extraction medication dicts to medications table rows.

    drug_name / dosage / frequency come from the LLM JSON.
    Entries tagged _from_ner=True are NER-only additions → low_confidence=True.
    """
    rows: list[dict] = []
    for med in medications:
        name = (med.get("drug_name") or med.get("name") or "").strip()
        if not name or len(name) < 2:
            continue
        from_ner = bool(med.get("_from_ner", False))
        rows.append({
            "patient_id":       patient_id,
            "record_id":        record_id,
            "name":             name,
            "dosage":           med.get("dosage") or None,
            "frequency":        med.get("frequency") or None,
            "duration":         med.get("duration") or None,
            "document_date":    document_date,
            "is_active":        True,
            # NER-only entries are unconfirmed by the LLM structured pass
            "low_confidence":   from_ner,
            "confidence_score": round(float(med.get("_ner_score", 1.0)), 3) if from_ner else 1.0,
        })
    return rows


def _build_lab_value_rows(
    lab_values: list[dict],
    patient_id: str,
    record_id: str,
    document_date: str | None,
) -> list[dict]:
    """Convert extraction lab value dicts to lab_values table rows."""
    rows: list[dict] = []
    seen: set[str] = set()    # deduplicate by test name (first occurrence wins)

    for lab in lab_values:
        test_name = (lab.get("test_name") or lab.get("name") or "").strip()
        value     = str(lab.get("value") or "").strip()
        if not test_name or not value:
            continue
        key = test_name.lower()
        if key in seen:
            continue
        seen.add(key)

        # Tolerate key aliases the LLM may use for reference_range
        ref_range = (
            lab.get("reference_range")
            or lab.get("reference_interval")
            or lab.get("ref_range")
            or lab.get("normal_range")
            or None
        )
        # is_abnormal can be None (no range to compare against), not just True/False.
        # Preserve None rather than coercing it to False — the DB column is now nullable.
        raw_abnormal = lab.get("is_abnormal")
        rows.append({
            "patient_id":      patient_id,
            "record_id":       record_id,
            "test_name":       test_name,
            "value":           value,
            "unit":            lab.get("unit") or None,
            "reference_range": ref_range,
            # Track where the reference range came from so the UI can badge it
            "reference_source": "lab_provided" if ref_range else None,
            "is_abnormal":     None if raw_abnormal is None else bool(raw_abnormal),
            "document_date":   document_date,
        })

    return rows


def _apply_reference_fallback(rows: list[dict]) -> None:
    """Fill missing reference_range from the standard lookup table (in-place).

    For each row without a document-provided range, we query the curated
    reference_ranges.json lookup.  If found, reference_source is set to
    "standard" and is_abnormal is computed by numeric comparison.

    Also computes is_abnormal for rows that already have a reference_range but
    where the LLM left is_abnormal=None (e.g. the LLM could not parse the format).
    """
    for row in rows:
        test_name = row.get("test_name", "")
        value_str = row.get("value", "")

        if not row.get("reference_range"):
            # No range from the document — try standard lookup
            result = reference_lookup.lookup(test_name)
            if result:
                range_str, source = result
                row["reference_range"] = range_str
                row["reference_source"] = source   # "standard"
                logger.debug(
                    "reference_fallback: '%s' → '%s' (standard)", test_name, range_str,
                )

        # Compute is_abnormal whenever we have a range but no verdict yet
        if row.get("reference_range") and row.get("is_abnormal") is None:
            computed = reference_lookup.compute_is_abnormal(value_str, row["reference_range"])
            row["is_abnormal"] = computed
