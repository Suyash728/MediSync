POST /api/chat
  auth: required (Bearer). gated: paid feature.
  req:  { "message": string, "conversation_id": string | null }
  res:  {
          "answer": string,
          "refused": boolean,          // true when nothing relevant retrieved
          "sources": [ { "record_id": number, "snippet": string } ],
          "provider": "groq" | "gemini"   // which LLM answered (for the resilience slide)
        }
  402 when trial expired & not paid.

GET /api/suggestions
  auth: required. gated: paid feature.
  res:  {
          "suggestions": [ { "text": string, "based_on_record_id": number | null } ],
          "generated_at": string   // ISO8601; empty array if no records yet
        }
  402 when trial expired & not paid.

GET /api/me/access   (cheap, ungated — frontend calls this to decide what to show)
  res:  { "is_paid": boolean, "trial_ends_at": string | null, "has_access": boolean }

POST /api/tts        (existing; now cached server-side, contract unchanged)
  req:  { "text": string, "language": string }
  res:  { "audio_url": string }   // signed URL to cached or freshly-generated audio