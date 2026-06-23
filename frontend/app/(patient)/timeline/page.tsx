"use client";

/**
 * Timeline page — chronological feed of all health records.
 *
 * Features:
 *   - Reverse-chronological list of every health_record for the patient.
 *   - Three client-side filters: record type, date range, free-text search
 *     (searches title + summary).
 *   - Skeleton loading state; empty states for "no records" and "no matches".
 *   - Clicking any row navigates to /record/[id].
 *
 * Data: fetched from GET /records/ via lib/api.ts (Bearer token forwarded).
 * Filtering: done client-side — the full record set is small enough that
 * a network round-trip per keystroke would be worse than local filtering.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  Hospital, User, CalendarDays, Search, SlidersHorizontal,
  FileText, AlertCircle, FileUp,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { createClient } from "@/lib/supabase";
import { api } from "@/lib/api";
import type { RecordType } from "@/lib/types";

// ── Types ─────────────────────────────────────────────────────────────────────

interface TimelineRecord {
  id:                string;
  record_type:       RecordType;
  title:             string;
  document_date:     string | null;
  facility:          string | null;
  doctor:            string | null;
  summary:           string | null;
  processing_status: string;
}

// Record type badge colour mapping (data, not labels — labels come from i18n)
const RECORD_TYPE_VARIANT: Record<RecordType, "default" | "secondary" | "outline"> = {
  prescription:       "default",
  lab_report:         "secondary",
  discharge_summary:  "secondary",
  imaging:            "outline",
  vaccination:        "outline",
  other:              "outline",
};

// All record type values (labels resolved inside the component via tCard)
const RECORD_TYPE_VALUES: RecordType[] = [
  "prescription", "lab_report", "discharge_summary", "imaging", "vaccination", "other",
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function TimelinePage() {
  const t     = useTranslations("timeline");
  const tCard = useTranslations("record_card");

  const [records,  setRecords]  = useState<TimelineRecord[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);

  // Filter state
  const [typeFilter,   setTypeFilter]   = useState<RecordType | "all">("all");
  const [searchQuery,  setSearchQuery]  = useState("");
  const [dateFrom,     setDateFrom]     = useState("");
  const [dateTo,       setDateTo]       = useState("");
  const [showFilters,  setShowFilters]  = useState(false);

  // ── Fetch all records ──────────────────────────────────────────────────────

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    setError(null);

    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { setLoading(false); return; }

    try {
      const data = await api.get<{ records: TimelineRecord[] }>(
        "/records/",
        session.access_token,
      );
      setRecords(data.records);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("no_records"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { void fetchRecords(); }, [fetchRecords]);

  // ── Client-side filtering ──────────────────────────────────────────────────
  //
  // Applied in order: type → date range → text search.
  // All comparisons are case-insensitive.

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();

    return records.filter((r) => {
      // Type filter
      if (typeFilter !== "all" && r.record_type !== typeFilter) return false;

      // Date range — document_date is "YYYY-MM-DD" or null
      if (dateFrom && r.document_date && r.document_date < dateFrom) return false;
      if (dateTo   && r.document_date && r.document_date > dateTo)   return false;

      // Text search over title and summary
      if (q) {
        const inTitle   = r.title.toLowerCase().includes(q);
        const inSummary = (r.summary ?? "").toLowerCase().includes(q);
        if (!inTitle && !inSummary) return false;
      }

      return true;
    });
  }, [records, typeFilter, searchQuery, dateFrom, dateTo]);

  // ── Active filter count (for the filter button badge) ─────────────────────

  const activeFilterCount = [
    typeFilter !== "all",
    !!dateFrom || !!dateTo,
  ].filter(Boolean).length;

  function clearFilters() {
    setTypeFilter("all");
    setSearchQuery("");
    setDateFrom("");
    setDateTo("");
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t("subtitle")}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowFilters((s) => !s)}
          className="shrink-0 flex items-center gap-2"
          aria-expanded={showFilters}
          aria-controls="timeline-filters"
        >
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          {t("filters")}
          {activeFilterCount > 0 && (
            <Badge variant="default" className="ml-1 h-5 w-5 rounded-full p-0 flex items-center justify-center text-[10px]">
              {activeFilterCount}
            </Badge>
          )}
        </Button>
      </div>

      {/* ── Search — always visible ──────────────────────────────────────────── */}
      <div className="relative">
        <Search
          className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          id="timeline-search"
          type="text"
          placeholder={t("search_placeholder")}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-9 w-full"
          aria-label={t("search")}
        />
      </div>

      {/* ── Filter panel (type + date range) ────────────────────────────────── */}
      {showFilters && (
        <Card id="timeline-filters">
          <CardContent className="pt-5 pb-5">
            <div className="grid gap-4 sm:grid-cols-2">

              {/* Record type */}
              <div className="space-y-1.5">
                <Label htmlFor="timeline-type">{t("record_type")}</Label>
                <select
                  id="timeline-type"
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value as RecordType | "all")}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="all">{t("all_types")}</option>
                  {RECORD_TYPE_VALUES.map((value) => (
                    <option key={value} value={value}>
                      {tCard(`type_${value}` as Parameters<typeof tCard>[0])}
                    </option>
                  ))}
                </select>
              </div>

              {/* Date range */}
              <div className="space-y-1.5">
                <Label>{t("date_range")}</Label>
                <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center">
                  <Input
                    type="date"
                    aria-label="From date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    max={dateTo || undefined}
                    className="text-xs"
                  />
                  <span className="text-muted-foreground text-xs shrink-0 hidden sm:inline">{t("to")}</span>
                  <Input
                    type="date"
                    aria-label="To date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    min={dateFrom || undefined}
                    className="text-xs"
                  />
                </div>
              </div>
            </div>

            {/* Clear filters */}
            {(activeFilterCount > 0 || !!searchQuery.trim()) && (
              <div className="mt-4 flex justify-end">
                <Button variant="ghost" size="sm" onClick={clearFilters}>
                  {t("clear_filters")}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Error ─────────────────────────────────────────────────────────────── */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* ── Results count ─────────────────────────────────────────────────────── */}
      {!loading && !error && records.length > 0 && (
        <p className="text-sm text-muted-foreground">
          {filtered.length === records.length
            ? t("record_count", { count: records.length })
            : t("record_count_filtered", { filtered: filtered.length, total: records.length })}
        </p>
      )}

      {/* ── Loading skeletons ─────────────────────────────────────────────────── */}
      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
      )}

      {/* ── Empty: no records at all ──────────────────────────────────────────── */}
      {!loading && !error && records.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <FileUp className="h-10 w-10 text-muted-foreground" aria-hidden="true" />
            <p className="font-medium text-muted-foreground">{t("no_records")}</p>
            <p className="text-sm text-muted-foreground">
              {t("no_records_hint").split("Dashboard")[0]}
              <Link href="/dashboard" className="text-primary underline underline-offset-4">
                Dashboard
              </Link>
              {t("no_records_hint").split("Dashboard")[1] ?? ""}
            </p>
          </CardContent>
        </Card>
      )}

      {/* ── Empty: filters matched nothing ────────────────────────────────────── */}
      {!loading && !error && records.length > 0 && filtered.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <Search className="h-10 w-10 text-muted-foreground" aria-hidden="true" />
            <p className="font-medium text-muted-foreground">{t("no_match")}</p>
            <Button variant="outline" size="sm" onClick={clearFilters}>
              {t("clear_filters")}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* ── Timeline list ─────────────────────────────────────────────────────── */}
      {!loading && filtered.length > 0 && (
        <div className="space-y-2">
          {filtered.map((record) => (
            <TimelineItem key={record.id} record={record} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Timeline item component ────────────────────────────────────────────────────

function TimelineItem({ record }: { record: TimelineRecord }) {
  const t     = useTranslations("timeline");
  const tCard = useTranslations("record_card");

  const typeLabel   = tCard(`type_${record.record_type}` as Parameters<typeof tCard>[0]) ?? record.record_type;
  const typeVariant = RECORD_TYPE_VARIANT[record.record_type] ?? "outline";

  const isPending    = record.processing_status === "pending" || record.processing_status === "processing";
  const isFailed     = record.processing_status === "failed";
  const needsReview  = record.processing_status === "needs_review";

  const formattedDate = record.document_date
    ? new Date(record.document_date).toLocaleDateString("en-IN", {
        day:   "numeric",
        month: "short",
        year:  "numeric",
      })
    : null;

  const summaryText = isFailed
    ? t("processing_failed")
    : isPending
    ? tCard("processing")
    : record.summary ?? tCard("no_summary");

  return (
    <Link
      href={`/record/${record.id}`}
      className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg"
    >
      <Card className="hover:shadow-md transition-shadow cursor-pointer">
        <CardContent className="flex items-start gap-4 py-4">

          {/* Month/year label column — anchors the dot on the timeline */}
          <div className="shrink-0 w-16 text-right hidden sm:block">
            {formattedDate ? (
              <span className="text-xs text-muted-foreground leading-snug">
                {new Date(record.document_date!).toLocaleDateString("en-IN", {
                  month: "short", year: "numeric",
                })}
              </span>
            ) : (
              <span className="text-xs text-muted-foreground">—</span>
            )}
          </div>

          {/* Divider dot */}
          <div className="flex flex-col items-center pt-1 shrink-0">
            <div className="h-2.5 w-2.5 rounded-full bg-primary" aria-hidden="true" />
            <div className="flex-1 w-px bg-border mt-1" aria-hidden="true" />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-sm truncate">{record.title}</span>
              <Badge variant={typeVariant} className="shrink-0 text-xs">
                {typeLabel}
              </Badge>
              {needsReview && (
                <Badge variant="warning" className="shrink-0 text-xs">
                  {t("needs_review_badge")}
                </Badge>
              )}
            </div>

            {/* Date + facility + doctor all on one horizontal row */}
            {(formattedDate || record.facility || record.doctor) && (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                {formattedDate && (
                  <span className="flex items-center gap-1">
                    <CalendarDays className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    {formattedDate}
                  </span>
                )}
                {record.facility && (
                  <span className="flex items-center gap-1">
                    <Hospital className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    {record.facility}
                  </span>
                )}
                {record.doctor && (
                  <span className="flex items-center gap-1">
                    <User className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    {record.doctor}
                  </span>
                )}
              </div>
            )}

            <p className="text-xs text-muted-foreground line-clamp-1">{summaryText}</p>
          </div>

          {/* Arrow hint */}
          <FileText className="h-4 w-4 text-muted-foreground shrink-0 mt-1" aria-hidden="true" />
        </CardContent>
      </Card>
    </Link>
  );
}
