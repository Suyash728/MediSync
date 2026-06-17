"use client";

/**
 * Patient dashboard — home screen after login.
 *
 * Sections (top → bottom):
 *   1. Stat cards: total records, active medications, open drug-conflict alerts
 *   2. Active drug-conflict alerts (if any) — surfaced prominently
 *   3. Upload zone
 *   4. Recent records (last 5) with link to full Timeline
 *
 * All DB reads go through either the FastAPI backend (records list) or the
 * Supabase browser client (counts, conflicts) — both respect RLS.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  FileText, Pill, TriangleAlert,
  Loader2, FileUp, AlertCircle, ChevronRight,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { UploadZone } from "@/components/UploadZone";
import { RecordCard } from "@/components/RecordCard";
import { WelcomeModal } from "@/components/WelcomeModal";
import { createClient } from "@/lib/supabase";
import { api } from "@/lib/api";
import type { RecordType, ConflictSeverity } from "@/lib/types";

// ── Local types ───────────────────────────────────────────────────────────────

interface RecordRow {
  id:                string;
  record_type:       RecordType;
  title:             string;
  document_date:     string | null;
  facility:          string | null;
  doctor:            string | null;
  summary:           string | null;
  processing_status: string;
  processing_error:  string | null;
  // counts are optional — we skip enrichment on the dashboard for speed
  medication_count?:   number;
  lab_value_count?:    number;
  abnormal_lab_count?: number;
}

interface DrugConflict {
  id:              string;
  drug_a:          string;
  drug_b:          string;
  severity:        ConflictSeverity;
  mechanism:       string | null;
  description:     string | null;
  explanation:     string | null;
  recommendation:  string | null;
  is_acknowledged: boolean;
  detected_at:     string;
}

// Badge variant per conflict severity (colour + text label — never colour alone)
const SEVERITY_VARIANT: Record<ConflictSeverity, "secondary" | "warning" | "destructive"> = {
  minor:    "secondary",
  moderate: "warning",
  major:    "destructive",
};

// ── Stat card component ───────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  icon: Icon,
  loading,
  accent = false,
}: {
  label:   string;
  value:   number;
  // Use the broad lucide prop type to avoid aria-hidden variance issues
  icon:    React.ComponentType<React.SVGProps<SVGSVGElement>>;
  loading: boolean;
  accent?: boolean;   // amber colour for the alert count card
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 pt-6 pb-6">
        <div className={`rounded-lg p-3 ${accent ? "bg-amber-100" : "bg-primary/10"}`}>
          <Icon
            className={`h-5 w-5 ${accent ? "text-amber-700" : "text-primary"}`}
            aria-hidden="true"
          />
        </div>
        <div className="min-w-0">
          {loading ? (
            <Skeleton className="h-7 w-10 mb-1" />
          ) : (
            <p className="text-2xl font-bold tracking-tight">{value}</p>
          )}
          <p className="text-xs text-muted-foreground truncate">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Page component ─────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const t       = useTranslations("dashboard");
  const tCommon = useTranslations("common");

  const [records,       setRecords]       = useState<RecordRow[]>([]);
  const [totalRecords,  setTotalRecords]  = useState(0);
  const [activeMedCount, setActiveMedCount] = useState(0);
  const [conflicts,     setConflicts]     = useState<DrugConflict[]>([]);
  const [openAlerts,    setOpenAlerts]    = useState(0);

  const [loadingData, setLoadingData] = useState(true);
  const [error,       setError]       = useState<string | null>(null);

  // ── Load all dashboard data in parallel ─────────────────────────────────────

  const loadDashboard = useCallback(async () => {
    setLoadingData(true);
    setError(null);

    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { setLoadingData(false); return; }

    try {
      // Parallel: backend records list + three Supabase count queries
      const [recordsData, medResult, alertCountResult, conflictsResult] = await Promise.all([
        api.get<{ records: RecordRow[] }>("/records/", session.access_token),

        // Active medication count — direct Supabase (RLS enforces patient scope)
        supabase
          .from("medications")
          .select("id", { count: "exact", head: true })
          .eq("is_active", true),

        // Open (unacknowledged) drug-conflict count
        supabase
          .from("drug_conflicts")
          .select("id", { count: "exact", head: true })
          .eq("is_acknowledged", false),

        // Actual conflict rows to display (max 5)
        supabase
          .from("drug_conflicts")
          .select("*")
          .eq("is_acknowledged", false)
          .order("detected_at", { ascending: false })
          .limit(5),
      ]);

      const allRecords = recordsData.records;
      setTotalRecords(allRecords.length);
      setRecords(allRecords.slice(0, 5));   // show 5 most recent

      setActiveMedCount(medResult.count ?? 0);
      setOpenAlerts(alertCountResult.count ?? 0);
      setConflicts((conflictsResult.data as DrugConflict[]) ?? []);

    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard.");
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => { void loadDashboard(); }, [loadDashboard]);

  // ── After upload: prepend new record + refresh stats ────────────────────────

  function handleUploadSuccess(result: {
    record:         Record<string, unknown>;
    medications:    unknown[];
    lab_values:     unknown[];
    new_conflicts?: DrugConflict[];
  }) {
    const rec = result.record as unknown as RecordRow;
    setRecords((prev) => [rec, ...prev].slice(0, 5));
    setTotalRecords((n) => n + 1);
    setActiveMedCount((n) => n + result.medications.length);

    // Prepend newly detected conflicts to the dashboard widget
    const incoming = result.new_conflicts ?? [];
    if (incoming.length > 0) {
      setConflicts((prev) => [...incoming, ...prev].slice(0, 5));
      setOpenAlerts((n) => n + incoming.length);
    }

    // Notify the nav bar to re-fetch the alert dot count
    window.dispatchEvent(new Event("medisync:alerts-update"));
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-8">

      {/* First-login onboarding modal — shown once, dismissed persistently via DB flag */}
      <WelcomeModal />

      {/* ── Page header ──────────────────────────────────────────────────────── */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t("subtitle")}</p>
      </div>

      {/* ── Stat cards ───────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          label={t("total_records")}
          value={totalRecords}
          icon={FileText}
          loading={loadingData}
        />
        <StatCard
          label={t("active_medications")}
          value={activeMedCount}
          icon={Pill}
          loading={loadingData}
        />
        <StatCard
          label={t("conflict_alerts")}
          value={openAlerts}
          icon={TriangleAlert}
          loading={loadingData}
          accent={openAlerts > 0}
        />
      </div>

      {/* ── Drug-conflict alerts ──────────────────────────────────────────────── */}
      {conflicts.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold tracking-tight flex items-center gap-2">
              <TriangleAlert className="h-4 w-4 text-amber-600" aria-hidden="true" />
              {t("drug_alerts_section")}
            </h2>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/alerts" className="text-sm text-primary flex items-center gap-1">
                {tCommon("view_all")}
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
          </div>
          {conflicts.map((c) => (
            <Alert
              key={c.id}
              variant={c.severity === "major" ? "destructive" : "default"}
              className={
                c.severity === "major"
                  ? ""
                  : "border-amber-300 bg-amber-50 text-amber-900"
              }
            >
              <AlertTitle className="flex items-center gap-2 text-sm font-semibold">
                {c.drug_a} + {c.drug_b}
                <Badge variant={SEVERITY_VARIANT[c.severity]} className="text-xs capitalize">
                  {c.severity}
                </Badge>
              </AlertTitle>
              <AlertDescription className="mt-1 text-xs">
                {c.explanation ?? c.description}
              </AlertDescription>
            </Alert>
          ))}
        </div>
      )}

      {/* ── Error ─────────────────────────────────────────────────────────────── */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* ── Upload zone ───────────────────────────────────────────────────────── */}
      <div id="upload-zone">
        <UploadZone onSuccess={handleUploadSuccess} />
      </div>

      {/* ── Recent records ────────────────────────────────────────────────────── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold tracking-tight">{t("recent_records")}</h2>
            {loadingData && (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden="true" />
            )}
          </div>
          {totalRecords > 5 && (
            <Button variant="ghost" size="sm" asChild>
              <Link href="/timeline" className="flex items-center gap-1 text-sm text-primary">
                {tCommon("view_all")} {totalRecords}
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
          )}
        </div>

        {loadingData && (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full rounded-lg" />
            ))}
          </div>
        )}

        {!loadingData && records.length === 0 && !error && (
          <Card>
            <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
              <FileUp className="h-10 w-10 text-muted-foreground" aria-hidden="true" />
              <p className="font-medium text-muted-foreground">{t("no_records")}</p>
              <p className="text-sm text-muted-foreground">{t("no_records_hint")}</p>
            </CardContent>
          </Card>
        )}

        {!loadingData && records.length > 0 && (
          <div className="space-y-3">
            {records.map((rec) => (
              <RecordCard key={rec.id} {...rec} />
            ))}
            {totalRecords > 5 && (
              <Button variant="outline" className="w-full" asChild>
                <Link href="/timeline">
                  {t("view_all_records", { count: totalRecords })}
                  <ChevronRight className="ml-2 h-4 w-4" aria-hidden="true" />
                </Link>
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
