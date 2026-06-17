/**
 * next-intl server-side request configuration.
 *
 * Reads the active locale from the `medisync_locale` cookie set by the language
 * selector in WelcomeModal and Settings.  Falls back to "en-IN" if no cookie
 * is present or the value is not a supported locale.
 *
 * This cookie approach avoids URL-based locale routing (/hi/dashboard etc.) which
 * would require restructuring all routes.  The patient simply changes language in
 * Settings and the page reloads in the new locale — single URL, many languages.
 */

import { getRequestConfig } from "next-intl/server";
import { cookies } from "next/headers";

const SUPPORTED_LOCALES = [
  "en-IN", "hi-IN", "ta-IN", "bn-IN", "te-IN",
  "kn-IN", "ml-IN", "mr-IN", "gu-IN", "pa-IN", "or-IN",
] as const;

export type SupportedLocale = typeof SUPPORTED_LOCALES[number];

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const raw = cookieStore.get("medisync_locale")?.value ?? "en-IN";
  const locale = (SUPPORTED_LOCALES as readonly string[]).includes(raw) ? raw : "en-IN";

  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default as Record<string, unknown>,
  };
});
