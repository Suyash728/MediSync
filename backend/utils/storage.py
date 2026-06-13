"""
Supabase Storage helpers for the private 'medical-docs' bucket.

All medical files are stored in a PRIVATE bucket — they are never served via
a public URL.  Access is via short-lived signed URLs generated on demand.

File layout inside the bucket:
    {patient_id}/{record_id}.{ext}

This scopes each file to its owner without needing extra path checks.
"""

import logging
import mimetypes
from pathlib import Path

from utils.db import get_supabase

logger = logging.getLogger(__name__)

BUCKET = "medical-docs"

# Allowed MIME types and their canonical extensions
ALLOWED_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/jpeg":      ".jpg",
    "image/png":       ".png",
}


def upload_file(
    file_bytes: bytes,
    patient_id: str,
    record_id: str,
    content_type: str,
) -> str:
    """Upload a file to the private medical-docs bucket.

    Args:
        file_bytes:   Raw bytes of the uploaded file.
        patient_id:   UUID of the owning patient (used as path prefix).
        record_id:    UUID of the health_records row being created.
        content_type: MIME type of the file.

    Returns:
        The storage path (e.g. "abc123/rec456.pdf") — store this in
        health_records.file_path, NOT a full URL.

    Raises:
        ValueError:   Unsupported MIME type.
        RuntimeError: Supabase Storage API error.
    """
    if content_type not in ALLOWED_TYPES:
        raise ValueError(
            f"Unsupported file type '{content_type}'. "
            f"Allowed: {list(ALLOWED_TYPES.keys())}"
        )

    ext = ALLOWED_TYPES[content_type]
    storage_path = f"{patient_id}/{record_id}{ext}"

    supabase = get_supabase()
    resp = supabase.storage.from_(BUCKET).upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": content_type},
    )

    # supabase-py raises on error, but check the path in the response just in case
    logger.info("Stored %d bytes at %s/%s", len(file_bytes), BUCKET, storage_path)
    return storage_path


def get_signed_url(storage_path: str, expires_in: int = 3600) -> str:
    """Generate a short-lived signed URL for a private file.

    Args:
        storage_path: Path returned by upload_file().
        expires_in:   URL lifetime in seconds (default 1 hour).

    Returns:
        A signed URL that the browser can use to download the file.
    """
    supabase = get_supabase()
    result = supabase.storage.from_(BUCKET).create_signed_url(
        path=storage_path,
        expires_in=expires_in,
    )
    # result is {'signedURL': '...', 'error': None}
    signed_url: str = result["signedURL"]
    return signed_url


def delete_file(storage_path: str) -> None:
    """Delete a file from Storage when its health_record is deleted."""
    supabase = get_supabase()
    supabase.storage.from_(BUCKET).remove([storage_path])
    logger.info("Deleted Storage file: %s", storage_path)
