/**
 * Next.js Edge Middleware — route protection and session refresh.
 *
 * Rules:
 *   - /dashboard, /timeline, /alerts, /share, /settings, /record/* require auth.
 *     Unauthenticated requests redirect to /login.
 *   - /login and /signup redirect to /dashboard if the user is already logged in.
 *   - All other paths (landing page, /clinician/shared/*) are public.
 *
 * The createServerClient call here also refreshes the Supabase session cookie
 * on every request, keeping the user logged in across page navigations.
 */

import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

// Routes that patients must be authenticated to access
const PROTECTED_PREFIXES = [
  "/dashboard",
  "/timeline",
  "/alerts",
  "/share",
  "/settings",
  "/record",
];

// Auth pages that should redirect to /dashboard if already logged in
const AUTH_PAGES = ["/login", "/signup"];

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          // Write cookie changes from Supabase into both the request and response
          // so the session stays fresh without a round-trip.
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  // getUser() verifies the JWT server-side — more secure than getSession()
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const pathname = request.nextUrl.pathname;

  // Redirect unauthenticated users away from protected pages
  const isProtected = PROTECTED_PREFIXES.some((p) => pathname.startsWith(p));
  if (isProtected && !user) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Redirect already-logged-in users away from auth pages
  if (AUTH_PAGES.includes(pathname) && user) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return response;
}

export const config = {
  // Run on all paths except Next.js internals and static files
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|fonts|icons).*)",
  ],
};
