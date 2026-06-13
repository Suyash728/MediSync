"""
OCR Service — adapted from MedInsight with significant enhancements.

Text extraction decision tree (in order of preference):
  1. PDF with native text layer (≥ 100 chars)
       → PyMuPDF text extraction: fast, lossless, no quality loss.
  2. PDF with thin/no text layer (< 100 chars — scanned or photographed)
       → rasterize each page to PNG bytes via PyMuPDF page.get_pixmap()
       → send raw PNG bytes to Gemini Vision via Part.from_bytes()
  3. JPEG / PNG image uploads
       → send file bytes directly to Gemini Vision
         (Tesseract fails on handwriting; Gemini handles it reliably)
  4. Tesseract OCR
       → last-resort fallback only when GEMINI_API_KEY is not configured.

Gemini SDK note: uses google-genai (new unified SDK), NOT google-generativeai
(end-of-life Nov 2025).  Import path: `from google import genai`.
"""

import asyncio
import io
import logging
import platform
import re
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image, ImageEnhance

logger = logging.getLogger(__name__)

# Windows: point to the Tesseract binary.
if platform.system() == "Windows":
    import os
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = os.getenv(
            "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )
    except ImportError:
        pass

SUPPORTED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}

# PDFs with fewer than this many native-text characters are treated as scanned.
_MIN_TEXT_LENGTH = 100

# Vision prompt — tells Gemini to return raw text only.
_VISION_PROMPT = (
    "Extract all text from this medical document image exactly as it appears. "
    "Preserve all numbers, units, abbreviations, and formatting. "
    "Do not summarise, interpret, or add any commentary. "
    "Return only the raw text content."
)

# Lazy-initialised Gemini client (google-genai SDK)
_gemini_client = None


# ── Public API ─────────────────────────────────────────────────────────────────

def extract_text(file_path: str, mime_type: str) -> str:
    """Synchronous entry point — routes to the appropriate extraction strategy.

    Args:
        file_path: Absolute path to the saved file.
        mime_type: One of application/pdf, image/jpeg, image/png.

    Returns:
        Cleaned plain-text string (may be empty if all strategies fail).

    Raises:
        ValueError: Unsupported MIME type.
    """
    if mime_type == "application/pdf":
        return _extract_from_pdf(file_path)
    elif mime_type in ("image/jpeg", "image/png"):
        return _extract_from_image(file_path, mime_type)
    else:
        raise ValueError(f"Unsupported MIME type: {mime_type}")


async def extract_text_async(file_path: str, mime_type: str) -> str:
    """Async wrapper — runs all extraction in a thread pool.

    PyMuPDF, the google-genai SDK (synchronous), and Tesseract are all
    blocking/CPU-bound.  Running in asyncio.to_thread() keeps the FastAPI
    event loop free for other requests.
    """
    return await asyncio.to_thread(extract_text, file_path, mime_type)


# ── Gemini Vision client ───────────────────────────────────────────────────────

def _get_gemini_client():
    """Lazy-init the google-genai Client.  Returns None if key not set."""
    global _gemini_client
    if _gemini_client is None:
        from utils.config import settings
        if not settings.gemini_api_key:
            return None
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=settings.gemini_api_key)
            logger.info("Gemini client initialised (model=%s).", settings.gemini_model)
        except ImportError:
            logger.warning("google-genai not installed — vision path unavailable.")
        except Exception as exc:
            logger.warning("Gemini client init failed: %s", exc)
    return _gemini_client


def _gemini_vision_extract(image_bytes: bytes, mime_type: str = "image/png") -> Optional[str]:
    """Send raw image bytes to Gemini Vision and return extracted text.

    Uses Part.from_bytes() from google.genai.types — the new SDK representation
    for inline binary data.  Returns None on any failure so callers can fall
    back to Tesseract.
    """
    client = _get_gemini_client()
    if client is None:
        return None

    try:
        from google.genai import types
        from utils.config import settings

        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[_VISION_PROMPT, image_part],
        )
        text = (response.text or "").strip()
        if text:
            logger.info("Gemini Vision extracted %d chars.", len(text))
        return text or None

    except Exception as exc:
        logger.warning("Gemini Vision call failed: %s", exc)
        return None


# ── Tesseract fallback ─────────────────────────────────────────────────────────

def _tesseract_extract(pil_image: Image.Image) -> str:
    """Tesseract OCR — only used when Gemini is unavailable.  Lazy import."""
    try:
        import pytesseract
        return pytesseract.image_to_string(pil_image, lang="eng")
    except ImportError:
        logger.error("pytesseract not installed — Tesseract fallback unavailable.")
        return ""
    except Exception as exc:
        logger.error("Tesseract OCR failed: %s", exc)
        return ""


def _preprocess_for_tesseract(img: Image.Image) -> Image.Image:
    """Grayscale + contrast + sharpness boost helps Tesseract on low-quality scans.
    NOT applied before Gemini Vision — the model works better on unprocessed images."""
    if img.mode != "L":
        img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.0)
    img = ImageEnhance.Sharpness(img).enhance(1.5)
    return img


# ── Extraction strategies ─────────────────────────────────────────────────────

def _extract_from_pdf(file_path: str) -> str:
    doc = fitz.open(file_path)
    text_parts: list[str] = []

    # Strategy 1: native text layer (born-digital PDFs)
    for page in doc:
        text_parts.append(page.get_text())

    full_text = "\n".join(text_parts).strip()

    if len(full_text) >= _MIN_TEXT_LENGTH:
        doc.close()
        return _clean_text(full_text)

    # Strategy 2: scanned PDF — rasterize pages and extract via vision.
    logger.info(
        "PDF native text is %d chars (below %d threshold); routing to vision.",
        len(full_text), _MIN_TEXT_LENGTH,
    )
    text_parts = []
    for page_num, page in enumerate(doc):
        # 300 DPI gives sharp text without excessive byte size
        mat = fitz.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=mat)
        page_bytes = pix.tobytes("png")   # raw PNG bytes → no PIL conversion needed

        page_text = _gemini_vision_extract(page_bytes, "image/png")
        if page_text is None:
            logger.info("Page %d: Gemini unavailable — using Tesseract.", page_num)
            pil_image = Image.open(io.BytesIO(page_bytes))
            page_text = _tesseract_extract(_preprocess_for_tesseract(pil_image))

        text_parts.append(page_text or "")

    doc.close()
    return _clean_text("\n".join(text_parts))


def _extract_from_image(file_path: str, mime_type: str) -> str:
    """For JPEG/PNG uploads, Gemini Vision is the primary extraction path.

    We read raw bytes from disk and pass them directly to Gemini via
    Part.from_bytes() — no PIL conversion needed for the vision path.
    PIL is only used when falling back to Tesseract.
    """
    with open(file_path, "rb") as fh:
        image_bytes = fh.read()

    text = _gemini_vision_extract(image_bytes, mime_type)
    if text is None:
        logger.info("Gemini Vision unavailable — falling back to Tesseract for image.")
        pil_image = Image.open(io.BytesIO(image_bytes))
        text = _tesseract_extract(_preprocess_for_tesseract(pil_image))

    return _clean_text(text or "")


# ── Text cleaning ─────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)         # collapse horizontal whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)       # max two consecutive newlines
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines).strip()
