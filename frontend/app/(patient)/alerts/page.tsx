"use client";

/**
 * /alerts — Drug interaction alert list.
 *
 * Sections:
 *   1. Header + "Re-run check" button
 *   2. Active (unacknowledged) alerts — sorted major → moderate → minor
 *   3. Reviewed (acknowledged) alerts — collapsible
 *
 * Severity is encoded by both colour AND text label (never colour alone).
 *   major    → red destructive badge
 *   moderate → amber badge
 *   minor    → slate secondary badge
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  TriangleAlert, RefreshCw, CheckCircle2,
  ChevronDown, ChevronUp, AlertCircle, Loader2,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { createClient } from "@/lib/supabase";
import { conflictsApi } from "@/lib/api";
import type { DrugConflict, ConflictSeverity } from "@/lib/types";

// ── Severity display config (label filled in at render time via translations) ──

const SEV_CONFIG: Record<
  ConflictSeverity,
  {
    badgeClass:  string;
    cardClass:   string;
    iconClass:   string;
  }
> = {
  major: {
    badgeClass: "bg-red-100 text-red-800 border-red-300",
    cardClass:  "border-red-200 bg-red-50",
    iconClass:  "text-red-600",
  },
  moderate: {
    badgeClass: "bg-amber-100 text-amber-800 border-amber-300",
    cardClass:  "border-amber-200 bg-amber-50",
    iconClass:  "text-amber-600",
  },
  minor: {
    badgeClass: "bg-slate-100 text-slate-700 border-slate-300",
    cardClass:  "border-slate-200 bg-white",
    iconClass:  "text-slate-500",
  },
};

const SEV_ORDER: Record<ConflictSeverity, number> = {
  major: 0, moderate: 1, minor: 2,
};

// ── Conflict card ─────────────────────────────────────────────────────────────

function ConflictCard({
  conflict,
  onAcknowledge,
  acknowledging,
  severityLabel,
  actionLabel,
  mechanismLabel,
  detectedLabel,
  reviewedLabel,
  acknowledgeLabel,
}: {
  conflict:        DrugConflict;
  onAcknowledge:   (id: string) => void;
  acknowledging:   boolean;
  severityLabel:   string;
  actionLabel:     string;
  mechanismLabel:  string;
  detectedLabel:   string;
  reviewedLabel:   string;
  acknowledgeLabel: string;
}) {
  const sev = conflict.severity in SEV_CONFIG
    ? conflict.severity
    : ("minor" as ConflictSeverity);
  const cfg = SEV_CONFIG[sev];

  return (
    <Card className={`border ${cfg.cardClass}`}>
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <TriangleAlert
              className={`h-4 w-4 shrink-0 ${cfg.iconClass}`}
              aria-hidden="true"
            />
            <span className="font-semibold text-sm">
              {conflict.drug_a} + {conflict.drug_b}
            </span>
            <span
              className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${cfg.badgeClass}`}
              aria-label={`Severity: ${severityLabel}`}
            >
              {severityLabel}
            </span>
          </div>

          {!conflict.is_acknowledged && (
            <Button
              variant="outline"
              size="sm"
              className="shrink-0 h-7 text-xs"
              disabled={acknowledging}
              onClick={() => onAcknowledge(conflict.id)}
              aria-label={`Acknowledge interaction between ${conflict.drug_a} and ${conflict.drug_b}`}
            >
              {acknowledging ? (
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
              ) : (
                <CheckCircle2 className="h-3 w-3 mr-1" aria-hidden="true" />
              )}
              {acknowledgeLabel}
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className="px-4 pb-4 space-y-1.5">
        {(conflict.explanation ?? conflict.description) && (
          <p className="text-sm text-foreground/80">
            {conflict.explanation ?? conflict.description}
          </p>
        )}
        {conflict.recommendation && (
          <p className="text-sm text-foreground/80">
            <span className="font-medium">{actionLabel} </span>
            {conflict.recommendation}
          </p>
        )}
        {conflict.mechanism && (
          <p className="text-xs text-muted-foreground">
            <span className="font-medium">{mechanismLabel}</span> {conflict.mechanism}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          {detectedLabel} {new Date(conflict.detected_at).toLocaleDateString("en-IN", {
            day: "numeric", month: "short", year: "numeric",
          })}
          {conflict.is_acknowledged && (
            <span className="ml-2 text-green-700 font-medium">· {reviewedLabel}</span>
          )}
        </p>
      </CardContent>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AlertsPage() {
  const t = useTranslations("alerts");

  const [conflicts,      setConflicts]      = useState<DrugConflict[]>([]);
  const [loading,        setLoading]        = useState(true);
  const [rechecking,     setRechecking]     = useState(false);
  const [acknowledging,  setAcknowledging]  = useState<string | null>(null);
  const [showReviewed,   setShowReviewed]   = useState(false);
  const [error,          setError]          = useState<string | null>(null);

  const loadConflicts = useCallback(async () => {
    setLoading(true);
    setError(null);
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { setLoading(false); return; }

    try {
      const data = await conflictsApi.list(session.access_token);
      setConflicts(data.conflicts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load alerts.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadConflicts(); }, [loadConflicts]);

  async function handleRecheck() {
    setRechecking(true);
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { setRechecking(false); return; }

    try {
      const result = await conflictsApi.recheck(session.access_token);
      if (result.count > 0) {
        toast.warning(`Found ${result.count} new interaction(s).`);
        await loadConflicts();
      } else {
        toast.success("No new interactions detected.");
      }
    } catch {
      toast.error("Re-check failed. Please try again.");
    } finally {
      setRechecking(false);
    }
  }

  async function handleAcknowledge(conflictId: string) {
    setAcknowledging(conflictId);
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { setAcknowledging(null); return; }

    try {
      await conflictsApi.acknowledge(conflictId, session.access_token);
      setConflicts((prev) =>
        prev.map((c) =>
          c.id === conflictId ? { ...c, is_acknowledged: true } : c
        )
      );
      // Notify the nav bar to re-fetch the alert dot count
      window.dispatchEvent(new Event("medisync:alerts-update"));
      toast.success("Alert marked as reviewed.");
    } catch {
      toast.error("Could not acknowledge alert. Please try again.");
    } finally {
      setAcknowledging(null);
    }
  }

  // Split into active vs reviewed and sort within each group
  const active = conflicts
    .filter((c) => !c.is_acknowledged)
    .sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity]);

  const reviewed = conflicts
    .filter((c) => c.is_acknowledged)
    .sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity]);

  return (
    <div className="space-y-6">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {t("subtitle")}{" "}
            <Link href="/dashboard" className="text-primary hover:underline">
              {t("go_to_dashboard")}
            </Link>
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRecheck}
          disabled={rechecking || loading}
          aria-label={t("rerun")}
        >
          <RefreshCw
            className={`h-4 w-4 mr-2 ${rechecking ? "animate-spin" : ""}`}
            aria-hidden="true"
          />
          {t("rerun")}
        </Button>
      </div>

      {/* ── Error ──────────────────────────────────────────────────────────── */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* ── Loading skeletons ───────────────────────────────────────────────── */}
      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardHeader className="pb-3">
                <Skeleton className="h-5 w-56" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-10 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* ── Active alerts ───────────────────────────────────────────────────── */}
      {!loading && (
        <>
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold tracking-tight">
                {t("active_alerts")}
              </h2>
              {active.length > 0 && (
                <Badge variant="destructive" className="text-xs">
                  {active.length}
                </Badge>
              )}
            </div>

            {active.length === 0 ? (
              <Card>
                <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
                  <CheckCircle2 className="h-8 w-8 text-green-600" aria-hidden="true" />
                  <p className="font-medium">{t("no_active")}</p>
                  <p className="text-sm text-muted-foreground">{t("no_active_hint")}</p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {active.map((c) => (
                  <ConflictCard
                    key={c.id}
                    conflict={c}
                    onAcknowledge={handleAcknowledge}
                    acknowledging={acknowledging === c.id}
                    severityLabel={t(`severity_${c.severity}`)}
                    actionLabel={t("action_label")}
                    mechanismLabel={t("mechanism_label")}
                    detectedLabel={t("detected")}
                    reviewedLabel={t("reviewed_badge")}
                    acknowledgeLabel={t("acknowledge")}
                  />
                ))}
              </div>
            )}
          </div>

          {/* ── Reviewed alerts ─────────────────────────────────────────────── */}
          {reviewed.length > 0 && (
            <div className="space-y-3">
              <button
                type="button"
                className="flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => setShowReviewed((v) => !v)}
                aria-expanded={showReviewed}
              >
                {showReviewed ? (
                  <ChevronUp className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <ChevronDown className="h-4 w-4" aria-hidden="true" />
                )}
                {t("reviewed")} ({reviewed.length})
              </button>

              {showReviewed && (
                <div className="space-y-3 opacity-70">
                  {reviewed.map((c) => (
                    <ConflictCard
                      key={c.id}
                      conflict={c}
                      onAcknowledge={handleAcknowledge}
                      acknowledging={acknowledging === c.id}
                      severityLabel={t(`severity_${c.severity}`)}
                      actionLabel={t("action_label")}
                      mechanismLabel={t("mechanism_label")}
                      detectedLabel={t("detected")}
                      reviewedLabel={t("reviewed_badge")}
                      acknowledgeLabel={t("acknowledge")}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
