"use client";

/**
 * AppShell — persistent top navigation bar rendered inside the (patient) layout.
 *
 * Contains:
 *   - Logo (Heart icon + "MediSync" wordmark)
 *   - Primary nav links (Dashboard, Timeline, Alerts, Share)
 *   - Mobile hamburger (collapses links)
 *   - User avatar dropdown (Settings, Sign out)
 *
 * This is a Client Component because it reads the active pathname for link
 * highlighting and calls createClient() for the sign-out action.
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
  Menu,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import { createClient } from "@/lib/supabase";

// Nav link definitions — labels are resolved from the "nav" translation namespace at render time
const NAV_LINKS = [
  { href: "/dashboard", key: "dashboard", icon: LayoutDashboard },
  { href: "/timeline",  key: "timeline",  icon: Activity },
  { href: "/alerts",    key: "alerts",    icon: Bell },
  { href: "/share",     key: "share",     icon: Share2 },
] as const;

interface AppShellProps {
  /** Display name of the signed-in patient (shown in avatar fallback). */
  userName?: string;
  /** URL of the patient's avatar image (optional). */
  userAvatar?: string;
  /** Patient's initials, derived server-side and passed in to avoid a client fetch. */
  userInitials?: string;
}

export function AppShell({
  userName = "Patient",
  userAvatar,
  userInitials = "P",
}: AppShellProps) {
  const pathname = usePathname();
  const router   = useRouter();
  const t        = useTranslations("nav");
  const [mobileOpen,  setMobileOpen]  = useState(false);
  const [alertCount,  setAlertCount]  = useState(0);

  // Fetch unacknowledged conflict count; re-fetch when the app emits an update event
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

    // Other parts of the app dispatch this event after upload or acknowledgement
    window.addEventListener("medisync:alerts-update", fetchAlertCount);
    return () => window.removeEventListener("medisync:alerts-update", fetchAlertCount);
  }, []);

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
  }

  return (
    <header className="sticky top-0 z-40 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center justify-between">

        {/* ── Logo ─────────────────────────────────────────────────────── */}
        <Link
          href="/dashboard"
          className="flex items-center gap-2 font-semibold text-primary"
          aria-label="MediSync home"
        >
          <Heart className="h-5 w-5 fill-primary" aria-hidden="true" />
          <span className="text-lg tracking-tight">MediSync</span>
        </Link>

        {/* ── Desktop nav ───────────────────────────────────────────────── */}
        <nav className="hidden md:flex items-center gap-1" aria-label="Main navigation">
          {NAV_LINKS.map(({ href, key, icon: Icon }) => {
            const isAlerts = href === "/alerts";
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  pathname === href || pathname.startsWith(href + "/")
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
                aria-current={pathname === href ? "page" : undefined}
              >
                {/* Red dot badge for unacknowledged alerts */}
                <span className="relative inline-flex">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {isAlerts && alertCount > 0 && (
                    <span
                      className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-red-500"
                      aria-label={`${alertCount} unacknowledged alert${alertCount !== 1 ? "s" : ""}`}
                    />
                  )}
                </span>
                {t(key)}
              </Link>
            );
          })}
        </nav>

        {/* ── Right side: user menu + mobile toggle ─────────────────────── */}
        <div className="flex items-center gap-2">

          {/* User avatar dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="relative h-9 w-9 rounded-full"
                aria-label={`Open user menu for ${userName}`}
              >
                <Avatar className="h-9 w-9">
                  {userAvatar && <AvatarImage src={userAvatar} alt={userName} />}
                  <AvatarFallback className="bg-primary/10 text-primary font-semibold text-sm">
                    {userInitials}
                  </AvatarFallback>
                </Avatar>
              </Button>
            </DropdownMenuTrigger>

            <DropdownMenuContent className="w-52" align="end" forceMount>
              <DropdownMenuLabel className="font-normal">
                <div className="flex flex-col space-y-1">
                  <p className="text-sm font-medium leading-none">{userName}</p>
                  <p className="text-xs leading-none text-muted-foreground">Patient account</p>
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />

              <DropdownMenuItem asChild>
                <Link href="/settings" className="cursor-pointer">
                  <Settings className="mr-2 h-4 w-4" aria-hidden="true" />
                  {t("settings")}
                </Link>
              </DropdownMenuItem>

              <DropdownMenuSeparator />

              <DropdownMenuItem
                className="text-destructive focus:text-destructive cursor-pointer"
                onClick={handleSignOut}
              >
                <LogOut className="mr-2 h-4 w-4" aria-hidden="true" />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Mobile hamburger */}
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={() => setMobileOpen((o) => !o)}
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileOpen}
          >
            {mobileOpen
              ? <X className="h-5 w-5" aria-hidden="true" />
              : <Menu className="h-5 w-5" aria-hidden="true" />
            }
          </Button>
        </div>
      </div>

      {/* ── Mobile nav drawer ─────────────────────────────────────────────── */}
      {mobileOpen && (
        <nav
          className="md:hidden border-t bg-background px-4 py-3 space-y-1"
          aria-label="Mobile navigation"
        >
          {NAV_LINKS.map(({ href, key, icon: Icon }) => {
            const isAlerts = href === "/alerts";
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  pathname === href
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-accent"
                )}
                aria-current={pathname === href ? "page" : undefined}
              >
                <span className="relative inline-flex">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {isAlerts && alertCount > 0 && (
                    <span
                      className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-red-500"
                      aria-label={`${alertCount} unacknowledged alert${alertCount !== 1 ? "s" : ""}`}
                    />
                  )}
                </span>
                {t(key)}
              </Link>
            );
          })}
        </nav>
      )}
    </header>
  );
}
