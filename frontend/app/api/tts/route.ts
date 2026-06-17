/**
 * POST /api/tts — Text-to-speech via Sarvam AI (server-side only).
 *
 * The SARVAM_API_KEY lives in the server environment and is never sent to the
 * browser.  The request body contains the text and language code; the response
 * is a WAV audio stream.
 *
 * Pipeline:
 *   1. Split text at sentence boundaries into chunks ≤450 chars
 *      (Sarvam AI's bulbul:v3 model has a per-request character limit)
 *   2. Call Sarvam TTS sequentially for each chunk
 *   3. Concatenate the returned WAV buffers:
 *        - Keep the full 44-byte WAV header from the first chunk
 *        - Strip headers from chunks 2..N
 *        - Rewrite the file-size field (bytes 4-7) and data-chunk size (bytes 40-43)
 *   4. Return the combined WAV as audio/wav
 */

import { NextRequest, NextResponse } from "next/server";

// ── Sentence-boundary chunk splitting ─────────────────────────────────────────
//
// Splits on sentence-ending punctuation (. ! ?) then groups sentences into
// chunks that stay under maxLen characters.  A single sentence longer than
// maxLen is kept as its own chunk — Sarvam handles long sentences gracefully.

function splitIntoChunks(text: string, maxLen = 450): string[] {
  // Split on sentence-terminating punctuation; the regex keeps the punctuation
  // attached to the preceding sentence via a lookbehind.
  const sentences = text.match(/[^.!?।]+[.!?।]+|[^.!?।]+$/g) ?? [text];

  const chunks: string[] = [];
  let current = "";

  for (const sentence of sentences) {
    const trimmed = sentence.trim();
    if (!trimmed) continue;

    if (current && (current + " " + trimmed).length > maxLen) {
      chunks.push(current.trim());
      current = trimmed;
    } else {
      current = current ? current + " " + trimmed : trimmed;
    }
  }

  if (current.trim()) chunks.push(current.trim());
  return chunks.length > 0 ? chunks : [text.trim()];
}

// ── WAV concatenation ─────────────────────────────────────────────────────────
//
// Standard WAV layout:
//   Bytes  0-3:  "RIFF"
//   Bytes  4-7:  file size minus 8 (little-endian uint32)
//   Bytes  8-11: "WAVE"
//   Bytes 12-15: "fmt "
//   Bytes 16-43: fmt chunk + padding
//   Bytes 36-39: "data"
//   Bytes 40-43: data chunk size (little-endian uint32)
//   Bytes 44+:   PCM audio samples

const WAV_HEADER_SIZE = 44;

function concatWav(buffers: Buffer[]): Buffer {
  if (buffers.length === 1) return buffers[0];

  // Strip the 44-byte header from every chunk after the first
  const parts = buffers.map((buf, i) =>
    i === 0 ? buf : buf.subarray(WAV_HEADER_SIZE)
  );

  const combined = Buffer.concat(parts);

  // Patch the combined header with the new sizes
  const dataSize = combined.length - WAV_HEADER_SIZE;
  const fileSize = combined.length - 8;

  combined.writeUInt32LE(fileSize, 4);   // RIFF chunk size
  combined.writeUInt32LE(dataSize, 40);  // data sub-chunk size

  return combined;
}

// ── Route handler ─────────────────────────────────────────────────────────────

export async function POST(req: NextRequest): Promise<NextResponse> {
  const apiKey = process.env.SARVAM_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "TTS not configured — SARVAM_API_KEY missing." },
      { status: 503 }
    );
  }

  let body: { text?: unknown; language_code?: unknown };
  try {
    body = await req.json() as { text?: unknown; language_code?: unknown };
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const text         = typeof body.text          === "string" ? body.text.trim()          : "";
  const languageCode = typeof body.language_code === "string" ? body.language_code.trim() : "en-IN";

  if (!text) {
    return NextResponse.json({ error: "text is required." }, { status: 400 });
  }

  const chunks = splitIntoChunks(text, 450);

  // Lazy-import the sarvamai package (keeps cold-start fast for non-TTS requests)
  const { SarvamAIClient } = await import("sarvamai");
  const client = new SarvamAIClient({ apiSubscriptionKey: apiKey });

  const wavBuffers: Buffer[] = [];

  for (const chunk of chunks) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- Sarvam SDK types are loose
      const response = await (client.textToSpeech as any).convert({
        inputs: [chunk],
        target_language_code: languageCode,
        speaker: "suhani",
        model: "bulbul:v3",
        enable_preprocessing: true,
      });

      const b64: string | undefined = response?.audios?.[0];
      if (b64) {
        wavBuffers.push(Buffer.from(b64, "base64"));
      }
    } catch (err) {
      // Non-fatal: skip this chunk rather than failing the whole request
      console.error("[TTS] chunk failed:", err);
    }
  }

  if (wavBuffers.length === 0) {
    return NextResponse.json(
      { error: "No audio generated — all TTS chunks failed." },
      { status: 502 }
    );
  }

  const combined = concatWav(wavBuffers);

  // NextResponse body must be BodyInit — convert Buffer to Uint8Array
  return new NextResponse(new Uint8Array(combined), {
    headers: {
      "Content-Type":   "audio/wav",
      "Content-Length": String(combined.byteLength),
      "Cache-Control":  "no-store",
    },
  });
}
