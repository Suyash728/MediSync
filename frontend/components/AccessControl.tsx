"use client";

import React from "react";
import Link from "next/link";
import { Lock, Sparkles } from "lucide-react";
import { useAccess } from "@/lib/AccessContext";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface PaidGateProps {
  children: React.ReactNode;
  featureName: string;
  className?: string;
  fallbackSize?: "sm" | "default" | "lg";
}

export function PaidGate({
  children,
  featureName,
  className,
  fallbackSize = "default",
}: PaidGateProps) {
  const { hasAccess, loading } = useAccess();

  if (loading) {
    return (
      <div className={cn("space-y-3 p-6 border rounded-lg bg-background", className)}>
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-9 w-24" />
      </div>
    );
  }

  if (hasAccess) {
    return <>{children}</>;
  }

  // Render a compact lock placeholder for inline lists or side items
  if (fallbackSize === "sm") {
    return (
      <div
        className={cn(
          "flex items-center justify-between gap-3 p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/10 text-xs",
          className
        )}
      >
        <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400">
          <Lock className="h-3.5 w-3.5 text-primary flex-shrink-0" />
          <span>Upgrade to Premium to unlock {featureName.toLowerCase()}.</span>
        </div>
        <Link href="/settings" className="text-primary font-semibold hover:underline">
          Upgrade
        </Link>
      </div>
    );
  }

  // Default Standard lock placeholder block
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center p-8 border border-dashed rounded-lg bg-slate-50/50 dark:bg-slate-900/10 space-y-4 text-center border-slate-200 dark:border-slate-800 bg-background",
        className
      )}
      role="alert"
      aria-label={`${featureName} requires premium upgrade`}
    >
      <div className="h-10 w-10 rounded-full bg-primary/10 text-primary flex items-center justify-center">
        <Lock className="h-5 w-5" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
          Premium Feature
        </p>
        <p className="text-xs text-muted-foreground max-w-sm leading-relaxed">
          Upgrade to Premium to unlock {featureName.toLowerCase()} and access RAG Q&A, TTS playback, and automatic record summaries.
        </p>
      </div>
      <Button
        size="sm"
        asChild
        className="text-xs h-8 bg-primary hover:bg-primary/90 text-primary-foreground"
      >
        <Link href="/settings">
          Upgrade Account
        </Link>
      </Button>
    </div>
  );
}

export function TrialBanner() {
  const { isPaid, trialEndsAt, loading } = useAccess();

  if (loading || isPaid || !trialEndsAt) return null;

  const ends = new Date(trialEndsAt);
  const diff = ends.getTime() - Date.now();
  const daysLeft = Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));

  // If the trial has expired, we hide the banner (PaidGate placeholders will handle block/upsells)
  if (daysLeft <= 0) return null;

  return (
    <div
      className="bg-primary/10 border-b border-primary/20 px-4 py-2 text-xs text-primary flex items-center justify-between gap-4 font-medium transition-colors"
      role="status"
    >
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 animate-pulse flex-shrink-0" />
        <span>
          Trial: {daysLeft} {daysLeft === 1 ? "day" : "days"} of AI features left
        </span>
      </div>
      <Link
        href="/settings"
        className="text-primary underline font-bold hover:text-primary/80 transition-colors whitespace-nowrap"
      >
        Upgrade to Premium
      </Link>
    </div>
  );
}
