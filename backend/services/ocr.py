"""
OCR Service — adapted from MedInsight with minimal changes.

Extracts plain text from medical documents:
  - Born-digital PDFs: PyMuPDF text layer (fast, no quality loss)
  - Scanned PDFs / images: render to 300 DPI PNG → pytesseract

The only MediSync addition is the async wrapper (`extract_text_async`) so the
CPU-bound OCR work runs in a thread pool without blocking FastAPI's event loop.
"""

import asyncio
import io
import platform
import re

import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageEnhance

# Windows: point to the Tesseract binary location
if platform.system() == "Windows":
    import os
    pytesseract.pytesseract.tesseract_cmd = os.getenv(
        "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

SUPPORTED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}

# If the direct text layer produces fewer than 100 characters the PDF is
# probably scanned — fall back to pytesseract OCR.
_MIN_TEXT_LENGTH = 100


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text(file_path: str, mime_type: str) -> str:
    """Synchronous entry point (reused from MedInsight).

    Args:
        file_path: Absolute path to the saved file.
        mime_type: One of application/pdf, image/jpeg, image/png.

    Returns:
        Cleaned plain-text string.

    Raises:
        ValueError: Unsupported MIME type.
    """
    if mime_type == "application/pdf":
        return _extract_from_pdf(file_path)
    elif mime_type in ("image/jpeg", "image/png"):
        return _extract_from_image(file_path)
    else:
        raise ValueError(f"Unsupported MIME type: {mime_type}")


async def extract_text_async(file_path: str, mime_type: str) -> str:
    """Async wrapper — runs OCR in a thread pool so the event loop stays free.

    OCR and PDF rendering are CPU-bound operations; calling them directly in an
    async function would block all other requests for seconds.
    """
    return await asyncio.to_thread(extract_text, file_path, mime_type)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_from_pdf(file_path: str) -> str:
    doc = fitz.open(file_path)
    text_parts: list[str] = []

    # First pass: try the text layer (fast path)
    for page in doc:
        text_parts.append(page.get_text())

    full_text = "\n".join(text_parts).strip()

    # Second pass: scanned PDF → render each page → pytesseract
    if len(full_text) < _MIN_TEXT_LENGTH:
        text_parts = []
        for page in doc:
            mat = fitz.Matrix(300 / 72, 300 / 72)   # 300 DPI
            pix = page.get_pixmap(matrix=mat)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            img = _preprocess_image(img)
            text_parts.append(pytesseract.image_to_string(img, lang="eng"))
        full_text = "\n".join(text_parts)

    doc.close()
    return _clean_text(full_text)


def _extract_from_image(file_path: str) -> str:
    img = Image.open(file_path)
    img = _preprocess_image(img)
    return _clean_text(pytesseract.image_to_string(img, lang="eng"))


def _preprocess_image(img: Image.Image) -> Image.Image:
    """Grayscale + contrast + sharpness boost improves OCR accuracy on medical
    documents which are often faint photocopies or smartphone photos."""
    if img.mode != "L":
        img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = ImageEnhance.Sharpness(img).enhance(1.5)
    return img


def _clean_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)         # collapse horizontal whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)       # max two consecutive newlines
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines).strip()
