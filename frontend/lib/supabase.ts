/**
 * Supabase client helpers for MediSync.
 *
 * Two separate clients are needed in Next.js App Router:
 *   createClient()       — browser (Client Components, "use client" files)
 *   createServerClient() — server (Server Components, Route Handlers, Actions)
 *
 * The server client threads cookies through every request so Supabase can read
 * the session set by the browser client. Never call createServerClient() from a
 * Client Component — it imports next/headers which is server-only.
 */

// ─── Browser client ───────────────────────────────────────────────────────────
// Safe to import in any "use client" component.

import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}

// ─── Server client ────────────────────────────────────────────────────────────
// Import this only in Server Components / Route Handlers / Server Actions.
// Kept in a separate exported async function so it can await cookies().

export async function createServerSupabaseClient() {
  // Dynamic import keeps next/headers out of the browser bundle.
  const { cookies } = await import("next/headers");
  const { createServerClient } = await import("@supabase/ssr");

  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) => {
              cookieStore.set(name, value, options);
            });
          } catch {
            // Called from a Server Component where cookie mutation is impossible.
            // The middleware is responsible for refreshing the session in this case.
          }
        },
      },
    }
  );
}
