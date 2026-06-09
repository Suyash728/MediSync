"""
LLM service — reused from MedInsight.

Primary: Groq llama-3.1-70b-versatile (fast inference, generous free tier).
Fallback: Google Gemini (if Groq rate-limits or is unreachable).

Responsibilities:
  1. Enrich / clean NER output (resolve ambiguous drug names, normalise units).
  2. Generate a plain-English summary of the record for the patient dashboard.
  3. Answer RAG-augmented queries (Phase 3+).

API keys are loaded from settings — NEVER read GROQ_API_KEY in the frontend.

This stub will be replaced with the real implementation in Phase 2.
"""

# from groq import AsyncGroq
# import google.generativeai as genai
# from utils.config import settings


async def summarise_record(raw_text: str, parsed_entities: dict) -> str:
    """Generate a plain-English summary of a medical record.

    Uses Groq llama-3.1-70b-versatile. Falls back to Gemini on failure.

    Args:
        raw_text:        OCR-extracted text from the document.
        parsed_entities: Output from the NER service.

    Returns:
        2–4 sentence plain-English summary suitable for patients.
    """
    raise NotImplementedError("LLM service will be implemented in Phase 2.")


async def enrich_entities(parsed_entities: dict) -> dict:
    """Use the LLM to resolve ambiguous entity names and fill gaps left by NER.

    For example: "Dolo 650" → drug_name="Paracetamol", dosage="650mg".
    """
    raise NotImplementedError("LLM entity enrichment will be implemented in Phase 2.")
