"use client";

/**
 * Sign-up page.
 *
 * Flow:
 *   1. Collect full_name, date_of_birth, abha_number (optional), email, password.
 *   2. Call supabase.auth.signUp() — passes name/DOB/ABHA as user metadata so
 *      the DB trigger can create the profiles row as a fallback.
 *   3. After signup, explicitly insert/upsert the profiles row (full data wins
 *      over the trigger's defaults).
 *   4. Redirect to /dashboard.
 *
 * Email confirmation: disabled in Supabase dashboard for the hackathon
 * (Authentication → Settings → disable "Enable email confirmations").
 * If confirmations are enabled, show a "check your email" message instead.
 */

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Heart, Eye, EyeOff, Loader2, Info } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { createClient } from "@/lib/supabase";

export default function SignUpPage() {
  const router = useRouter();

  const [fullName,    setFullName]    = useState("");
  const [dob,         setDob]         = useState("");            // "YYYY-MM-DD"
  const [abha,        setAbha]        = useState("");            // optional 14-digit
  const [email,       setEmail]       = useState("");
  const [password,    setPassword]    = useState("");
  const [showPw,      setShowPw]      = useState(false);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState<string | null>(null);
  const [needsVerify, setNeedsVerify] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    // Basic ABHA validation: must be exactly 14 digits if provided
    if (abha && !/^\d{14}$/.test(abha.replace(/-/g, ""))) {
      setError("ABHA number must be exactly 14 digits.");
      return;
    }

    setLoading(true);
    const supabase = createClient();

    // Step 1: Create the auth user.
    // We pass metadata so the DB trigger handle_new_user() can create a
    // profiles row even if step 2 fails.
    const { data: signupData, error: signupError } = await supabase.auth.signUp({
      email:    email.trim(),
      password,
      options: {
        data: {
          full_name:     fullName.trim(),
          date_of_birth: dob,
          abha_number:   abha.trim() || null,
        },
      },
    });

    if (signupError) {
      setError(signupError.message);
      setLoading(false);
      return;
    }

    // If Supabase requires email confirmation the session will be null
    if (!signupData.session) {
      setNeedsVerify(true);
      setLoading(false);
      return;
    }

    // Step 2: Upsert the profiles row with full data.
    // ON CONFLICT (id) DO UPDATE ensures we overwrite any trigger-created row.
    const userId = signupData.user!.id;
    const { error: profileError } = await supabase.from("profiles").upsert({
      id:            userId,
      full_name:     fullName.trim(),
      date_of_birth: dob,
      abha_number:   abha.trim() || null,
    });

    if (profileError) {
      // Non-fatal: the trigger fallback already created the row.
      // Log for debugging but continue.
      console.warn("Profile upsert warning:", profileError.message);
    }

    router.push("/dashboard");
    router.refresh();
  }

  if (needsVerify) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>Check your email</CardTitle>
            <CardDescription>
              We sent a confirmation link to <strong>{email}</strong>.
              Click it to activate your account, then{" "}
              <Link href="/login" className="text-primary underline underline-offset-4">
                sign in
              </Link>.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4 py-8">
      <div className="w-full max-w-sm space-y-6">

        {/* Logo */}
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="flex items-center gap-2 text-primary font-semibold text-xl">
            <Heart className="h-6 w-6 fill-primary" aria-hidden="true" />
            MediSync
          </div>
          <p className="text-sm text-muted-foreground">Your health ledger</p>
        </div>

        <form onSubmit={handleSubmit}>
          <Card>
            <CardHeader>
              <CardTitle>Create account</CardTitle>
              <CardDescription>
                Your medical records, always in your control.
              </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4">
              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              {/* Full name */}
              <div className="space-y-1.5">
                <Label htmlFor="fullName">Full name</Label>
                <Input
                  id="fullName"
                  type="text"
                  placeholder="Ananya Sharma"
                  autoComplete="name"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>

              {/* Date of birth */}
              <div className="space-y-1.5">
                <Label htmlFor="dob">Date of birth</Label>
                <Input
                  id="dob"
                  type="date"
                  required
                  value={dob}
                  onChange={(e) => setDob(e.target.value)}
                  max={new Date().toISOString().split("T")[0]}  // no future dates
                />
              </div>

              {/* ABHA number (optional) */}
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5">
                  <Label htmlFor="abha">ABHA number</Label>
                  <span className="text-xs text-muted-foreground">(optional)</span>
                </div>
                <Input
                  id="abha"
                  type="text"
                  placeholder="14-digit Health ID"
                  inputMode="numeric"
                  pattern="[\d-]{14,17}"
                  maxLength={17}
                  value={abha}
                  onChange={(e) => setAbha(e.target.value)}
                />
                <p className="text-xs text-muted-foreground flex items-start gap-1">
                  <Info className="h-3 w-3 mt-0.5 shrink-0" aria-hidden="true" />
                  Your 14-digit ABDM Health ID. Verification happens in settings.
                </p>
              </div>

              {/* Email */}
              <div className="space-y-1.5">
                <Label htmlFor="email">Email address</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              {/* Password */}
              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPw ? "text" : "password"}
                    placeholder="At least 8 characters"
                    autoComplete="new-password"
                    required
                    minLength={8}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="pr-10"
                  />
                  <button
                    type="button"
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    onClick={() => setShowPw((s) => !s)}
                    aria-label={showPw ? "Hide password" : "Show password"}
                  >
                    {showPw
                      ? <EyeOff className="h-4 w-4" aria-hidden="true" />
                      : <Eye    className="h-4 w-4" aria-hidden="true" />
                    }
                  </button>
                </div>
              </div>
            </CardContent>

            <CardFooter className="flex flex-col gap-3">
              <Button type="submit" className="w-full" disabled={loading}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
                {loading ? "Creating account…" : "Create account"}
              </Button>
            </CardFooter>
          </Card>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link href="/login" className="text-primary underline underline-offset-4">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
