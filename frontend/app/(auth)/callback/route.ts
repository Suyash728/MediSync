/**
 * Supabase OAuth / magic-link callback handler.
 *
 * Supabase redirects here after:
 *   - Email confirmation (if enabled)
 *   - OAuth social login (if added later)
 *   - Magic link login (if added later)
 *
 * We exchange the code for a session, then redirect to /dashboard.
 */

import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";

export async function GET(request: NextRequest) {
  const requestUrl = new URL(request.url);
  const code       = requestUrl.searchParams.get("code");
  const next       = requestUrl.searchParams.get("next") ?? "/dashboard";

  if (!code) {
    // No code — something went wrong upstream; send to login
    return NextResponse.redirect(new URL("/login", request.url));
  }

  const response = NextResponse.redirect(new URL(next, requestUrl.origin));

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  await supabase.auth.exchangeCodeForSession(code);
  return response;
}
