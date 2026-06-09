"""
POST /process/{record_id} — triggers the OCR → BioBERT NER → LLM pipeline
for a specific record and writes the parsed_data back to Supabase.

Phase 2 will implement the full pipeline. This stub returns a 501 placeholder.
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/{record_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def process_record(record_id: str) -> JSONResponse:
    """Trigger document processing — implemented in Phase 2."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "Process endpoint not yet implemented (Phase 2)."},
    )


@router.get("/{record_id}/status", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_processing_status(record_id: str) -> JSONResponse:
    """Get processing status for a record — implemented in Phase 2."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": "Processing status endpoint not yet implemented (Phase 2)."},
    )
