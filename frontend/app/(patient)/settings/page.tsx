"use client";

/**
 * /settings — Patient account settings.
 *
 * Three sections:
 *   1. Language preference — selector + save; updates DB and reloads page with new locale
 *   2. Account info — read-only profile fields (name, email, DOB, ABHA)
 *   3. Danger zone — delete account with confirmation dialog
 *
 * Language save writes preferred_language to the profiles table directly via the
 * Supabase browser client (same pattern as has_onboarded — RLS allows patients
 * to update their own row) and sets the medisync_locale cookie before reloading.
 *
 * Delete account calls DELETE /profile on the backend, which:
 *   a. Deletes all Storage files for the patient
 *   b. Deletes the profile row (cascades to all health records, medications, etc.)
 *   c. Deletes the Supabase Auth user via the service-role admin API
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslations, useLocale } from "next-intl";
import { Loader2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Dialog, DialogContent, DialogHeader, DialogFooter,
  DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { createClient } from "@/lib/supabase";
import { api } from "@/lib/api";

// ── Language options ──────────────────────────────────────────────────────────

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

// ── Profile shape returned from profiles table ────────────────────────────────

interface Profile {
  full_name:          string | null;
  email:              string | null;
  date_of_birth:      string | null;
  abha_number:        string | null;
  preferred_language: string | null;
}

// Tri-state for the profile fetch: loading / loaded / error
type ProfileState = "loading" | "loaded" | "error";

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const t      = useTranslations("settings");
  const locale = useLocale();

  const [profile,           setProfile]           = useState<Profile | null>(null);
  const [profileState,      setProfileState]      = useState<ProfileState>("loading");
  const [selectedLang,      setSelectedLang]      = useState("en-IN");
  const [savingLang,        setSavingLang]        = useState(false);
  const [showDeleteDialog,  setShowDeleteDialog]  = useState(false);
  const [deleting,          setDeleting]          = useState(false);

  const loadingProfile = profileState === "loading";
  console.log("[settings] render — profileState:", profileState, "selectedLang:", selectedLang);

  // ── Load profile ────────────────────────────────────────────────────────────

  const loadProfile = useCallback(async () => {
    setProfileState("loading");
    const supabase = createClient();

    // 1. Confirm we have a logged-in user
    const { data: { user } } = await supabase.auth.getUser();
    console.log("[settings] auth.getUser result:", user?.id ?? "NO USER");
    if (!user) { setProfileState("error"); return; }

    // 2. Fetch the profile row
    let { data, error } = await supabase
      .from("profiles")
      .select("full_name, email, date_of_birth, abha_number, preferred_language")
      .eq("id", user.id)
      .single();

    console.log("[settings] profiles SELECT raw result:", { data, error });

    // 3. If the profile row is missing (signup trigger may have failed), insert one now
    if (error?.code === "PGRST116" || !data) {
      const { data: inserted, error: insertError } = await supabase
        .from("profiles")
        .insert({
          id:         user.id,
          email:      user.email ?? null,
          // full_name is NOT NULL in the schema — fall back to "Patient" to satisfy constraint
          full_name:  (user.user_metadata?.full_name as string | undefined) ?? "Patient",
          // date_of_birth is NOT NULL — use placeholder; user can update it later
          date_of_birth: (user.user_metadata?.date_of_birth as string | undefined) ?? "1990-01-01",
        })
        .select("full_name, email, date_of_birth, abha_number, preferred_language")
        .single();

      console.log("[settings] profiles INSERT result:", { inserted, insertError });

      if (insertError || !inserted) {
        setProfileState("error");
        return;
      }
      data  = inserted;
      error = null;
    }

    if (error || !data) {
      console.log("[settings] falling through to error state. error:", error);
      setProfileState("error");
      return;
    }

    // 4. profiles.email may be null if signup didn't copy it — fall back to auth email
    const merged: Profile = {
      ...(data as Profile),
      email: (data as Profile).email ?? user.email ?? null,
    };
    console.log("[settings] merged profile:", merged);
    console.log("[settings] calling setSelectedLang with:", merged.preferred_language ?? "en-IN");
    setProfile(merged);
    setSelectedLang(merged.preferred_language ?? "en-IN");
    setProfileState("loaded");
  }, []);

  useEffect(() => { void loadProfile(); }, [loadProfile]);

  // ── Save language ────────────────────────────────────────────────────────────

  async function handleSaveLanguage() {
    setSavingLang(true);
    const supabase = createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) { setSavingLang(false); return; }

    const { error } = await supabase
      .from("profiles")
      .update({ preferred_language: selectedLang })
      .eq("id", user.id);

    if (error) {
      toast.error("Could not save language preference.");
      setSavingLang(false);
      return;
    }

    // Set locale cookie and reload — next-intl picks it up server-side
    document.cookie = `medisync_locale=${selectedLang}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`;
    toast.success(t("saved"));

    // Short delay so the toast is visible before reload
    setTimeout(() => window.location.reload(), 800);
  }

  // ── Delete account ────────────────────────────────────────────────────────────

  async function handleDeleteAccount() {
    setDeleting(true);
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { setDeleting(false); return; }

    try {
      await api.delete<{ deleted: boolean }>("/profile/", session.access_token);
      // Sign out the frontend session, then redirect to the landing page
      await supabase.auth.signOut();
      window.location.href = "/";
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not delete account.");
      setDeleting(false);
      setShowDeleteDialog(false);
    }
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────

  // Returns null (not "—") for missing dates so ReadOnlyField shows the notProvided placeholder
  function formatDate(iso: string | null): string | null {
    if (!iso) return null;
    // Use the current locale for culturally-appropriate date formatting
    return new Date(iso).toLocaleDateString(locale, {
      day: "numeric", month: "long", year: "numeric",
    });
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 max-w-2xl">

      {/* ── Page header ──────────────────────────────────────────────────────── */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t("subtitle")}</p>
      </div>

      {/* ── 1. Language preference ────────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("language_section")}</CardTitle>
          <CardDescription className="text-sm">{t("language_hint")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="lang-select" className="text-sm font-medium">
              {t("language_label")}
            </label>
            {loadingProfile ? (
              <Skeleton className="h-10 w-full" />
            ) : (
              <select
                id="lang-select"
                value={selectedLang}
                onChange={(e) => setSelectedLang(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {LANGUAGE_OPTIONS.map(({ code, label }) => (
                  <option key={code} value={code}>{label}</option>
                ))}
              </select>
            )}
          </div>
          <Button
            onClick={handleSaveLanguage}
            disabled={savingLang || loadingProfile}
            className="w-full sm:w-auto"
          >
            {savingLang && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
            {t("save_language")}
          </Button>
        </CardContent>
      </Card>

      {/* ── 2. Account info (read-only) ───────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("account_section")}</CardTitle>
          <CardDescription className="text-sm">{t("readonly_hint")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {profileState === "loading" ? (
            <>
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </>
          ) : profileState === "error" ? (
            <p className="text-sm text-destructive">{t("profile_error")}</p>
          ) : (
            <>
              <ReadOnlyField label={t("name_label")}  value={profile?.full_name}                          notProvided={t("not_provided")} />
              <ReadOnlyField label={t("email_label")} value={profile?.email}                              notProvided={t("not_provided")} />
              <ReadOnlyField label={t("dob_label")}   value={formatDate(profile?.date_of_birth ?? null)}  notProvided={t("not_provided")} />
              <ReadOnlyField label={t("abha_label")}  value={profile?.abha_number}                        notProvided={t("not_provided")} />
            </>
          )}
        </CardContent>
      </Card>

      {/* ── 3. Danger zone ────────────────────────────────────────────────────── */}
      <Card className="border-red-200">
        <CardHeader>
          <CardTitle className="text-base text-destructive flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            {t("danger_section")}
          </CardTitle>
          <CardDescription className="text-sm">{t("delete_hint")}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="destructive"
            onClick={() => setShowDeleteDialog(true)}
            aria-label={t("delete_account")}
          >
            {t("delete_account")}
          </Button>
        </CardContent>
      </Card>

      <Separator />
      <p className="text-xs text-muted-foreground">{t("language_footer")}</p>

      {/* ── Delete account confirmation dialog ────────────────────────────────── */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("delete_confirm_title")}</DialogTitle>
            <DialogDescription>{t("delete_confirm_desc")}</DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              variant="outline"
              onClick={() => setShowDeleteDialog(false)}
              disabled={deleting}
            >
              {/* common.cancel already exists in all 11 language files */}
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteAccount}
              disabled={deleting}
            >
              {deleting && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
              {deleting ? t("deleting") : t("delete_permanently")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Read-only field helper ─────────────────────────────────────────────────────

function ReadOnlyField({
  label,
  value,
  notProvided,
}: {
  label:       string;
  value:       string | null | undefined;
  notProvided: string;
}) {
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</p>
      <div className="rounded-md border border-input bg-muted/40 px-3 py-2 text-sm">
        {value || <span className="text-muted-foreground italic">{notProvided}</span>}
      </div>
    </div>
  );
}
