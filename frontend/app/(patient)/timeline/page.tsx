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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import {
  Hospital, User, CalendarDays, Search, SlidersHorizontal,
  FileText, AlertCircle, FileUp, Share2, Printer, Loader2,
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
import { cn } from "@/lib/utils";
import type { RecordType } from "@/lib/types";
import { ShareDialog } from "@/components/ShareDialog";

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

// Shape of GET /records/{id}'s `record` field — only what Export/Print needs.
interface PrintRecordDetail {
  id:        string;
  title:     string;
  file_path: string | null;
  file_url:  string | null;
}

interface PrintDoc {
  id:       string;
  title:    string;
  fileUrl:  string;
  isImage:  boolean;
}

// Mirrors record/[id]/page.tsx's isImageFile — same extension check, local
// copy since it's a small pure function and neither page currently shares
// helpers via lib/.
function isImageFile(fileUrl: string | null, filePath: string | null): boolean {
  const src = fileUrl ?? filePath ?? "";
  const ext = src.split("?")[0].split(".").pop()?.toLowerCase() ?? "";
  return ext === "jpg" || ext === "jpeg" || ext === "png";
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

  // Select-to-share mode
  const [selectMode,  setSelectMode]  = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Export/Print PDF (same selection, separate action)
  const [exporting, setExporting] = useState(false);
  const [printDocs, setPrintDocs] = useState<PrintDoc[]>([]);
  // Resolvers for each doc's onLoad, populated right before the print-only
  // container renders so the JSX's onLoad handlers can always find them.
  const loadResolversRef = useRef<Map<string, () => void>>(new Map());

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

  function toggleRecord(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function exitSelectMode() {
    setSelectMode(false);
    setSelectedIds(new Set());
  }

  // ── Export / Print PDF ──────────────────────────────────────────────────────
  //
  // Prints ONLY the original uploaded documents for the selected records — no
  // app chrome, no AI summaries, no lab/med tables (see the @media print rules
  // in globals.css). There's no batch signed-URL endpoint, so we fetch a fresh
  // file_url per record via GET /records/{id}, capped at a modest concurrency.
  //
  // window.print() is used instead of jsPDF/html2canvas: those rasterise via
  // <canvas>, which taints on cross-origin Supabase signed URLs and fails.
  // Images are embedded directly; PDFs via <iframe> (shipped, not the
  // full-page-link-list fallback — see report).

  async function handleExportPrint() {
    setExporting(true);

    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { setExporting(false); return; }

    const ids = Array.from(selectedIds);
    const docs: PrintDoc[] = [];

    // Fetch fresh signed URLs in capped-concurrency batches, not one big
    // Promise.all — keeps this well-behaved for larger selections.
    const CONCURRENCY = 4;
    for (let i = 0; i < ids.length; i += CONCURRENCY) {
      const batch = ids.slice(i, i + CONCURRENCY);
      const results = await Promise.all(
        batch.map(async (id): Promise<PrintDoc | null> => {
          try {
            const res = await api.get<{ record: PrintRecordDetail }>(
              `/records/${id}`,
              session.access_token,
            );
            if (!res.record.file_url) return null;
            return {
              id:      res.record.id,
              title:   res.record.title,
              fileUrl: res.record.file_url,
              isImage: isImageFile(res.record.file_url, res.record.file_path),
            };
          } catch {
            return null;   // skip records whose fetch/signing failed
          }
        }),
      );
      docs.push(...results.filter((d): d is PrintDoc => d !== null));
    }

    if (docs.length === 0) {
      toast.error("None of the selected records have a printable document.");
      setExporting(false);
      return;
    }

    // Populate resolvers BEFORE mounting the print container — the onLoad/
    // onError handlers in the JSX below read from this ref by id, so it must
    // already hold an entry for every doc by the time the browser fires load.
    loadResolversRef.current = new Map();
    const loadPromises = docs.map(
      (doc) =>
        new Promise<void>((resolve) => {
          loadResolversRef.current.set(doc.id, resolve);
          // Fallback: cross-origin PDF iframes don't always fire onLoad
          // reliably — don't let one stuck doc block printing forever.
          setTimeout(resolve, 4000);
        }),
    );

    setPrintDocs(docs);
    await Promise.all(loadPromises);

    window.print();
    setExporting(false);

    // Drop the (signed-URL-bearing) print content once the print dialog
    // closes, rather than leaving it sitting in the DOM indefinitely.
    const cleanup = () => {
      setPrintDocs([]);
      window.removeEventListener("afterprint", cleanup);
    };
    window.addEventListener("afterprint", cleanup);
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
    <div className={cn("space-y-6", selectMode && selectedIds.size > 0 && "pb-24")}>

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t("subtitle")}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* Select mode toggle */}
          <Button
            variant={selectMode ? "default" : "outline"}
            size="sm"
            onClick={() => (selectMode ? exitSelectMode() : setSelectMode(true))}
            className="shrink-0"
          >
            {selectMode ? "Cancel" : "Share records"}
          </Button>
          {/* Filters panel toggle */}
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
            <TimelineItem
              key={record.id}
              record={record}
              selectMode={selectMode}
              selected={selectedIds.has(record.id)}
              onToggle={toggleRecord}
            />
          ))}
        </div>
      )}
    </div>

    {/* ── Sticky action bar (shown when 1+ records selected) ──────────────────── */}
    {selectMode && selectedIds.size > 0 && (
      <div className="fixed bottom-0 left-0 right-0 z-50 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 p-4">
        <div className="container flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-sm font-medium text-foreground">
            {selectedIds.size} record{selectedIds.size !== 1 ? "s" : ""} selected
          </span>
          <div className="flex items-center gap-2 flex-wrap">
            <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>
              Clear
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void handleExportPrint()}
              disabled={exporting}
              aria-label="Export or print the original documents for the selected records"
            >
              {exporting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                  Preparing…
                </>
              ) : (
                <>
                  <Printer className="mr-2 h-4 w-4" aria-hidden="true" />
                  Export / Print PDF
                </>
              )}
            </Button>
            <ShareDialog
              recordIds={Array.from(selectedIds)}
              trigger={
                <Button size="sm">
                  <Share2 className="mr-2 h-4 w-4" aria-hidden="true" />
                  Share selected →
                </Button>
              }
              onCreated={exitSelectMode}
            />
          </div>
        </div>
      </div>
    )}

    {/* ── Print-only container (Export/Print PDF) ──────────────────────────────
        Hidden on screen; shown ONLY under @media print via globals.css, which
        also hides everything else on the page. One document per printed page. */}
    <div id="print-export-root" className="hidden">
      {printDocs.map((doc) => (
        <div key={doc.id} className="print-page">
          <p className="print-page-title">{doc.title}</p>
          {doc.isImage ? (
            // eslint-disable-next-line @next/next/no-img-element -- print-only content, not a Next-optimised asset
            <img
              src={doc.fileUrl}
              alt={doc.title}
              onLoad={() => loadResolversRef.current.get(doc.id)?.()}
              onError={() => loadResolversRef.current.get(doc.id)?.()}
            />
          ) : (
            <iframe
              src={doc.fileUrl}
              title={doc.title}
              onLoad={() => loadResolversRef.current.get(doc.id)?.()}
            />
          )}
        </div>
      ))}
    </div>
    </>
  );
}

// ── Timeline item component ────────────────────────────────────────────────────

function TimelineItem({
  record,
  selectMode,
  selected,
  onToggle,
}: {
  record:     TimelineRecord;
  selectMode: boolean;
  selected:   boolean;
  onToggle:   (id: string) => void;
}) {
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

  const cardContent = (
    <Card className={cn(
      "hover:shadow-md transition-shadow cursor-pointer",
      selected && "ring-2 ring-primary ring-offset-1",
    )}>
      <CardContent className="flex items-start gap-4 py-4">

        {/* Checkbox — visible in select mode */}
        {selectMode && (
          <div className="flex items-center shrink-0 pt-1">
            <input
              type="checkbox"
              readOnly
              checked={selected}
              tabIndex={-1}
              aria-hidden="true"
              className="h-4 w-4 rounded border-input accent-primary cursor-pointer"
            />
          </div>
        )}

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

        {/* Arrow hint — hidden in select mode */}
        {!selectMode && (
          <FileText className="h-4 w-4 text-muted-foreground shrink-0 mt-1" aria-hidden="true" />
        )}
      </CardContent>
    </Card>
  );

  if (selectMode) {
    return (
      <div
        role="checkbox"
        aria-checked={selected}
        aria-label={record.title}
        tabIndex={0}
        onClick={() => onToggle(record.id)}
        onKeyDown={(e) => {
          if (e.key === " " || e.key === "Enter") {
            e.preventDefault();
            onToggle(record.id);
          }
        }}
        className="block rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {cardContent}
      </div>
    );
  }

  return (
    <Link
      href={`/record/${record.id}`}
      className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg"
    >
      {cardContent}
    </Link>
  );
}
