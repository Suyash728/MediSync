"use client";

/**
 * SidebarNav — fixed left sidebar navigation component for the authenticated app.
 *
 * Requirements:
 *   - Fixed left sidebar on desktop (>=1024px), ~240px wide.
 *   - App logo/name at the top (Heart icon + "MediSync").
 *   - Nav links (Dashboard, Timeline, Alerts, Share, Settings) with lucide icons + labels.
 *   - Active-route highlighting via usePathname.
 *   - User profile info & sign-out affordance at the bottom.
 *   - Reuses existing shadcn components (Avatar, Button).
 *   - Uses the clinical slate/teal palette (no neon, no gradients).
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import { useTranslations } from "next-intl";
import {
  Heart,
  LayoutDashboard,
  Activity,
  Bell,
  Share2,
  Settings,
  LogOut,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import { createClient } from "@/lib/supabase";

// Navigation links configuration
const NAV_LINKS = [
  { href: "/dashboard", key: "dashboard", icon: LayoutDashboard },
  { href: "/timeline",  key: "timeline",  icon: Activity },
  { href: "/alerts",    key: "alerts",    icon: Bell },
  { href: "/share",     key: "share",     icon: Share2 },
  { href: "/settings",  key: "settings",  icon: Settings },
] as const;

interface SidebarNavProps {
  /** Display name of the signed-in patient (shown in avatar fallback). */
  userName?: string;
  /** URL of the patient's avatar image (optional). */
  userAvatar?: string;
  /** Patient's initials, derived server-side and passed in to avoid client fetch. */
  userInitials?: string;
}

export function SidebarNav({
  userName = "Patient",
  userAvatar,
  userInitials = "P",
}: SidebarNavProps) {
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations("nav");
  const [alertCount, setAlertCount] = useState(0);

  // Fetch unacknowledged conflict count; re-fetch when the app emits an update event.
  // Replicates the same logic as the existing AppShell to stay perfectly in sync.
  useEffect(() => {
    async function fetchAlertCount() {
      const supabase = createClient();
      const { count } = await supabase
        .from("drug_conflicts")
        .select("id", { count: "exact", head: true })
        .eq("is_acknowledged", false);
      setAlertCount(count ?? 0);
    }

    void fetchAlertCount();

    // Trigger update whenever there is an upload or conflict acknowledgement
    window.addEventListener("medisync:alerts-update", fetchAlertCount);
    return () => window.removeEventListener("medisync:alerts-update", fetchAlertCount);
  }, []);

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
  }

  return (
    <aside className="hidden lg:flex flex-col fixed inset-y-0 left-0 z-30 w-60 border-r bg-background">
      {/* ── Top Section: App Logo/Name ───────────────────────────────────── */}
      <div className="flex h-16 items-center px-6 border-b">
        <Link
          href="/dashboard"
          className="flex items-center gap-2.5 font-bold text-primary group"
          aria-label="MediSync home"
        >
          <div className="rounded-lg bg-primary/10 p-1.5 transition-transform group-hover:scale-105">
            <Heart className="h-5 w-5 fill-primary text-primary" aria-hidden="true" />
          </div>
          <span className="text-lg tracking-tight font-bold text-slate-800 dark:text-slate-100">
            MediSync
          </span>
        </Link>
      </div>

      {/* ── Middle Section: Main Navigation Links ─────────────────────────── */}
      <nav className="flex-1 space-y-1 px-4 py-6" aria-label="Sidebar navigation">
        {NAV_LINKS.map(({ href, key, icon: Icon }) => {
          const isActive =
            pathname === href || (href !== "/dashboard" && pathname.startsWith(href + "/"));
          const isAlerts = href === "/alerts";

          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center justify-between rounded-md px-3 py-2 text-sm font-medium transition-colors group",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-slate-100 hover:text-foreground dark:hover:bg-slate-900"
              )}
              aria-current={isActive ? "page" : undefined}
            >
              <div className="flex items-center gap-3">
                <Icon
                  className={cn(
                    "h-4 w-4 transition-colors",
                    isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                  )}
                  aria-hidden="true"
                />
                <span>{t(key)}</span>
              </div>

              {/* Dynamic Alerts Pill Counter */}
              {isAlerts && alertCount > 0 && (
                <span
                  className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1.5 text-[10px] font-bold text-destructive-foreground"
                  aria-label={`${alertCount} unacknowledged alerts`}
                >
                  {alertCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* ── Bottom Section: User Profile & Sign-out Affordance ────────────── */}
      <div className="mt-auto p-4 border-t bg-slate-50/50 dark:bg-slate-900/50">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-3 min-w-0">
            <Avatar className="h-9 w-9 border border-border">
              {userAvatar && <AvatarImage src={userAvatar} alt={userName} />}
              <AvatarFallback className="bg-primary/10 text-primary font-semibold text-sm">
                {userInitials}
              </AvatarFallback>
            </Avatar>
            <div className="flex flex-col min-w-0">
              <p className="text-sm font-semibold truncate text-slate-800 dark:text-slate-200">
                {userName}
              </p>
              <p className="text-xs text-muted-foreground truncate">
                Patient account
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleSignOut}
            className="text-muted-foreground hover:text-destructive hover:bg-destructive/10 h-8 w-8 rounded-md transition-colors"
            title="Sign out"
            aria-label="Sign out"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </aside>
  );
}
