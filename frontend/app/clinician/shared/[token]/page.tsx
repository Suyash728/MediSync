/**
 * /clinician/shared/[token] — read-only patient record view for clinicians.
 *
 * Public page — no login required. Resolves the token server-side (no client JS
 * needed for the auth check). The backend's /share/view/{token} endpoint enforces:
 *   - Token exists
 *   - Grant is active (not revoked)
 *   - Grant has not expired
 * Signed URLs for original documents are generated server-side using the service-role
 * key — the clinician's browser never has direct Storage access or sees credentials.
 *
 * On any auth failure the backend returns 403 with a human-readable message;
 * we show that message in place of any medical data.
 */

import {
  ShieldCheck, CalendarDays, Hospital, User,
  FileText, AlertCircle, Pill, FlaskConical, Info,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import type { RecordType } from "@/lib/types";

// ── Types from the backend /share/view/{token} response ───────────────────────

interface MedicationRow {
  id:             string;
  name:           string;
  dosage:         string | null;
  frequency:      string | null;
  duration:       string | null;
  is_active:      boolean;
  low_confidence: boolean;
}

interface LabValueRow {
  id:               string;
  test_name:        string;
  value:            string;
  unit:             string | null;
  reference_range:  string | null;
  reference_source: "lab_provided" | "standard" | null;
  is_abnormal:      boolean | null;
}

interface SharedRecord {
  id:                string;
  record_type:       RecordType;
  title:             string;
  document_date:     string | null;
  facility:          string | null;
  doctor:            string | null;
  file_path:         string | null;
  file_url:          string | null;  // signed URL generated server-side, valid 1 hour
  summary:           string | null;
  processing_status: string;
  medications:       MedicationRow[];
  lab_values:        LabValueRow[];
}

interface SharedViewData {
  patient_name:     string;
  grant_expires_at: string;
  scope_label:      string;
  recipient_name:   string | null;
  records:          SharedRecord[];
}

// ── Constants ──────────────────────────────────────────────────────────────────

const RECORD_TYPE_LABELS: Record<RecordType, string> = {
  prescription:       "Prescription",
  lab_report:         "Lab Report",
  discharge_summary:  "Discharge Summary",
  imaging:            "Imaging",
  vaccination:        "Vaccination",
  other:              "Other",
};

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL!;

// ── Helpers ───────────────────────────────────────────────────────────────────

function isImageFile(fileUrl: string | null, filePath: string | null): boolean {
  const src = fileUrl ?? filePath ?? "";
  const ext = src.split("?")[0].split(".").pop()?.toLowerCase() ?? "";
  return ext === "jpg" || ext === "jpeg" || ext === "png";
}

// ── Data fetcher ──────────────────────────────────────────────────────────────

async function fetchSharedData(
  token: string,
): Promise<{ data: SharedViewData } | { error: string }> {
  try {
    // Server-side fetch — no CORS restriction, no client JS required
    const res = await fetch(`${BACKEND_URL}/share/view/${token}`, {
      cache: "no-store",  // grant state (revoked/expired) must always be live
    });

    if (!res.ok) {
      let detail = `Access denied (HTTP ${res.status})`;
      try {
        const body = (await res.json()) as { detail?: string };
        if (body.detail) detail = body.detail;
      } catch { /* response wasn't JSON */ }
      return { error: detail };
    }

    const data = (await res.json()) as SharedViewData;
    return { data };
  } catch {
    return { error: "Could not reach the server. Please try again later." };
  }
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function SharedRecordPage({
  params,
}: {
  params: { token: string };
}) {
  const result = await fetchSharedData(params.token);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">

      {/* Minimal header — no patient nav links, clinician-facing only */}
      <header className="border-b bg-background sticky top-0 z-10">
        <div className="container h-14 flex items-center justify-between max-w-4xl">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />
            MediSync — Shared Records
          </div>
          <span className="text-xs text-muted-foreground font-mono bg-muted px-2 py-0.5 rounded">
            Read Only
          </span>
        </div>
      </header>

      <main className="flex-1 container py-8 space-y-6 max-w-4xl">

        {"error" in result ? (
          // ── Access denied / expired / revoked ────────────────────────────────
          <div className="flex flex-col items-center gap-6 py-16">
            <div className="rounded-full bg-red-50 p-4">
              <AlertCircle className="h-8 w-8 text-red-500" aria-hidden="true" />
            </div>
            <Alert variant="destructive" className="max-w-md">
              <AlertTitle>Cannot display records</AlertTitle>
              <AlertDescription>{result.error}</AlertDescription>
            </Alert>
            <p className="text-sm text-muted-foreground text-center max-w-sm">
              Contact the patient who shared this link to request renewed access.
            </p>
          </div>
        ) : (
          // ── Valid grant — show scoped records ────────────────────────────────
          <>
            {/* Read-only shared view notice */}
            <Alert className="border-blue-200 bg-blue-50 text-blue-900">
              <Info className="h-4 w-4 text-blue-600" aria-hidden="true" />
              <AlertTitle className="text-blue-900">Read-only shared view</AlertTitle>
              <AlertDescription className="text-blue-800">
                These records were shared by{" "}
                <strong>{result.data.patient_name}</strong>
                {result.data.recipient_name && (
                  <> with <strong>{result.data.recipient_name}</strong></>
                )}
                . Access expires{" "}
                {new Date(result.data.grant_expires_at).toLocaleDateString("en-IN", {
                  day: "numeric", month: "long", year: "numeric",
                })}
                . The patient can revoke access at any time.
              </AlertDescription>
            </Alert>

            {/* Scope context strip */}
            <div className="rounded-lg border bg-primary/5 px-4 py-3">
              <p className="text-xs text-muted-foreground">
                Scope: <span className="font-medium text-foreground">{result.data.scope_label}</span>
              </p>
            </div>

            {/* Records */}
            {result.data.records.length === 0 ? (
              <Card>
                <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
                  <FileText className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
                  <p className="font-medium text-muted-foreground">No records in this share</p>
                  <p className="text-sm text-muted-foreground">
                    The patient may not have any records of the shared type yet.
                  </p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-8">
                <h2 className="text-base font-semibold tracking-tight">
                  {result.data.records.length} record{result.data.records.length !== 1 ? "s" : ""}
                </h2>
                {result.data.records.map((rec) => (
                  <SharedRecordCard key={rec.id} record={rec} />
                ))}
              </div>
            )}

            {/* Footer disclaimer */}
            <p className="text-xs text-muted-foreground text-center border-t pt-4">
              This is a read-only view of patient-shared records. Data is extracted by AI
              and should be verified against the original documents. MediSync does not
              provide medical advice.
            </p>
          </>
        )}
      </main>
    </div>
  );
}

// ── Record card ───────────────────────────────────────────────────────────────

function SharedRecordCard({ record }: { record: SharedRecord }) {
  const typeLabel = RECORD_TYPE_LABELS[record.record_type] ?? record.record_type;
  const isImage = isImageFile(record.file_url, record.file_path);

  const formattedDate = record.document_date
    ? new Date(record.document_date).toLocaleDateString("en-IN", {
        day: "numeric", month: "long", year: "numeric",
      })
    : null;

  return (
    <div className="space-y-4">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-lg font-semibold tracking-tight">{record.title}</h3>
          <Badge variant="outline" className="text-xs font-normal">{typeLabel}</Badge>
        </div>
        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
          {formattedDate && (
            <span className="flex items-center gap-1">
              <CalendarDays className="h-3 w-3" aria-hidden="true" />
              {formattedDate}
            </span>
          )}
          {record.facility && (
            <span className="flex items-center gap-1">
              <Hospital className="h-3 w-3" aria-hidden="true" />
              {record.facility}
            </span>
          )}
          {record.doctor && (
            <span className="flex items-center gap-1">
              <User className="h-3 w-3" aria-hidden="true" />
              {record.doctor}
            </span>
          )}
        </div>
      </div>

      {/* ── Original document + Clinical summary (side by side on large screens) */}
      <div className="grid gap-4 lg:grid-cols-2">

        {/* Original document */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <FileText className="h-4 w-4 text-primary" aria-hidden="true" />
              Original Document
            </CardTitle>
            <CardDescription className="text-xs">
              Signed URL valid for 1 hour · regenerates on page reload
            </CardDescription>
          </CardHeader>
          <CardContent>
            {record.file_url ? (
              isImage ? (
                // eslint-disable-next-line @next/next/no-img-element
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
                <p className="text-sm">Preview unavailable</p>
                <p className="text-xs">
                  The document may not have been uploaded, or the signed URL has expired.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Clinical summary */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Clinical Summary</CardTitle>
            <CardDescription className="text-xs">
              AI-generated from extracted document content
            </CardDescription>
          </CardHeader>
          <CardContent>
            {record.summary ? (
              <p className="text-sm text-muted-foreground leading-relaxed">{record.summary}</p>
            ) : (
              <p className="text-sm text-muted-foreground italic">No summary available.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Medications table ─────────────────────────────────────────────────── */}
      {record.medications.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Pill className="h-4 w-4 text-primary" aria-hidden="true" />
              Medications
              <Badge variant="secondary" className="text-xs">{record.medications.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Drug name</TableHead>
                  <TableHead>Dosage</TableHead>
                  <TableHead>Frequency</TableHead>
                  <TableHead>Duration</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {record.medications.map((med) => (
                  <TableRow key={med.id}>
                    <TableCell className="font-medium">{med.name}</TableCell>
                    <TableCell className="text-muted-foreground">{med.dosage ?? "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{med.frequency ?? "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{med.duration ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* ── Lab values table ─────────────────────────────────────────────────── */}
      {record.lab_values.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <FlaskConical className="h-4 w-4 text-primary" aria-hidden="true" />
              Lab Values
              <Badge variant="secondary" className="text-xs">{record.lab_values.length}</Badge>
              {record.lab_values.some((l) => l.is_abnormal === true) && (
                <Badge variant="warning" className="text-xs">
                  {record.lab_values.filter((l) => l.is_abnormal === true).length} abnormal
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Test</TableHead>
                  <TableHead>Value</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead>Reference range</TableHead>
                  <TableHead className="w-24">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {record.lab_values.map((lab) => (
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
                              title="General reference range — not specific to this laboratory."
                            >
                              Std
                            </span>
                          )}
                        </span>
                      ) : "—"}
                    </TableCell>
                    <TableCell>
                      {lab.is_abnormal === true ? (
                        <Badge variant="warning" className="text-xs">Abnormal</Badge>
                      ) : lab.is_abnormal === false ? (
                        <span className="text-xs text-muted-foreground">Normal</span>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Separator />
    </div>
  );
}
