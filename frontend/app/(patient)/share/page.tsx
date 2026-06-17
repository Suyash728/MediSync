"use client";

/**
 * /share — Share grant management + access history.
 *
 * Sections:
 *   1. "New share link" — ShareDialog trigger (creates a grant)
 *   2. Active & revoked grants table — copy link + revoke actions
 *   3. Access history — last 20 access_log rows (share_view, view, share_create, share_revoke)
 *      Queried directly from Supabase (RLS guarantees patient sees only their own rows).
 */

import { useCallback, useEffect, useState } from "react";
import { Link2, Trash2, Check, Clock, ShieldOff, Eye, Loader2, History } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ShareDialog } from "@/components/ShareDialog";
import { createClient } from "@/lib/supabase";
import { shareApi } from "@/lib/api";
import type { ShareGrant } from "@/lib/types";

// ── Access log row (subset of fields we display) ──────────────────────────────

interface AccessLogRow {
  id:         string;
  action:     "view" | "download" | "share_create" | "share_revoke" | "share_view";
  actor_type: "patient" | "clinician";
  actor_id:   string | null;
  metadata:   Record<string, unknown> | null;
  created_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function isExpired(grant: ShareGrant): boolean {
  return new Date(grant.expires_at) < new Date();
}

// Keys in the "share" i18n namespace that map to each action type
const ACTION_KEY_MAP: Record<AccessLogRow["action"], string> = {
  view:         "action_view",
  download:     "action_download",
  share_create: "action_share_create",
  share_revoke: "action_share_revoke",
  share_view:   "action_share_view",
};

const ACTION_ICON: Record<AccessLogRow["action"], React.ElementType> = {
  view:          Eye,
  download:      Eye,
  share_create:  Link2,
  share_revoke:  ShieldOff,
  share_view:    Eye,
};

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SharePage() {
  const t = useTranslations("share");

  const [grants,       setGrants]       = useState<ShareGrant[]>([]);
  const [accessLog,    setAccessLog]    = useState<AccessLogRow[]>([]);
  const [loadingGrants, setLoadingGrants] = useState(true);
  const [loadingLog,   setLoadingLog]   = useState(true);
  const [revoking,     setRevoking]     = useState<string | null>(null);
  const [error,        setError]        = useState<string | null>(null);
  const [copiedId,     setCopiedId]     = useState<string | null>(null);

  // ── Load grants ─────────────────────────────────────────────────────────────

  const loadGrants = useCallback(async () => {
    setLoadingGrants(true);
    setError(null);
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { setLoadingGrants(false); return; }

    try {
      const data = await shareApi.list(session.access_token);
      setGrants(data.grants);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load share grants.");
    } finally {
      setLoadingGrants(false);
    }
  }, []);

  // ── Load access log (direct Supabase — RLS scopes to auth.uid()) ────────────

  const loadAccessLog = useCallback(async () => {
    setLoadingLog(true);
    const supabase = createClient();
    // Exclude patient's own record views/downloads — show only share events
    const { data, error: dbError } = await supabase
      .from("access_log")
      .select("id, action, actor_type, actor_id, metadata, created_at")
      .in("action", ["share_create", "share_revoke", "share_view"])
      .order("created_at", { ascending: false })
      .limit(20);

    if (!dbError && data) setAccessLog(data as AccessLogRow[]);
    setLoadingLog(false);
  }, []);

  useEffect(() => {
    void loadGrants();
    void loadAccessLog();
  }, [loadGrants, loadAccessLog]);

  // ── Copy share link ──────────────────────────────────────────────────────────

  async function handleCopy(grant: ShareGrant) {
    const url = `${window.location.origin}/clinician/shared/${grant.token}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopiedId(grant.id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      toast.error("Could not copy to clipboard.");
    }
  }

  // ── Revoke grant ─────────────────────────────────────────────────────────────

  async function handleRevoke(grantId: string) {
    if (!window.confirm(t("revoke_confirm"))) return;
    setRevoking(grantId);
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { setRevoking(null); return; }

    try {
      await shareApi.revoke(grantId, session.access_token);
      setGrants((prev) =>
        prev.map((g) => g.id === grantId ? { ...g, is_active: false } : g)
      );
      toast.success("Share link revoked. Access is now blocked.");
      void loadAccessLog();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to revoke link.");
    } finally {
      setRevoking(null);
    }
  }

  const activeGrants  = grants.filter((g) => g.is_active && !isExpired(g));
  const inactiveGrants = grants.filter((g) => !g.is_active || isExpired(g));

  return (
    <div className="space-y-8 max-w-3xl">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t("subtitle")}</p>
        </div>
        <ShareDialog onCreated={() => { void loadGrants(); void loadAccessLog(); }} />
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* ── Active grants ───────────────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Link2 className="h-4 w-4 text-primary" aria-hidden="true" />
            {t("active_links")}
            {activeGrants.length > 0 && (
              <Badge variant="secondary" className="text-xs">{activeGrants.length}</Badge>
            )}
          </CardTitle>
          <CardDescription className="text-xs">{t("active_links_desc")}</CardDescription>
        </CardHeader>
        <CardContent>
          {loadingGrants ? (
            <div className="space-y-3">
              {[0, 1].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
            </div>
          ) : activeGrants.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <Link2 className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
              <p className="text-sm text-muted-foreground">{t("no_active_links")}</p>
              <p className="text-xs text-muted-foreground">{t("no_active_links_hint")}</p>
            </div>
          ) : (
            <div className="space-y-3">
              {activeGrants.map((grant) => (
                <GrantRow
                  key={grant.id}
                  grant={grant}
                  copiedId={copiedId}
                  revoking={revoking}
                  onCopy={handleCopy}
                  onRevoke={handleRevoke}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Inactive / expired grants ─────────────────────────────────────────── */}
      {!loadingGrants && inactiveGrants.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2 text-muted-foreground">
              <Clock className="h-4 w-4" aria-hidden="true" />
              {t("past_links")}
              <Badge variant="outline" className="text-xs">{inactiveGrants.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 opacity-70">
              {inactiveGrants.map((grant) => (
                <GrantRow
                  key={grant.id}
                  grant={grant}
                  copiedId={copiedId}
                  revoking={revoking}
                  onCopy={handleCopy}
                  onRevoke={handleRevoke}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Access history ───────────────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <History className="h-4 w-4 text-primary" aria-hidden="true" />
            {t("access_history")}
          </CardTitle>
          <CardDescription className="text-xs">{t("history_desc")}</CardDescription>
        </CardHeader>
        <CardContent>
          {loadingLog ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
            </div>
          ) : accessLog.length === 0 ? (
            <p className="text-sm text-muted-foreground italic py-4 text-center">
              {t("no_activity")}
            </p>
          ) : (
            <div className="space-y-2">
              {accessLog.map((entry) => {
                const Icon = ACTION_ICON[entry.action] ?? Eye;
                const meta = entry.metadata ?? {};
                const recipient = (meta.recipient_name as string) ?? null;
                const isClinician = entry.actor_type === "clinician";
                const isShareCreate = entry.action === "share_create";
                const recordTitle = (meta.record_title as string) ?? null;
                const recordDate  = (meta.record_date as string)  ?? null;
                const expiresAt   = (meta.expires_at  as string)  ?? null;
                const actionLabel = t(ACTION_KEY_MAP[entry.action] as Parameters<typeof t>[0]);

                return (
                  <div
                    key={entry.id}
                    className="flex items-start gap-3 rounded-md px-3 py-2 text-sm hover:bg-muted/50 transition-colors"
                  >
                    <Icon className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" aria-hidden="true" />
                    <div className="min-w-0 space-y-0.5">
                      {/* Heading line */}
                      <p className="text-sm">
                        <span className="font-medium">{actionLabel}</span>
                        {isShareCreate && recordTitle && (
                          <span className="text-muted-foreground"> — {recordTitle}</span>
                        )}
                        {!isShareCreate && isClinician && recipient && (
                          <span className="text-muted-foreground"> — {recipient}</span>
                        )}
                      </p>

                      {/* Detail lines — only for share_create entries */}
                      {isShareCreate && (
                        <div className="text-xs text-muted-foreground space-y-0.5">
                          {recordDate && (
                            <p>
                              {t("document_label")}{" "}
                              {new Date(recordDate).toLocaleDateString("en-IN", {
                                day: "numeric", month: "short", year: "numeric",
                              })}
                            </p>
                          )}
                          {recipient && <p>{t("recipient_label")} {recipient}</p>}
                          {expiresAt && (
                            <p>
                              {t("expires_label")}{" "}
                              {new Date(expiresAt).toLocaleDateString("en-IN", {
                                day: "numeric", month: "short", year: "numeric",
                                hour: "2-digit", minute: "2-digit",
                              })}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Timestamp */}
                      <p className="text-xs text-muted-foreground">
                        {new Date(entry.created_at).toLocaleDateString("en-IN", {
                          day: "numeric", month: "short", year: "numeric",
                          hour: "2-digit", minute: "2-digit",
                        })}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Grant row sub-component ───────────────────────────────────────────────────

function GrantRow({
  grant,
  copiedId,
  revoking,
  onCopy,
  onRevoke,
}: {
  grant:    ShareGrant;
  copiedId: string | null;
  revoking: string | null;
  onCopy:   (g: ShareGrant) => void;
  onRevoke: (id: string) => void;
}) {
  const t = useTranslations("share");

  const expired  = isExpired(grant);
  const inactive = !grant.is_active || expired;

  const expiryText = (() => {
    if (!grant.is_active) return t("revoked");
    if (expired) return t("expired");
    const diff = Math.ceil(
      (new Date(grant.expires_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    );
    return t("expires_in_days", { days: diff });
  })();

  const scopeText = (() => {
    if (grant.scope_record_ids?.length)
      return t("scope_records", { count: grant.scope_record_ids.length });
    if (grant.scope_record_types?.length)
      return grant.scope_record_types.map((s) => s.replace("_", " ")).join(", ");
    return t("all_records");
  })();

  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border p-3 flex-wrap">
      <div className="min-w-0 space-y-0.5">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm truncate">
            {grant.recipient_name ?? "Unnamed recipient"}
          </span>
          {inactive ? (
            <Badge
              variant="secondary"
              className={`text-xs ${grant.is_active ? "" : "bg-slate-100 text-slate-500"}`}
            >
              {grant.is_active ? t("expired") : t("revoked")}
            </Badge>
          ) : (
            <Badge className="text-xs bg-green-100 text-green-800 border-green-200">
              {t("active")}
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {scopeText} · {expiryText}
        </p>
        <p className="text-xs text-muted-foreground font-mono">
          …{grant.token.slice(-8)}
        </p>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {/* Copy link — only for active, non-expired grants */}
        {!inactive && (
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={() => onCopy(grant)}
            aria-label={t("copy_link")}
          >
            {copiedId === grant.id ? (
              <Check className="h-3 w-3 text-green-600" aria-hidden="true" />
            ) : (
              <Link2 className="h-3 w-3" aria-hidden="true" />
            )}
          </Button>
        )}

        {/* Revoke — only for active, non-expired grants */}
        {!inactive && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-destructive hover:text-destructive hover:bg-destructive/10"
            disabled={revoking === grant.id}
            onClick={() => onRevoke(grant.id)}
            aria-label={t("revoke")}
          >
            {revoking === grant.id ? (
              <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
            ) : (
              <Trash2 className="h-3 w-3" aria-hidden="true" />
            )}
          </Button>
        )}
      </div>
    </div>
  );
}
