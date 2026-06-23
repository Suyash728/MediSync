"use client";

/**
 * ShareDialog — create a time-limited, revocable share link for a clinician.
 *
 * Props:
 *   recordId    — when provided, scope defaults to "this record only"
 *   recordTitle — displayed in the dialog header for context
 *   trigger     — custom trigger element (defaults to a "Share" button)
 *   onCreated   — called after successful creation (e.g. to refresh grant list)
 */

import { useState } from "react";
import { Share2, Copy, Check, Link2, Loader2, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase";
import { shareApi } from "@/lib/api";
import type { RecordType } from "@/lib/types";

// ── Constants ──────────────────────────────────────────────────────────────────

// Scope options available when no specific record is pre-selected
const TYPE_SCOPE_OPTIONS: { value: RecordType; label: string }[] = [
  { value: "prescription",      label: "Prescriptions" },
  { value: "lab_report",        label: "Lab reports" },
  { value: "discharge_summary", label: "Discharge summaries" },
  { value: "imaging",           label: "Imaging reports" },
  { value: "vaccination",       label: "Vaccination records" },
];

const EXPIRY_OPTIONS = [
  { value: 7,  label: "7 days" },
  { value: 14, label: "14 days" },
  { value: 30, label: "30 days" },
];

// ── Types ──────────────────────────────────────────────────────────────────────

type ScopeMode = "all" | "type" | "record";

interface ShareDialogProps {
  recordId?:    string;
  recordTitle?: string;
  recordIds?:   string[];       // pre-selected IDs from multi-select; hides scope selector
  trigger?:     React.ReactNode;
  onCreated?:   () => void;
}

// ── Component ──────────────────────────────────────────────────────────────────

export function ShareDialog({
  recordId,
  recordTitle,
  recordIds,
  trigger,
  onCreated,
}: ShareDialogProps) {
  const [open,         setOpen]         = useState(false);
  const [step,         setStep]         = useState<"form" | "created">("form");
  const [submitting,   setSubmitting]   = useState(false);
  const [copied,       setCopied]       = useState(false);
  const [shareUrl,     setShareUrl]     = useState("");

  // Form state
  const [recipientName, setRecipientName] = useState("");
  // Default scope: lock to the provided record if recordId is set
  const [scopeMode,     setScopeMode]     = useState<ScopeMode>(recordId ? "record" : "all");
  const [scopeType,     setScopeType]     = useState<RecordType>("prescription");
  const [expiryDays,    setExpiryDays]    = useState(7);

  function resetAndClose() {
    setOpen(false);
    setStep("form");
    setRecipientName("");
    setScopeMode(recordId ? "record" : "all");
    setScopeType("prescription");
    setExpiryDays(7);
    setCopied(false);
    setShareUrl("");
  }

  async function handleSubmit() {
    setSubmitting(true);
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { setSubmitting(false); return; }

    try {
      // Build scope parameters — recordIds prop (multi-select) takes precedence
      const scopeRecordIds =
        recordIds && recordIds.length > 0
          ? recordIds
          : scopeMode === "record" && recordId
          ? [recordId]
          : null;
      const scopeRecordTypes = scopeMode === "type" ? [scopeType] : null;

      const { grant, token } = await shareApi.create(
        {
          recipient_name:     recipientName.trim() || null,
          scope_record_ids:   scopeRecordIds,
          scope_record_types: scopeRecordTypes,
          expires_in_days:    expiryDays,
        },
        session.access_token,
      );

      // Construct the full shareable URL using the current browser origin
      const url = `${window.location.origin}/clinician/shared/${token}`;
      setShareUrl(url);
      setStep("created");
      onCreated?.();
      logger_info(grant.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create share link.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy to clipboard.");
    }
  }

  // Logging the grant ID for the audit trail (frontend console only — not sensitive)
  function logger_info(grantId: string) {
    console.info("[ShareDialog] grant created:", grantId.slice(0, 8));
  }

  return (
    <>
      {/* Trigger — defaults to a "Share" button */}
      <span onClick={() => setOpen(true)}>
        {trigger ?? (
          <Button variant="outline" size="sm">
            <Share2 className="mr-2 h-4 w-4" aria-hidden="true" />
            Share
          </Button>
        )}
      </span>

      <Dialog open={open} onOpenChange={(v) => { if (!v) resetAndClose(); }}>
        <DialogContent className="sm:max-w-md">

          {step === "form" ? (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Share2 className="h-4 w-4 text-primary" aria-hidden="true" />
                  Share with a clinician
                </DialogTitle>
                <DialogDescription>
                  {recordTitle
                    ? `Create a read-only link for "${recordTitle}".`
                    : "Create a time-limited, read-only link for a clinician."}
                  {" "}The patient can revoke access at any time.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4 py-2">

                {/* Recipient name */}
                <div className="space-y-1.5">
                  <Label htmlFor="recipient">Recipient name (optional)</Label>
                  <Input
                    id="recipient"
                    placeholder="e.g. Dr. Sharma — Cardiology"
                    value={recipientName}
                    onChange={(e) => setRecipientName(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Used to label the link in your access history.
                  </p>
                </div>

                {/* Scope selector — hidden when specific records are pre-selected */}
                {recordIds && recordIds.length > 0 ? (
                  <div className="space-y-1.5">
                    <Label>What to share</Label>
                    <p className="text-sm text-muted-foreground">
                      Sharing{" "}
                      <span className="font-medium text-foreground">
                        {recordIds.length} selected record{recordIds.length !== 1 ? "s" : ""}
                      </span>
                      .
                    </p>
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    <Label>What to share</Label>
                    <div className="flex flex-wrap gap-2">
                      {recordId && (
                        <ScopePill
                          active={scopeMode === "record"}
                          onClick={() => setScopeMode("record")}
                        >
                          This record only
                        </ScopePill>
                      )}
                      <ScopePill
                        active={scopeMode === "all"}
                        onClick={() => setScopeMode("all")}
                      >
                        All records
                      </ScopePill>
                      <ScopePill
                        active={scopeMode === "type"}
                        onClick={() => setScopeMode("type")}
                      >
                        By type
                      </ScopePill>
                    </div>

                    {scopeMode === "type" && (
                      <div className="mt-2">
                        <select
                          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          value={scopeType}
                          onChange={(e) => setScopeType(e.target.value as RecordType)}
                          aria-label="Select record type to share"
                        >
                          {TYPE_SCOPE_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>
                )}

                {/* Expiry */}
                <div className="space-y-1.5">
                  <Label htmlFor="expiry">Link expires after</Label>
                  <select
                    id="expiry"
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    value={expiryDays}
                    onChange={(e) => setExpiryDays(Number(e.target.value))}
                  >
                    {EXPIRY_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={resetAndClose}>
                  Cancel
                </Button>
                <Button onClick={handleSubmit} disabled={submitting}>
                  {submitting ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Link2 className="mr-2 h-4 w-4" aria-hidden="true" />
                  )}
                  Create link
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2 text-green-700">
                  <Check className="h-4 w-4" aria-hidden="true" />
                  Share link created
                </DialogTitle>
                <DialogDescription>
                  Send this link to the clinician. They can view records without creating
                  an account. The link expires in {expiryDays} days.
                </DialogDescription>
              </DialogHeader>

              <div className="py-2 space-y-3">
                {/* Copyable link */}
                <div className="flex items-center gap-2">
                  <Input
                    readOnly
                    value={shareUrl}
                    className="font-mono text-xs"
                    aria-label="Shareable link"
                    onFocus={(e) => e.target.select()}
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={handleCopy}
                    aria-label="Copy link to clipboard"
                    className="shrink-0"
                  >
                    {copied ? (
                      <Check className="h-4 w-4 text-green-600" aria-hidden="true" />
                    ) : (
                      <Copy className="h-4 w-4" aria-hidden="true" />
                    )}
                  </Button>
                </div>

                <p className="text-xs text-muted-foreground">
                  You can revoke this link at any time from the{" "}
                  <a href="/share" className="text-primary hover:underline">
                    Share management page
                  </a>
                  .
                </p>
              </div>

              <DialogFooter>
                <Button onClick={resetAndClose}>
                  <X className="mr-2 h-4 w-4" aria-hidden="true" />
                  Done
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

// ── Small helper ───────────────────────────────────────────────────────────────

function ScopePill({
  active,
  onClick,
  children,
}: {
  active:   boolean;
  onClick:  () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        rounded-full border px-3 py-1 text-xs font-medium transition-colors
        ${active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-input bg-background text-foreground hover:bg-muted"}
      `}
    >
      {children}
    </button>
  );
}
