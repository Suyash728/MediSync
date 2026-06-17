import Link from "next/link";
import {
  Heart,
  ShieldCheck,
  FileText,
  AlertTriangle,
  Share2,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

// Landing page — visible to unauthenticated users.
// Keep it simple: value proposition + 2 CTAs (Login / Sign up).

const FEATURES = [
  {
    icon: FileText,
    title: "One place for every record",
    body: "Upload prescriptions, lab reports, discharge summaries and imaging. We parse them into a searchable timeline.",
  },
  {
    icon: AlertTriangle,
    title: "Automatic drug-conflict detection",
    body: "Our engine cross-checks your full medication history and flags dangerous interactions before they become a problem.",
  },
  {
    icon: Share2,
    title: "Secure, time-limited sharing",
    body: "Generate a scoped share link for your clinician. Choose which records to include. Revoke any time.",
  },
  {
    icon: ShieldCheck,
    title: "You own your data",
    body: "Records are encrypted at rest. No third-party access. Every view and download is logged and visible to you.",
  },
] as const;

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col">

      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <header className="border-b bg-background">
        <div className="container flex h-16 items-center justify-between">
          <div className="flex items-center gap-2 font-semibold text-primary">
            <Heart className="h-5 w-5 fill-primary" aria-hidden="true" />
            <span className="text-lg tracking-tight">MediSync</span>
          </div>

          <nav className="flex items-center gap-2">
            <Button variant="ghost" asChild>
              <Link href="/login">Log in</Link>
            </Button>
            <Button asChild>
              <Link href="/signup">
                Get started
                <ArrowRight className="ml-1.5 h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
          </nav>
        </div>
      </header>

      {/* ── Hero ────────────────────────────────────────────────────────── */}
      <section className="flex-1 flex items-center justify-center bg-slate-50 py-20 px-4">
        <div className="max-w-2xl text-center space-y-6">

          <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-1.5 text-sm font-medium text-primary">
            <Heart className="h-3.5 w-3.5 fill-primary" aria-hidden="true" />
            Patient-controlled health records
          </div>

          <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
            Your complete health history,{" "}
            <span className="text-primary">always in your hands</span>
          </h1>

          <p className="text-lg text-muted-foreground leading-relaxed">
            Upload medical documents from any source. MediSync parses them into a
            structured timeline, detects drug conflicts across your full history,
            and lets you share scoped views with clinicians — securely and on your terms.
          </p>

          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Button size="lg" asChild>
              <Link href="/signup">
                Create free account
                <ArrowRight className="ml-1.5 h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <Link href="/login">Sign in to my records</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* ── Feature cards ────────────────────────────────────────────────── */}
      <section className="py-16 px-4 bg-background">
        <div className="container">
          <h2 className="text-2xl font-semibold text-center mb-10 text-foreground">
            Everything you need to manage your health
          </h2>

          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <Card key={title} className="border-border/60">
                <CardContent className="pt-6 space-y-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                    <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
                  </div>
                  <h3 className="font-semibold text-foreground">{title}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">{body}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="border-t py-6 text-center text-sm text-muted-foreground">
        <div className="container flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-1.5">
            <Heart className="h-3.5 w-3.5 fill-muted-foreground" aria-hidden="true" />
            <span>MediSync — CodeFusion 2026</span>
          </div>
          <p>Your data stays yours. Always.</p>
        </div>
      </footer>
    </div>
  );
}
