"""
POST /chat — RAG-powered chat endpoint.

Flow:
  1. Auth: resolve patient_id from Bearer token. (TEMPORARILY BYPASSED FOR LOCAL DEV)
  2. Embed the message and retrieve top-k chunks from record_chunks via RPC.
  3. Deterministic refusal gate (rag.is_relevant): if the best match is below
     SIMILARITY_FLOOR, return a canned refusal WITHOUT calling any LLM.
  4. Build a grounded system prompt + user prompt from the retrieved excerpts.
  5. Call llm_client.complete() — Groq primary, Gemini fallback.
  6. Return the contract shape with sources mapped to {record_id, snippet}.

Tier gating is intentionally absent here — that is Phase A3.
"""

import logging

from fastapi import APIRouter, status
from pydantic import BaseModel

from services import rag as rag_svc
from services import llm_client
# from utils.auth import get_current_patient  <-- Commented out for local dev bypass

logger = logging.getLogger(__name__)

router = APIRouter()

# Canned refusal shown when no grounding evidence clears SIMILARITY_FLOOR.
_REFUSAL_TEXT = (
    "I couldn't find anything about that in your uploaded records. "
    "Please try rephrasing, or upload a document that contains this information."
)

_SYSTEM_PROMPT = """\
You are a medical records assistant for a patient.
Answer ONLY using the record excerpts provided below.
If the excerpts do not contain enough information to answer, say so plainly — \
do not guess or invent medical facts.
Be concise, factual, and precise.
This is not medical advice.\
"""


# ── Pydantic models ───────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class SourceItem(BaseModel):
    # record_id is a UUID string in our schema (health_records.id is UUID).
    record_id: str
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    refused: bool
    sources: list[SourceItem]
    provider: str   # "groq" | "gemini"


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Answer a patient question using their medical records (RAG)",
)
async def chat(
    body: ChatRequest,
    # patient_id: str = Depends(get_current_patient),  <-- ⚠️ BYPASSED FOR DEV TESTING
) -> ChatResponse:
    """RAG-powered Q&A over the authenticated patient's own records.

    Returns a refused=True response (no LLM call) when retrieval finds nothing
    above the similarity threshold, guaranteeing grounded answers only.
    """
    
    # ── ⚠️ TEMPORARY DEV BYPASS FOR LOCAL TESTING ──────────────────────────────
    # Using the backfilled demo UUID so you can test instantly via Swagger Docs
    patient_id = "8c5cf54d-72f5-4a0d-adb4-d06a5fb4706b"
    # ──────────────────────────────────────────────────────────────────────────

    # ── Step 2: Retrieve top-k matching chunks ────────────────────────────────
    # search_records returns a list of dictionaries from Supabase RPC
    matches = await rag_svc.search_records(patient_id, body.message, k=5)

    # ── Step 3: Deterministic refusal gate ────────────────────────────────────
    if not rag_svc.is_relevant(matches):
        # Safely grab the similarity score from the first dictionary match
        top_sim = matches[0]["similarity"] if matches else 0.0
        logger.info(
            "chat [%.8s]: refusal — top similarity=%.3f (floor=%.2f)",
            patient_id,
            top_sim,
            rag_svc.SIMILARITY_FLOOR,
        )
        return ChatResponse(
            answer=_REFUSAL_TEXT,
            refused=True,
            sources=[],
            provider="groq",   # no LLM was called; label is a no-op here
        )

    # ── Step 4: Build grounded prompt ─────────────────────────────────────────
    # Safely extract content using dictionary keys
    excerpts = "\n".join(
        f"[{i + 1}] {m['content']}"
        for i, m in enumerate(matches)
    )
    user_prompt = (
        f"Record excerpts from your medical history:\n\n"
        f"{excerpts}\n\n"
        f"Patient question: {body.message}"
    )

    # ── Step 5: LLM completion ────────────────────────────────────────────────
    logger.info("chat [%.8s]: calling LLM with %d source chunk(s).", patient_id, len(matches))
    answer, provider = await llm_client.complete(
        prompt=user_prompt,
        system=_SYSTEM_PROMPT,
    )

    # ── Step 6: Build sources ─────────────────────────────────────────────────
    # Safely build sources using dictionary keys and convert record_id to string
    sources = [
        SourceItem(
            record_id=str(m["record_id"]),
            snippet=m["content"][:160],
        )
        for m in matches
    ]

    return ChatResponse(
        answer=answer,
        refused=False,
        sources=sources,
        provider=provider,
    )