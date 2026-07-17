"use client";

/**
 * Record detail page — /record/[id]
 *
 * Shows the full detail of a single health_record:
 *   - Document preview (PDF → <iframe>, image → <img>, via signed Supabase URL)
 *   - LLM-generated clinical summary with a TTS "Listen" button (Sarvam AI)
 *   - Record metadata (date, facility, doctor, type)
 *   - Extracted medications table (with low-confidence warning badge)
 *   - Extracted lab values table (abnormal values highlighted in amber)
 *
 * TTS state machine: idle → loading → playing → paused
 *   Audio is fetched from the FastAPI backend's POST /tts/ (via ttsApi in
 *   lib/api.ts), which returns a signed Supabase Storage URL — played directly
 *   in an HTMLAudioElement, no blob/object-URL step needed.  The Sarvam API key
 *   lives server-side in the backend only.  TTS is omitted when no summary exists.
 *
 * Data: GET /records/{id} via lib/api.ts — returns record + medications + lab_values.
 * Security: the FastAPI endpoint verifies the patient_id, so another patient's
 * record ID will return 404.  The access_log row is written server-side on each view.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations, useLocale } from "next-intl";
import {
  ArrowLeft, CalendarDays, Hospital, User,
  Trash2, AlertCircle, FileText, Pill, FlaskConical,
  Volume2, Pause, Play, Square, Loader2, Download,
} from "lucide-react";
import { toast } from "sonner";

import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ShareDialog } from "@/components/ShareDialog";
import { PaidGate } from "@/components/AccessControl";
import { createClient } from "@/lib/supabase";
import { api, ttsApi, APIError } from "@/lib/api";
import type { RecordType } from "@/lib/types";

// ── Types mirroring the backend /records/{id} response ────────────────────────

interface RecordDetail {
  id:                string;
  patient_id:        string;
  record_type:       RecordType;
  title:             string;
  document_date:     string | null;
  facility:          string | null;
  doctor:            string | null;
  file_path:         string | null;
  file_url:          string | null;    // signed URL, valid for 1 hour
  raw_text:          string | null;
  summary:           string | null;
  processing_status: string;
  processing_error:  string | null;
  created_at:        string;
}

interface MedicationRow {
  id:               string;
  name:             string;
  dosage:           string | null;
  frequency:        string | null;
  duration:         string | null;
  is_active:        boolean;
  low_confidence:   boolean;
  document_date:    string | null;
}

interface LabValueRow {
  id:               string;
  test_name:        string;
  value:            string;
  unit:             string | null;
  reference_range:  string | null;
  reference_source: "lab_provided" | "standard" | null;
  is_abnormal:      boolean | null;
  document_date:    string | null;
}

interface RecordResponse {
  record:      RecordDetail;
  medications: MedicationRow[];
  lab_values:  LabValueRow[];
}

// ── TTS state ─────────────────────────────────────────────────────────────────

type TtsState = "idle" | "loading" | "playing" | "paused";

// ── Helpers ───────────────────────────────────────────────────────────────────

const RECORD_TYPE_LABELS: Record<RecordType, string> = {
  prescription:       "Prescription",
  lab_report:         "Lab Report",
  discharge_summary:  "Discharge Summary",
  imaging:            "Imaging",
  vaccination:        "Vaccination",
  other:              "Other",
};

const RECORD_TYPE_VARIANT: Record<RecordType, "default" | "secondary" | "outline"> = {
  prescription:       "default",
  lab_report:         "secondary",
  discharge_summary:  "secondary",
  imaging:            "outline",
  vaccination:        "outline",
  other:              "outline",
};

function isImageFile(fileUrl: string | null, filePath: string | null): boolean {
  const src = fileUrl ?? filePath ?? "";
  const ext = src.split("?")[0].split(".").pop()?.toLowerCase() ?? "";
  return ext === "jpg" || ext === "jpeg" || ext === "png";
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RecordDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const router = useRouter();
  const t      = useTranslations("record");
  const locale = useLocale();

  const [data,       setData]       = useState<RecordResponse | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState<string | null>(null);
  const [deleting,   setDeleting]   = useState(false);

  // TTS state
  const [ttsState,  setTtsState]  = useState<TtsState>("idle");
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // ── Fetch record ────────────────────────────────────────────────────────────

  const fetchRecord = useCallback(async () => {
    setLoading(true);
    setError(null);

    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { setLoading(false); return; }

    try {
      const result = await api.get<RecordResponse>(
        `/records/${params.id}`,
        session.access_token,
      );
      setData(result);
    } catch (err) {
      if (err instanceof APIError && err.status === 404) {
        setError("Record not found — it may have been deleted.");
      } else {
        setError(err instanceof Error ? err.message : "Failed to load record.");
      }
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => { void fetchRecord(); }, [fetchRecord]);

  // ── TTS ─────────────────────────────────────────────────────────────────────

  async function handleTts() {
    if (ttsState === "playing") {
      audioRef.current?.pause();
      setTtsState("paused");
      return;
    }

    if (ttsState === "paused") {
      void audioRef.current?.play();
      setTtsState("playing");
      return;
    }

    // idle → loading: fetch audio from the backend (cached, gated, paid feature)
    if (!data?.record.summary) return;
    setTtsState("loading");

    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { setTtsState("idle"); return; }

    try {
      const { audio_url } = await ttsApi.synthesise(
        data.record.summary,
        locale,
        session.access_token,
      );

      const audio = new Audio(audio_url);
      audioRef.current = audio;
      audio.onended = () => setTtsState("idle");
      audio.onerror = () => {
        setTtsState("idle");
        toast.error("Audio playback failed.");
      };
      void audio.play();
      setTtsState("playing");
    } catch (err) {
      setTtsState("idle");
      // Race fallback only: the TTS controls are already wrapped in <PaidGate>
      // (below), so useAccess normally hides this button before a trial-expired
      // 402 can fire. This branch only matters if access expires between page
      // load and the click itself.
      if (err instanceof APIError && err.status === 402) {
        toast.error("Upgrade to Premium to unlock audio playback.", {
          action: { label: "Upgrade", onClick: () => router.push("/settings") },
        });
      } else {
        toast.error("Could not generate audio. Please try again.");
      }
    }
  }

  function handleTtsStop() {
    audioRef.current?.pause();
    if (audioRef.current) audioRef.current.currentTime = 0;
    setTtsState("idle");
  }

  // ── Delete record ───────────────────────────────────────────────────────────

  async function handleDelete() {
    if (!window.confirm("Delete this record permanently? This cannot be undone.")) return;
    setDeleting(true);

    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;

    try {
      await api.delete(`/records/${params.id}`, session.access_token);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
      setDeleting(false);
    }
  }

  // ── Download original document ──────────────────────────────────────────────

  const [downloading, setDownloading] = useState(false);

  async function handleDownload() {
    const record = data?.record;
    if (!record?.file_url) return;
    setDownloading(true);
    try {
      const res = await fetch(record.file_url);
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const ext  = record.file_path?.split(".").pop() ?? "pdf";
      const a    = document.createElement("a");
      a.href     = url;
      a.download = `${record.title}.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Download failed. Please try again.");
    } finally {
      setDownloading(false);
    }
  }

  // ── Loading state ───────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="space-y-6 max-w-4xl">
        <div className="flex items-center gap-3">
          <Skeleton className="h-9 w-20" />
        </div>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-48" />
        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-64 rounded-lg" />
          <Skeleton className="h-64 rounded-lg" />
        </div>
        <Skeleton className="h-48 rounded-lg" />
        <Skeleton className="h-48 rounded-lg" />
      </div>
    );
  }

  // ── Error state ──────────────────────────────────────────────────────────────

  if (error || !data) {
    return (
      <div className="space-y-4 max-w-4xl">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/dashboard">
            <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" /> Back
          </Link>
        </Button>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          <AlertDescription>{error ?? "Something went wrong."}</AlertDescription>
        </Alert>
      </div>
    );
  }

  const { record, medications, lab_values } = data;
  const typeLabel    = RECORD_TYPE_LABELS[record.record_type] ?? record.record_type;
  const typeVariant  = RECORD_TYPE_VARIANT[record.record_type] ?? "outline";
  const isPending    = record.processing_status === "pending" || record.processing_status === "processing";
  const isFailed     = record.processing_status === "failed";
  const needsReview  = record.processing_status === "needs_review";
  const isImage      = isImageFile(record.file_url, record.file_path);

  const formattedDate = record.document_date
    ? new Date(record.document_date).toLocaleDateString("en-IN", {
        day: "numeric", month: "long", year: "numeric",
      })
    : null;

  const createdDate = new Date(record.created_at).toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric",
  });

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 max-w-4xl">

      {/* ── Nav ─────────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/timeline">
            <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />
            {t("back_to_timeline")}
          </Link>
        </Button>
        <div className="flex items-center gap-2">
          {data && (
            <ShareDialog
              recordId={data.record.id}
              recordTitle={data.record.title}
            />
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={handleDelete}
            disabled={deleting}
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
            aria-label="Delete this record"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {/* ── Page header ─────────────────────────────────────────────────────── */}
      <div>
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <h1 className="text-2xl font-semibold tracking-tight">{record.title}</h1>
          <Badge variant={typeVariant} className="text-xs">{typeLabel}</Badge>
          {needsReview && <Badge variant="warning" className="text-xs">Needs review</Badge>}
          {isFailed    && <Badge variant="destructive" className="text-xs">Failed</Badge>}
          {isPending   && <Badge variant="secondary" className="text-xs">Processing</Badge>}
        </div>
        <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
          {formattedDate && (
            <span className="flex items-center gap-1">
              <CalendarDays className="h-4 w-4" aria-hidden="true" />
              {formattedDate}
            </span>
          )}
          {record.facility && (
            <span className="flex items-center gap-1">
              <Hospital className="h-4 w-4" aria-hidden="true" />
              {record.facility}
            </span>
          )}
          {record.doctor && (
            <span className="flex items-center gap-1">
              <User className="h-4 w-4" aria-hidden="true" />
              {record.doctor}
            </span>
          )}
        </div>
      </div>

      {/* ── Processing banner ────────────────────────────────────────────────── */}
      {(isFailed || isPending || needsReview) && (
        <Alert variant={isFailed ? "destructive" : "default"}
               className={needsReview ? "border-amber-300 bg-amber-50 text-amber-900" : undefined}>
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          <AlertDescription>
            {isFailed
              ? `Processing failed: ${record.processing_error ?? "Unknown error."}`
              : isPending
              ? "Document is still being processed. Refresh in a moment."
              : "No medications or lab values were extracted. Verify the document content manually."}
          </AlertDescription>
        </Alert>
      )}

      {/* ── Document preview + Summary ──────────────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-2">

        {/* Document preview */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <FileText className="h-4 w-4 text-primary" aria-hidden="true" />
                  {t("original_doc")}
                </CardTitle>
                <CardDescription className="text-xs mt-1">
                  {t("uploaded_at", { date: createdDate })}
                </CardDescription>
              </div>
              {record.file_url && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDownload}
                  disabled={downloading}
                  aria-label={t("download")}
                >
                  {downloading
                    ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    : <Download className="h-3.5 w-3.5" aria-hidden="true" />
                  }
                  <span className="ml-1.5 hidden sm:inline">{t("download")}</span>
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {record.file_url ? (
              isImage ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={record.file_url}
                  alt={record.title}
                  className="w-full rounded border object-contain max-h-[50vh] sm:max-h-[70vh]"
                />
              ) : (
                <iframe
                  src={record.file_url}
                  title={record.title}
                  className="w-full rounded border h-[50vh] sm:h-[70vh]"
                  aria-label={`Preview of ${record.title}`}
                />
              )
            ) : (
              <div className="flex flex-col items-center gap-2 py-8 text-center text-muted-foreground">
                <FileText className="h-8 w-8" aria-hidden="true" />
                <p className="text-sm">{t("preview_unavailable")}</p>
                <p className="text-xs">{t("preview_expired")}</p>
                <Button variant="outline" size="sm" onClick={fetchRecord}>
                  Reload
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* LLM summary + metadata */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">{t("clinical_summary")}</CardTitle>
              <CardDescription className="text-xs">{t("summary_source")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <PaidGate featureName="Clinical Summary">
                {record.summary ? (
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {record.summary}
                  </p>
                ) : isPending ? (
                  <div className="space-y-2">
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-5/6" />
                    <Skeleton className="h-4 w-4/6" />
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    {t("no_summary")}
                  </p>
                )}
              </PaidGate>

              {/* TTS Listen button — shown only when summary exists and not clinician view */}
              {record.summary && (
                <PaidGate featureName="Text-to-Speech playback" fallbackSize="sm">
                  <div className="flex items-center gap-2 pt-1">
                    {ttsState === "idle" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void handleTts()}
                        className="h-8 text-xs gap-1.5"
                      >
                        <Volume2 className="h-3.5 w-3.5" aria-hidden="true" />
                        {t("listen")}
                      </Button>
                    )}
                    {ttsState === "loading" && (
                      <Button variant="outline" size="sm" disabled className="h-8 text-xs gap-1.5">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                        {t("generating_audio")}
                      </Button>
                    )}
                    {ttsState === "playing" && (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => void handleTts()}
                          className="h-8 text-xs gap-1.5"
                        >
                          <Pause className="h-3.5 w-3.5" aria-hidden="true" />
                          {t("pause")}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={handleTtsStop}
                          className="h-8 text-xs gap-1.5 text-muted-foreground"
                        >
                          <Square className="h-3.5 w-3.5" aria-hidden="true" />
                          {t("stop")}
                        </Button>
                      </>
                    )}
                    {ttsState === "paused" && (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => void handleTts()}
                          className="h-8 text-xs gap-1.5"
                        >
                          <Play className="h-3.5 w-3.5" aria-hidden="true" />
                          {t("resume")}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={handleTtsStop}
                          className="h-8 text-xs gap-1.5 text-muted-foreground"
                        >
                          <Square className="h-3.5 w-3.5" aria-hidden="true" />
                          {t("stop")}
                        </Button>
                      </>
                    )}
                  </div>
                </PaidGate>
              )}
            </CardContent>
          </Card>

          {/* Metadata */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">{t("record_details")}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm space-y-2">
              <Row label={t("type")}          value={typeLabel} />
              {record.document_date && <Row label={t("document_date")} value={formattedDate ?? ""} />}
              {record.facility && <Row label={t("facility")}  value={record.facility} />}
              {record.doctor   && <Row label={t("doctor")}    value={record.doctor} />}
              <Row label={t("uploaded")}    value={createdDate} />
              <Row label={t("status")}      value={record.processing_status.replace("_", " ")} />
            </CardContent>
          </Card>
        </div>
      </div>

      {/* ── Medications table ────────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Pill className="h-4 w-4 text-primary" aria-hidden="true" />
            {t("medications")}
            {medications.length > 0 && (
              <Badge variant="secondary" className="text-xs">{medications.length}</Badge>
            )}
          </CardTitle>
          <CardDescription className="text-xs">{t("meds_hint")}</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {medications.length === 0 ? (
            <p className="text-sm text-muted-foreground italic px-6 py-4">
              {t("no_medications")}
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("drug_name")}</TableHead>
                  <TableHead>{t("dosage")}</TableHead>
                  <TableHead>{t("frequency")}</TableHead>
                  <TableHead>{t("duration")}</TableHead>
                  <TableHead className="w-28">{t("confidence")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {medications.map((med) => (
                  <TableRow key={med.id}>
                    <TableCell className="font-medium">{med.name}</TableCell>
                    <TableCell className="text-muted-foreground">{med.dosage ?? "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{med.frequency ?? "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{med.duration ?? "—"}</TableCell>
                    <TableCell>
                      {med.low_confidence ? (
                        <Badge variant="warning" className="text-xs">{t("unverified")}</Badge>
                      ) : (
                        <Badge variant="success" className="text-xs">{t("verified")}</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── Lab values table ─────────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <FlaskConical className="h-4 w-4 text-primary" aria-hidden="true" />
            {t("lab_values")}
            {lab_values.length > 0 && (
              <Badge variant="secondary" className="text-xs">{lab_values.length}</Badge>
            )}
            {lab_values.some((l) => l.is_abnormal === true) && (
              <Badge variant="warning" className="text-xs">
                {lab_values.filter((l) => l.is_abnormal === true).length} {t("abnormal")}
              </Badge>
            )}
          </CardTitle>
          <CardDescription className="text-xs">{t("labs_hint")}</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {lab_values.length === 0 ? (
            <p className="text-sm text-muted-foreground italic px-6 py-4">
              {t("no_labs")}
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("test")}</TableHead>
                  <TableHead>{t("value")}</TableHead>
                  <TableHead>{t("unit")}</TableHead>
                  <TableHead>{t("reference_range")}</TableHead>
                  <TableHead className="w-24">{t("status_label")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lab_values.map((lab) => (
                  <TableRow
                    key={lab.id}
                    className={lab.is_abnormal === true ? "bg-amber-50 hover:bg-amber-100" : ""}
                  >
                    <TableCell className="font-medium">{lab.test_name}</TableCell>
                    <TableCell
                      className={lab.is_abnormal === true ? "font-semibold text-amber-800" : ""}
                    >
                      {lab.value}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{lab.unit ?? "—"}</TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {lab.reference_range ? (
                        <span className="inline-flex items-center gap-1.5">
                          {lab.reference_range}
                          {lab.reference_source === "standard" && (
                            <span
                              className="inline-block rounded border px-1 py-px text-[9px] font-medium bg-muted text-muted-foreground cursor-help shrink-0"
                              title="General reference range — not specific to this laboratory's equipment."
                            >
                              Std
                            </span>
                          )}
                        </span>
                      ) : "—"}
                    </TableCell>
                    <TableCell>
                      {lab.is_abnormal === true ? (
                        <Badge variant="warning" className="text-xs">{t("abnormal")}</Badge>
                      ) : lab.is_abnormal === false ? (
                        <span className="text-xs text-muted-foreground">{t("normal")}</span>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Separator />

      <p className="text-xs text-muted-foreground">
        Record ID: {record.id} · {t("verify_disclaimer")}
      </p>
    </div>
  );
}

// ── Small helper ──────────────────────────────────────────────────────────────

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-muted-foreground w-28 shrink-0">{label}</span>
      <span className="capitalize">{value}</span>
    </div>
  );
}
