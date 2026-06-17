"use client";

/**
 * UploadZone — drag-and-drop document uploader.
 *
 * Accepts PDF, JPEG, and PNG files (≤ 20 MB).  On drop or file-input change:
 *   1. Validates the file client-side (type + size).
 *   2. Gets the Supabase access token for the Bearer header.
 *   3. POSTs multipart/form-data to POST /upload on the FastAPI backend.
 *   4. Calls onSuccess(result) with the parsed record data so the parent can
 *      update the records list without a full page reload.
 *
 * The backend pipeline can take 10–30 s (OCR + NER + LLM) — we show step
 * labels so the patient knows processing is in progress.
 */

import { useState, useRef, DragEvent, ChangeEvent } from "react";
import { UploadCloud, FileText, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { createClient } from "@/lib/supabase";
import type { RecordType, DrugConflict } from "@/lib/types";

// Maximum 20 MB — matches the backend limit
const MAX_BYTES = 20 * 1024 * 1024;

const ALLOWED_MIME_TYPES = new Set([
  "application/pdf",
  "image/jpeg",
  "image/png",
]);

// Values only — labels come from the record_card i18n namespace (type_<value>)
const RECORD_TYPE_VALUES: RecordType[] = [
  "prescription",
  "lab_report",
  "discharge_summary",
  "imaging",
  "vaccination",
  "other",
];

interface UploadResult {
  record:         Record<string, unknown>;
  medications:    unknown[];
  lab_values:     unknown[];
  diagnoses:      unknown[];
  new_conflicts:  DrugConflict[];
}

interface Props {
  onSuccess: (result: UploadResult) => void;
}

export function UploadZone({ onSuccess }: Props) {
  const t       = useTranslations("upload");
  const tCard   = useTranslations("record_card");
  const tCommon = useTranslations("common");

  // Processing step labels — resolved inside the component so hooks are valid
  const PROCESSING_STEPS = [
    t("step_uploading"),
    t("step_ocr"),
    t("step_ner"),
    t("step_summary"),
    t("step_saving"),
  ];

  const fileInputRef = useRef<HTMLInputElement>(null);

  const [dragging,      setDragging]     = useState(false);
  const [selectedFile,  setSelectedFile] = useState<File | null>(null);
  const [recordType,    setRecordType]   = useState<RecordType | "">("");
  const [title,         setTitle]        = useState("");
  const [documentDate,  setDocDate]      = useState("");
  const [facility,      setFacility]     = useState("");
  const [doctor,        setDoctor]       = useState("");

  const [loading,       setLoading]      = useState(false);
  const [stepIdx,       setStepIdx]      = useState(0);
  const [error,         setError]        = useState<string | null>(null);
  const [done,          setDone]         = useState(false);

  // ── File selection ─────────────────────────────────────────────────────────

  function validateAndSet(file: File): string | null {
    if (!ALLOWED_MIME_TYPES.has(file.type)) {
      return "Only PDF, JPEG, and PNG files are supported.";
    }
    if (file.size > MAX_BYTES) {
      return "File is too large (max 20 MB).";
    }
    return null;
  }

  function onDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(true);
  }

  function onDragLeave() {
    setDragging(false);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const err = validateAndSet(file);
    if (err) { setError(err); return; }
    setSelectedFile(file);
    setError(null);
    // Pre-fill title from filename (strip extension)
    if (!title) setTitle(file.name.replace(/\.[^/.]+$/, ""));
  }

  function onFileInputChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const err = validateAndSet(file);
    if (err) { setError(err); return; }
    setSelectedFile(file);
    setError(null);
    if (!title) setTitle(file.name.replace(/\.[^/.]+$/, ""));
  }

  // ── Upload ────────────────────────────────────────────────────────────────

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedFile) return;
    if (!recordType) {
      setError(t("type_required"));
      return;
    }

    setError(null);
    setLoading(true);
    setStepIdx(0);

    // Get the current session token
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) {
      setError("Session expired. Please sign in again.");
      setLoading(false);
      return;
    }

    const formData = new FormData();
    formData.append("file",          selectedFile);
    formData.append("record_type",   recordType);
    formData.append("title",         title.trim() || selectedFile.name);
    formData.append("document_date", documentDate);
    formData.append("facility",      facility.trim());
    formData.append("doctor",        doctor.trim());

    // Simulate step progression (the backend doesn't stream status, so we just
    // advance the label every few seconds to show something is happening)
    const stepTimer = setInterval(() => {
      setStepIdx((i) => Math.min(i + 1, PROCESSING_STEPS.length - 1));
    }, 4000);

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
      const res = await fetch(`${backendUrl}/upload/`, {
        method: "POST",
        // Do NOT set Content-Type — the browser sets it with the multipart boundary
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
        body: formData,
      });

      clearInterval(stepTimer);

      if (!res.ok) {
        const body = await res.json().catch(() => ({})) as { detail?: string };
        throw new Error(body.detail ?? `Server error (${res.status})`);
      }

      const result: UploadResult = await res.json();
      setDone(true);
      onSuccess(result);

      // Fire a toast for each newly-detected major drug interaction
      const majorConflicts = (result.new_conflicts ?? []).filter(
        (c) => c.severity === "major"
      );
      for (const c of majorConflicts) {
        toast.warning(`⚠️ Drug interaction detected: ${c.drug_a} + ${c.drug_b}`, {
          description: "Go to Drug Alerts to view details and acknowledge.",
          duration: 8000,
        });
      }

    } catch (err) {
      clearInterval(stepTimer);
      setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  // ── Reset ──────────────────────────────────────────────────────────────────

  function reset() {
    setSelectedFile(null);
    setRecordType("");
    setTitle("");
    setDocDate("");
    setFacility("");
    setDoctor("");
    setError(null);
    setDone(false);
    setStepIdx(0);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("title")}</CardTitle>
        <CardDescription>{t("subtitle")}</CardDescription>
      </CardHeader>

      <CardContent>
        {done ? (
          // ── Success state ──────────────────────────────────────────────────
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <CheckCircle2 className="h-10 w-10 text-primary" aria-hidden="true" />
            <p className="font-medium">{t("success")}</p>
            <Button variant="outline" size="sm" onClick={reset}>
              {t("upload_another")}
            </Button>
          </div>
        ) : (
          <form onSubmit={handleUpload} className="space-y-5">

            {/* ── Drop zone ───────────────────────────────────────────────── */}
            <div
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
              role="button"
              aria-label={t("drop_label")}
              className={`
                flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed
                p-8 cursor-pointer transition-colors
                ${dragging
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/50 hover:bg-slate-50"
                }
              `}
            >
              {selectedFile ? (
                <>
                  <FileText className="h-8 w-8 text-primary" aria-hidden="true" />
                  <p className="text-sm font-medium">{selectedFile.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(selectedFile.size / 1024).toFixed(0)} KB ·{" "}
                    <button
                      type="button"
                      className="text-primary hover:underline"
                      onClick={(e) => { e.stopPropagation(); reset(); }}
                    >
                      {t("remove")}
                    </button>
                  </p>
                </>
              ) : (
                <>
                  <UploadCloud className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
                  <p className="text-sm text-muted-foreground">{t("drop_hint")}</p>
                  <p className="text-xs text-muted-foreground">{t("file_types")}</p>
                </>
              )}
            </div>

            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png"
              className="hidden"
              onChange={onFileInputChange}
            />

            {/* ── Metadata ────────────────────────────────────────────────── */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="record-type">{t("doc_type")}</Label>
                <select
                  id="record-type"
                  value={recordType}
                  onChange={(e) => setRecordType(e.target.value as RecordType | "")}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="" disabled>{t("doc_type_placeholder")}</option>
                  {RECORD_TYPE_VALUES.map((value) => (
                    <option key={value} value={value}>{tCard(`type_${value}`)}</option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="doc-date">{t("doc_date")}</Label>
                <Input
                  id="doc-date"
                  type="date"
                  required
                  value={documentDate}
                  onChange={(e) => setDocDate(e.target.value)}
                  max={new Date().toISOString().split("T")[0]}
                />
              </div>

              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="doc-title">{t("doc_title")}</Label>
                <Input
                  id="doc-title"
                  type="text"
                  required
                  placeholder={t("doc_title_placeholder")}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="facility">
                  {t("facility")}{" "}
                  <span className="text-muted-foreground text-xs">({tCommon("optional")})</span>
                </Label>
                <Input
                  id="facility"
                  type="text"
                  placeholder={t("facility_placeholder")}
                  value={facility}
                  onChange={(e) => setFacility(e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="doctor">
                  {t("doctor")}{" "}
                  <span className="text-muted-foreground text-xs">({tCommon("optional")})</span>
                </Label>
                <Input
                  id="doctor"
                  type="text"
                  placeholder={t("doctor_placeholder")}
                  value={doctor}
                  onChange={(e) => setDoctor(e.target.value)}
                />
              </div>
            </div>

            {/* ── Error ───────────────────────────────────────────────────── */}
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" aria-hidden="true" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* ── Processing indicator ─────────────────────────────────────── */}
            {loading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin shrink-0" aria-hidden="true" />
                <span>{PROCESSING_STEPS[stepIdx]}</span>
              </div>
            )}

            <Button
              type="submit"
              className="w-full"
              disabled={loading || !selectedFile || !recordType}
            >
              {loading
                ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />{t("processing")}</>
                : t("upload_button")
              }
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
