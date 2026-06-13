"""
POST /upload — Document ingestion pipeline.

Full flow (synchronous within the request for hackathon simplicity):
  1. Verify JWT  →  get patient_id
  2. Validate file type (PDF / JPEG / PNG only)
  3. Save raw bytes to a temp file  →  upload to Supabase Storage
  4. Create health_records row (status=processing)
  5. OCR  →  raw_text
  6. BioBERT NER + regex  →  entities dict
  7. Map entities  →  medications[] + lab_values[]
  8. LLM  →  patient-facing summary
  9. Insert medications[] and lab_values[] rows
 10. Update health_records (status=done, summary, raw_text)
 11. Return the full record + extracted rows

Error handling: if any pipeline step fails, the record is marked
status=failed with processing_error populated.  We never leave a row
in 'processing' state permanently.

Note on async:  OCR and NER are CPU-bound.  They run via asyncio.to_thread()
so the event loop is not blocked.  LLM is I/O-bound and uses AsyncGroq.
"""

import logging
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, status

from models.schemas import MedicalRecord, ProcessingStatus, RecordType
from services import ocr, ner, llm
from utils.auth import get_current_patient
from utils.db import get_supabase
from utils.storage import upload_file, ALLOWED_TYPES

logger = logging.getLogger(__name__)

router = APIRouter()

# Maximum upload size: 20 MB
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


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
    document_date: str = Form(...),   # ISO date string "YYYY-MM-DD"
    facility:      str = Form(""),
    doctor:        str = Form(""),
    patient_id:    str = Depends(get_current_patient),
) -> dict:
    """Accept a medical document, run the full parsing pipeline, and persist results.

    Requires:  Authorization: Bearer <supabase_access_token>
    Body:      multipart/form-data with fields above + file
    Returns:   The newly-created health_record with extracted medications and lab values.
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

    # ── 2. Generate IDs and save to Storage ───────────────────────────────────

    record_id  = str(uuid.uuid4())
    supabase   = get_supabase()

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

    # ── 3. Create the health_records row (status=processing) ─────────────────

    record_row = {
        "id":                record_id,
        "patient_id":        patient_id,
        "record_type":       record_type,
        "title":             title,
        "document_date":     document_date or None,
        "facility":          facility or None,
        "doctor":            doctor or None,
        "file_path":         storage_path,
        "processing_status": "processing",
    }

    supabase.table("health_records").insert(record_row).execute()

    # ── 4. Run the parsing pipeline ───────────────────────────────────────────
    # We wrap in try/except so a pipeline failure marks the record as 'failed'
    # rather than leaving it stuck in 'processing'.

    raw_text      = ""
    entities:  dict = {}
    summary:   str  = ""
    error_msg: str | None = None

    # 4a. Write bytes to a temp file for OCR (both fitz and Tesseract need a path)
    suffix = Path(file.filename or "doc").suffix or ALLOWED_TYPES[content_type]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        # 4b. OCR — CPU-bound, runs in thread pool
        logger.info("[%s] OCR start", record_id[:8])
        raw_text = await ocr.extract_text_async(tmp_path, content_type)
        logger.info("[%s] OCR done: %d chars", record_id[:8], len(raw_text))

        # 4c. NER — CPU-bound, runs in thread pool
        logger.info("[%s] NER start", record_id[:8])
        entities = await ner.extract_entities_async(raw_text)
        logger.info(
            "[%s] NER done: %d meds, %d labs, %d diagnoses",
            record_id[:8],
            len(entities.get("medications", [])),
            len(entities.get("lab_values", [])),
            len(entities.get("diagnoses", [])),
        )

        # 4d. LLM summary — I/O-bound, truly async
        logger.info("[%s] LLM start", record_id[:8])
        summary = await llm.summarise_record_async(raw_text, entities)
        logger.info("[%s] LLM done", record_id[:8])

    except Exception as exc:
        error_msg = str(exc)
        logger.error("[%s] Pipeline error: %s", record_id[:8], exc)
    finally:
        # Always clean up the temp file
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass

    # ── 5. Map NER output → DB rows ───────────────────────────────────────────

    medications_rows: list[dict] = []
    lab_value_rows:   list[dict] = []

    if entities and not error_msg:
        medications_rows, lab_value_rows = ner.map_ner_to_schema(
            entities=entities,
            raw_text=raw_text,
            document_date=document_date or None,
            patient_id=patient_id,
            record_id=record_id,
        )

    # ── 6. Persist extracted rows ─────────────────────────────────────────────

    if medications_rows:
        supabase.table("medications").insert(medications_rows).execute()
        logger.info("[%s] Inserted %d medication rows", record_id[:8], len(medications_rows))

    if lab_value_rows:
        supabase.table("lab_values").insert(lab_value_rows).execute()
        logger.info("[%s] Inserted %d lab_value rows", record_id[:8], len(lab_value_rows))

    # ── 7. Update health_records ──────────────────────────────────────────────

    update_payload: dict = {
        "raw_text":          raw_text or None,
        "summary":           summary or None,
        "processing_status": "failed" if error_msg else "done",
        "processing_error":  error_msg,
    }

    supabase.table("health_records").update(update_payload).eq("id", record_id).execute()

    # ── 8. Write access log row ───────────────────────────────────────────────
    # Every record creation is logged (even failures) for the audit trail.
    supabase.table("access_log").insert({
        "patient_id": patient_id,
        "record_id":  record_id,
        "action":     "view",           # creation counts as first view
        "actor_type": "patient",
        "actor_id":   patient_id,
        "metadata": {
            "event":       "upload",
            "record_type": record_type,
            "file_name":   file.filename,
            "status":      "failed" if error_msg else "done",
        },
    }).execute()

    # ── 9. Build response ─────────────────────────────────────────────────────

    return {
        "record": {
            **record_row,
            "raw_text":          raw_text or None,
            "summary":           summary or None,
            "processing_status": "failed" if error_msg else "done",
            "processing_error":  error_msg,
        },
        "medications": medications_rows,
        "lab_values":  lab_value_rows,
        "diagnoses":   entities.get("diagnoses", []) if entities else [],
    }
