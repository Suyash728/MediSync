import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Ensures NEXT_PUBLIC_BACKEND_URL is always defined at build time.
  // Falls back to http://localhost:8000 for local dev when the env var is unset.
  // In production (Vercel), set NEXT_PUBLIC_BACKEND_URL to your Railway URL.
  env: {
    NEXT_PUBLIC_BACKEND_URL:
      process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000",
  },
};

export default withNextIntl(nextConfig);
