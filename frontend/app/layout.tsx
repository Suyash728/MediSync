import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import "./globals.css";
import { Toaster } from "@/components/ui/sonner";
import ServiceWorkerRegistrar from "@/components/ServiceWorkerRegistrar";

// Lazy font injection: we inject a Google Fonts <link> for the active locale only.
// English uses the system font stack (no external font needed).
// Each Noto Sans variant covers one script family.
const SCRIPT_FONT_URL: Record<string, string> = {
  "hi-IN": "https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;500;600;700&display=swap",
  "mr-IN": "https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;500;600;700&display=swap",
  "ta-IN": "https://fonts.googleapis.com/css2?family=Noto+Sans+Tamil:wght@400;500;600;700&display=swap",
  "bn-IN": "https://fonts.googleapis.com/css2?family=Noto+Sans+Bengali:wght@400;500;600;700&display=swap",
  "te-IN": "https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@400;500;600;700&display=swap",
  "kn-IN": "https://fonts.googleapis.com/css2?family=Noto+Sans+Kannada:wght@400;500;600;700&display=swap",
  "ml-IN": "https://fonts.googleapis.com/css2?family=Noto+Sans+Malayalam:wght@400;500;600;700&display=swap",
  "gu-IN": "https://fonts.googleapis.com/css2?family=Noto+Sans+Gujarati:wght@400;500;600;700&display=swap",
  "pa-IN": "https://fonts.googleapis.com/css2?family=Noto+Sans+Gurmukhi:wght@400;500;600;700&display=swap",
  "or-IN": "https://fonts.googleapis.com/css2?family=Noto+Sans+Oriya:wght@400;500;600;700&display=swap",
};

export const metadata: Metadata = {
  title: {
    default: "MediSync — Your Health Ledger",
    template: "%s | MediSync",
  },
  description:
    "Patient-controlled medical records. Upload documents, track your medication history, and share securely with clinicians.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();
  const fontUrl = SCRIPT_FONT_URL[locale];

  return (
    <html lang={locale} suppressHydrationWarning>
      <head>
        {/* PWA manifest + theme */}
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#0d9488" />
        {/* iOS home-screen icon */}
        <link rel="apple-touch-icon" href="/icons/icon-192.png" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <meta name="apple-mobile-web-app-title" content="MediSync" />
        {/* Locale-specific Noto Sans fonts */}
        {fontUrl && (
          <>
            <link rel="preconnect" href="https://fonts.googleapis.com" />
            <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
            <link href={fontUrl} rel="stylesheet" />
          </>
        )}
      </head>
      <body className="font-sans antialiased">
        <NextIntlClientProvider locale={locale} messages={messages}>
          {children}
          {/* Global toast notifications */}
          <Toaster position="top-right" />
          {/* PWA service worker registration */}
          <ServiceWorkerRegistrar />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
