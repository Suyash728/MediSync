"""
TTS service — reused from MedInsight (optional feature).

Uses edge-tts with the en-IN-NeerjaNeural voice to read record summaries aloud.
Particularly useful for elderly patients or low-literacy scenarios.

This stub will be replaced with the real implementation in Phase 5 (optional).
"""

# import edge_tts
# import tempfile, os


async def synthesise_speech(text: str) -> bytes:
    """Convert text to MP3 audio using Microsoft Edge TTS.

    Args:
        text: Plain-text content to synthesise (typically a record summary).

    Returns:
        MP3 bytes suitable for streaming to the browser.
    """
    raise NotImplementedError("TTS service will be implemented in Phase 5 (optional).")
