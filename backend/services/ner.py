"""
NER service — reused from MedInsight.

Uses HuggingFace BioBERT (dmis-lab/biobert-base-cased-v1.2) for biomedical
named-entity recognition. Extracts entities such as:
  - Drug names (mapped to Medication objects)
  - Diagnoses / conditions
  - Lab test names and values
  - Dosages, frequencies, durations

The model is loaded once at startup and kept in memory (model is ~400 MB).
On the first run it will be downloaded from HuggingFace Hub.

This stub will be replaced with the real implementation in Phase 2.
"""

# from transformers import pipeline, TokenClassificationPipeline
# from models.schemas import ParsedRecordData

# _ner_pipeline: TokenClassificationPipeline | None = None


def get_ner_pipeline():
    """Lazy-load the BioBERT NER pipeline (download on first call)."""
    # Phase 2: load dmis-lab/biobert-base-cased-v1.2 via transformers pipeline
    raise NotImplementedError("NER service will be implemented in Phase 2.")


async def extract_entities(text: str) -> dict:
    """Run BioBERT NER over raw text and return structured entity lists.

    Args:
        text: Raw OCR / PDF-extracted text.

    Returns:
        Dict with keys: medications, diagnoses, lab_results, vitals
        (matching the ParsedRecordData schema).
    """
    raise NotImplementedError("NER service will be implemented in Phase 2.")
