"use client";

/**
 * WelcomeModal — shown once after a patient's first login.
 *
 * Reads `has_onboarded` from the patient's profile row. If false, renders the
 * Dialog. On dismiss (any path — button, backdrop, Escape), sets both
 * `has_onboarded` and `preferred_language` so subsequent uploads use the right
 * language immediately.
 *
 * The language selector is the FIRST field — patients can choose before reading
 * the rest of the modal. On dismiss/confirm the choice is persisted to the DB,
 * the medisync_locale cookie is set, and the page reloads to apply the new locale.
 *
 * SQL required:
 *   ALTER TABLE profiles ADD COLUMN IF NOT EXISTS has_onboarded boolean NOT NULL DEFAULT false;
 *   ALTER TABLE profiles ADD COLUMN IF NOT EXISTS preferred_language text DEFAULT 'en-IN';
 */

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase";

const LANGUAGE_OPTIONS = [
  { code: "en-IN", label: "English" },
  { code: "hi-IN", label: "हिंदी" },
  { code: "ta-IN", label: "தமிழ்" },
  { code: "bn-IN", label: "বাংলা" },
  { code: "te-IN", label: "తెలుగు" },
  { code: "kn-IN", label: "ಕನ್ನಡ" },
  { code: "ml-IN", label: "മലയാളം" },
  { code: "mr-IN", label: "मराठी" },
  { code: "gu-IN", label: "ગુજરાતી" },
  { code: "pa-IN", label: "ਪੰਜਾਬੀ" },
  { code: "or-IN", label: "ଓଡ଼ିଆ" },
] as const;

export function WelcomeModal() {
  const [open, setOpen] = useState(false);
  const [selectedLang, setSelectedLang] = useState("en-IN");

  // Check DB flag on mount — avoids a flash for returning users
  useEffect(() => {
    async function checkOnboarded() {
      const supabase = createClient();
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;

      const { data } = await supabase
        .from("profiles")
        .select("has_onboarded, preferred_language")
        .eq("id", user.id)
        .single();

      if (data && data.has_onboarded === false) {
        // Pre-fill the selector with whatever was previously saved (if any)
        if (data.preferred_language) setSelectedLang(data.preferred_language);
        setOpen(true);
      }
    }
    void checkOnboarded();
  }, []);

  // Persist both flags and apply locale — called on every dismiss path
  async function finishOnboarding() {
    const supabase = createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (user) {
      await supabase
        .from("profiles")
        .update({ has_onboarded: true, preferred_language: selectedLang })
        .eq("id", user.id);
    }

    // Set the locale cookie so next-intl picks it up on reload
    document.cookie = `medisync_locale=${selectedLang}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`;

    setOpen(false);
    window.location.reload();
  }

  function handleOpenChange(v: boolean) {
    if (!v) void finishOnboarding();
  }

  function handleGetStarted() {
    void finishOnboarding();
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="w-[calc(100%-2rem)] sm:max-w-lg max-h-[85vh] overflow-y-auto pb-[max(1.5rem,env(safe-area-inset-bottom))]"
      >
        <DialogHeader>
          <DialogTitle className="text-xl">Welcome to MediSync</DialogTitle>
          <DialogDescription>
            Your invisible health ledger — private, structured, and always in your hands.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-1 text-sm">
          {/* ── Language selector — first field so it applies to the rest of the session ── */}
          <div className="space-y-1.5">
            <label htmlFor="welcome-lang" className="text-sm font-medium text-foreground">
              Choose your preferred language
            </label>
            <select
              id="welcome-lang"
              value={selectedLang}
              onChange={(e) => setSelectedLang(e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {LANGUAGE_OPTIONS.map(({ code, label }) => (
                <option key={code} value={code}>{label}</option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground">
              Medical summaries for new uploads will be generated in this language.
            </p>
          </div>

          <p className="text-muted-foreground leading-relaxed">
            MediSync lets you upload medical documents from any source — prescriptions,
            lab reports, discharge summaries — and builds a structured chronological
            record. Drug interactions are flagged automatically, and you can share scoped,
            time-limited views with clinicians without giving up control of your data.
          </p>

          <div className="space-y-1.5">
            <p className="font-medium text-foreground">What you can do:</p>
            <ul className="space-y-1 text-muted-foreground list-disc list-inside">
              <li>Upload and store all your medical documents in one place</li>
              <li>View your full health history on a chronological timeline</li>
              <li>Get automatic drug conflict alerts across your medication history</li>
              <li>Share time-limited, read-only links with clinicians — revocable any time</li>
            </ul>
          </div>

          {/* Honest limitations — prominently disclosed */}
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 space-y-1.5">
            <p className="font-semibold text-amber-900 text-xs uppercase tracking-wide">
              Important limitations
            </p>
            <ul className="space-y-1 text-amber-800 text-xs list-disc list-inside">
              <li>
                AI extraction may miss details from handwritten documents — always verify
                extracted data against the original.
              </li>
              <li>
                Drug conflict detection uses a curated dataset; always consult your doctor
                before changing medications.
              </li>
              <li>
                Shared links expire automatically and can be revoked at any time.
              </li>
            </ul>
          </div>
        </div>

        <DialogFooter>
          <Button onClick={handleGetStarted} className="w-full sm:w-auto">
            Get started — Upload your first record
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
