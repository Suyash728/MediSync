"use client";

/**
 * RecordCard — displays a single health record summary.
 *
 * Shows: title, date, type badge, facility/doctor, LLM summary, and
 * counts for medications and lab values.  Clicking navigates to the
 * full record detail page.
 */

import Link from "next/link";
import { CalendarDays, Hospital, User, Pill, FlaskConical, AlertTriangle } from "lucide-react";
import { useTranslations } from "next-intl";

import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { RecordType } from "@/lib/types";

// Badge colour variant per record type
const RECORD_TYPE_VARIANT: Record<
  RecordType,
  "default" | "secondary" | "outline"
> = {
  prescription:      "default",
  lab_report:        "secondary",
  discharge_summary: "secondary",
  imaging:           "outline",
  vaccination:       "outline",
  other:             "outline",
};

interface RecordCardProps {
  id:                  string;
  record_type:         RecordType;
  title:               string;
  document_date?:      string | null;
  facility?:           string | null;
  doctor?:             string | null;
  summary?:            string | null;
  processing_status:   string;
  processing_error?:   string | null;
  medication_count?:   number;
  lab_value_count?:    number;
  abnormal_lab_count?: number;
}

export function RecordCard({
  id,
  record_type,
  title,
  document_date,
  facility,
  doctor,
  summary,
  processing_status,
  processing_error,
  medication_count   = 0,
  lab_value_count    = 0,
  abnormal_lab_count = 0,
}: RecordCardProps) {
  const t = useTranslations("record_card");

  const typeLabel   = t(`type_${record_type}` as Parameters<typeof t>[0]) ?? record_type;
  const typeVariant = RECORD_TYPE_VARIANT[record_type] ?? "outline";

  const isFailed    = processing_status === "failed";
  const isPending   = processing_status === "pending" || processing_status === "processing";
  // needs_review: pipeline ran but found no structured data — show amber warning, not red error
  const needsReview = processing_status === "needs_review";

  return (
    <Link href={`/record/${id}`} className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg">
      <Card className="hover:shadow-md transition-shadow cursor-pointer">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-base leading-snug">{title}</CardTitle>
            <Badge variant={typeVariant} className="shrink-0 text-xs">
              {typeLabel}
            </Badge>
          </div>

          {/* Date, facility, doctor */}
          <CardDescription>
            <span className="flex flex-wrap gap-3 text-xs mt-1">
              {document_date && (
                <span className="flex items-center gap-1">
                  <CalendarDays className="h-3.5 w-3.5" aria-hidden="true" />
                  {new Date(document_date).toLocaleDateString("en-IN", {
                    day:   "numeric",
                    month: "short",
                    year:  "numeric",
                  })}
                </span>
              )}
              {facility && (
                <span className="flex items-center gap-1">
                  <Hospital className="h-3.5 w-3.5" aria-hidden="true" />
                  {facility}
                </span>
              )}
              {doctor && (
                <span className="flex items-center gap-1">
                  <User className="h-3.5 w-3.5" aria-hidden="true" />
                  {doctor}
                </span>
              )}
            </span>
          </CardDescription>
        </CardHeader>

        <CardContent className="pb-3">
          {isFailed ? (
            <p className="text-sm text-destructive">
              {t("failed")}: {processing_error ?? "Unknown error."}
            </p>
          ) : isPending ? (
            <p className="text-sm text-muted-foreground italic">{t("processing")}</p>
          ) : needsReview ? (
            <p className="text-sm text-amber-700">{t("needs_review")}</p>
          ) : summary ? (
            <p className="text-sm text-muted-foreground line-clamp-3">{summary}</p>
          ) : (
            <p className="text-sm text-muted-foreground italic">{t("no_summary")}</p>
          )}
        </CardContent>

        {/* Extracted entity counts */}
        {!isFailed && !isPending && !needsReview && (medication_count > 0 || lab_value_count > 0) && (
          <>
            <Separator />
            <CardFooter className="pt-3 pb-3">
              <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                {medication_count > 0 && (
                  <span className="flex items-center gap-1">
                    <Pill className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                    {t("medications", { count: medication_count })}
                  </span>
                )}
                {lab_value_count > 0 && (
                  <span className="flex items-center gap-1">
                    <FlaskConical className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                    {t("lab_results", { count: lab_value_count })}
                  </span>
                )}
                {abnormal_lab_count > 0 && (
                  <span className="flex items-center gap-1 text-amber-700">
                    <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                    {t("abnormal_count", { count: abnormal_lab_count })}
                  </span>
                )}
              </div>
            </CardFooter>
          </>
        )}
      </Card>
    </Link>
  );
}
