"""
OCR service — reused from MedInsight with light edits.

Responsibilities:
  1. If the PDF has a text layer (born-digital): extract with PyMuPDF (fitz).
  2. If the PDF is scanned or below a text-density threshold: render pages to
     images with PyMuPDF, pre-process with Pillow (deskew, binarise, upscale),
     and feed to pytesseract for OCR.
  3. Return the raw extracted text for downstream NER processing.

This stub will be replaced with the real implementation in Phase 2.
"""

# from pathlib import Path
# import fitz              # PyMuPDF
# import pytesseract
# from PIL import Image, ImageFilter


async def extract_text(file_path: str) -> str:
    """Extract plain text from a PDF or image file.

    Args:
        file_path: Local path to the uploaded file.

    Returns:
        Extracted plain-text string (may be multi-page, newlines preserved).

    Raises:
        ValueError: If the file type is not supported.
        RuntimeError: If OCR fails after all retries.
    """
    # Phase 2: implement PyMuPDF text-layer extraction with pytesseract fallback
    raise NotImplementedError("OCR service will be implemented in Phase 2.")
