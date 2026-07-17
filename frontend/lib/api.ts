/**
 * Typed fetch wrapper for the MediSync FastAPI backend.
 *
 * All component-level data fetching goes through this module — never inline
 * fetch() calls in components. This makes it easy to add auth headers, retries,
 * or base-URL changes in one place.
 *
 * Auth: the Supabase JWT is forwarded on every request so FastAPI can verify it
 * via the Authorization: Bearer header.
 */

import { mockChatApi } from "./mockChat";
import { ChatResponse } from "./types";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

// ─── Error type ───────────────────────────────────────────────────────────────

export class APIError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "APIError";
  }
}

// ─── Core fetch helper ────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  authToken?: string
): Promise<T> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    ...options.headers,
  };

  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    // FastAPI returns { "detail": "..." } on errors.
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json() as { detail?: string };
      message = body.detail ?? message;
    } catch {
      // Body wasn't JSON — keep the status string.
    }
    throw new APIError(res.status, message);
  }

  // 204 No Content → return undefined cast to T
  if (res.status === 204) return undefined as T;

  return res.json() as Promise<T>;
}

// ─── Multipart helper (file uploads) ─────────────────────────────────────────

async function apiUpload<T>(
  path: string,
  formData: FormData,
  authToken?: string
): Promise<T> {
  const headers: HeadersInit = {
    // Do NOT set Content-Type for multipart — the browser sets it with the boundary.
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
  };

  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json() as { detail?: string };
      message = body.detail ?? message;
    } catch { /* empty */ }
    throw new APIError(res.status, message);
  }

  return res.json() as Promise<T>;
}

// ─── Public API surface ───────────────────────────────────────────────────────

export const api = {
  get<T>(path: string, authToken?: string): Promise<T> {
    return apiFetch<T>(path, { method: "GET" }, authToken);
  },

  post<T>(path: string, body?: unknown, authToken?: string): Promise<T> {
    return apiFetch<T>(
      path,
      { method: "POST", body: JSON.stringify(body) },
      authToken
    );
  },

  put<T>(path: string, body?: unknown, authToken?: string): Promise<T> {
    return apiFetch<T>(
      path,
      { method: "PUT", body: JSON.stringify(body) },
      authToken
    );
  },

  patch<T>(path: string, body?: unknown, authToken?: string): Promise<T> {
    return apiFetch<T>(
      path,
      { method: "PATCH", body: JSON.stringify(body) },
      authToken
    );
  },

  delete<T>(path: string, authToken?: string): Promise<T> {
    return apiFetch<T>(path, { method: "DELETE" }, authToken);
  },

  /** Upload a file via multipart/form-data (used by the record upload flow). */
  upload<T>(path: string, formData: FormData, authToken?: string): Promise<T> {
    return apiUpload<T>(path, formData, authToken);
  },
};

// ─── Share grant helpers ──────────────────────────────────────────────────────

export const shareApi = {
  create(
    body: {
      recipient_name?: string | null;
      recipient_email?: string | null;
      scope_record_ids?: string[] | null;
      scope_record_types?: string[] | null;
      expires_in_days?: number;
    },
    authToken: string,
  ) {
    return api.post<{
      grant: import("./types").ShareGrant;
      token: string;
    }>("/share/", body, authToken);
  },

  list(authToken: string) {
    return api.get<{
      grants: import("./types").ShareGrant[];
      total: number;
    }>("/share/", authToken);
  },

  revoke(grantId: string, authToken: string) {
    return api.delete<void>(`/share/${grantId}`, authToken);
  },
};

// ─── Conflict-specific helpers ────────────────────────────────────────────────

export const conflictsApi = {
  list(authToken: string) {
    return api.get<{
      conflicts: import("./types").DrugConflict[];
      total: number;
      unacknowledged_count: number;
    }>("/conflicts/", authToken);
  },

  recheck(authToken: string) {
    return api.post<{
      new_conflicts: import("./types").DrugConflict[];
      count: number;
      message: string;
    }>("/conflicts/recheck", undefined, authToken);
  },

  acknowledge(conflictId: string, authToken: string) {
    return api.post<{ success: boolean; id: string }>(
      `/conflicts/${conflictId}/acknowledge`,
      undefined,
      authToken,
    );
  },
};

// ─── TTS-specific helpers ─────────────────────────────────────────────────────

export const ttsApi = {
  synthesise(text: string, languageCode: string, authToken: string) {
    return api.post<{ audio_url: string }>(
      "/tts/",
      { text, language_code: languageCode },
      authToken,
    );
  },
};

// ─── Chat-specific helpers ───────────────────────────────────────────────────

export const chatApi = {
  send(
    message: string,
    conversationId: string | null,
    authToken?: string
  ): Promise<ChatResponse> {
    return api.post<ChatResponse>(
      "/chat/",
      { message, conversation_id: conversationId },
      authToken
    );
  },
};

// ─── Profile-specific helpers ────────────────────────────────────────────────

export const profileApi = {
  getAccess(authToken?: string): Promise<{
    is_paid: boolean;
    trial_ends_at: string | null;
    has_access: boolean;
  }> {
    return api.get<{
      is_paid: boolean;
      trial_ends_at: string | null;
      has_access: boolean;
    }>("/me/access", authToken);
  },
};

