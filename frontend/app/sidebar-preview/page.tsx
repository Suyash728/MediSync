"use client";

import { useState } from "react";
import { SidebarNav } from "@/components/SidebarNav";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Play, RotateCcw, AlertTriangle, ShieldCheck } from "lucide-react";

export default function SidebarPreviewPage() {
  const [simulatedAlertCount, setSimulatedAlertCount] = useState(0);

  // Function to simulate backend updating conflict alerts
  const handleAddAlert = () => {
    // We increment a local state for the UI, but we can also fire the custom event
    // that the SidebarNav component listens to. Since SidebarNav queries Supabase on mount/update,
    // firing the event will cause SidebarNav to re-fetch from the database.
    // If the database has 0, it will query 0. To demonstrate real-time reactivity in the sandbox,
    // we dispatch the event and print a notice.
    const event = new CustomEvent("medisync:alerts-update");
    window.dispatchEvent(event);
    setSimulatedAlertCount(prev => prev + 1);
  };

  const handleResetAlerts = () => {
    const event = new CustomEvent("medisync:alerts-update");
    window.dispatchEvent(event);
    setSimulatedAlertCount(0);
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100">
      {/* ── Left Sidebar (Desktop Only) ─────────────────────────────────── */}
      <SidebarNav
        userName="Rahul Verma"
        userInitials="RV"
        userAvatar=""
      />

      {/* ── Right Content Area ─────────────────────────────────────────── */}
      <div className="lg:pl-60 flex flex-col min-h-screen">
        {/* Top bar replica */}
        <header className="h-16 border-b bg-white dark:bg-slate-950 flex items-center px-8 justify-between">
          <h1 className="font-semibold text-lg">Sidebar Component Sandbox</h1>
          <div className="text-xs text-muted-foreground bg-slate-100 dark:bg-slate-900 px-2.5 py-1 rounded-full">
            Route: /sidebar-preview
          </div>
        </header>

        {/* Main body */}
        <main className="flex-1 p-8 max-w-4xl space-y-6">
          <Card className="border-slate-200 dark:border-slate-800">
            <CardHeader>
              <CardTitle className="text-primary text-2xl font-bold">Reviewing the Sidebar Component</CardTitle>
              <CardDescription>
                This sandbox displays the new desktop sidebar navigation component on the left side of the screen (on displays &gt;= 1024px).
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                The sidebar is built in complete isolation using **Next.js 14 client component hooks** (`usePathname`, `useRouter`), **shadcn components**, and **lucide-react** icons. It incorporates the clinical teal/slate theme colors and respects the localization settings of the app.
              </p>
              
              <div className="bg-slate-100 dark:bg-slate-905 p-4 rounded-lg border text-sm space-y-2">
                <h4 className="font-semibold text-slate-700 dark:text-slate-300">Key Features to Notice:</h4>
                <ul className="list-disc pl-5 space-y-1 text-slate-600 dark:text-slate-400">
                  <li><strong>Desktop Fixed Layout:</strong> Shrink/expand the browser width. The sidebar will hide below 1024px (mobile) and display perfectly on desktop.</li>
                  <li><strong>Active Highlighting:</strong> Hover over the links. The links use the primary teal background highlights (`bg-primary/10 text-primary`) when active (based on pathname). Since we are currently on `/sidebar-preview`, no routes are highlighted, but they will be once integrated.</li>
                  <li><strong>User Profile Card:</strong> Renders the user avatar fallbacks ("RV" for Rahul Verma) and patient profile info cleanly at the bottom.</li>
                  <li><strong>Sign-out Affordance:</strong> The exit button at the bottom invokes Supabase sign-out and routes back to `/login`.</li>
                </ul>
              </div>
            </CardContent>
          </Card>

          {/* Real-time event demonstration */}
          <Card className="border-slate-200 dark:border-slate-800">
            <CardHeader>
              <CardTitle className="text-lg font-semibold flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-amber-500" />
                Dynamic Alert Counter Verification
              </CardTitle>
              <CardDescription>
                The SidebarNav component listens for the custom <code>medisync:alerts-update</code> event to re-fetch the unacknowledged conflict counts from Supabase.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-slate-600 dark:text-slate-400">
                You can trigger the update event below. When you click, a window event is dispatched. The SidebarNav will query Supabase for the exact count of active drug interactions.
              </p>
              
              <div className="flex flex-wrap gap-3">
                <Button 
                  onClick={handleAddAlert}
                  className="bg-primary text-primary-foreground hover:bg-primary/90"
                >
                  <Play className="mr-2 h-4 w-4" />
                  Trigger Alerts Update Event
                </Button>
                <Button 
                  variant="outline"
                  onClick={handleResetAlerts}
                >
                  <RotateCcw className="mr-2 h-4 w-4" />
                  Reset Event
                </Button>
              </div>

              {simulatedAlertCount > 0 && (
                <div className="p-3 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900 rounded-md flex items-center gap-3 text-sm text-red-800 dark:text-red-300">
                  <AlertTriangle className="h-4 w-4 text-red-500 animate-bounce" />
                  <span>
                    Simulated Event dispatched! SidebarNav triggered a database re-fetch for unacknowledged conflicts.
                  </span>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border-slate-200 dark:border-slate-800">
            <CardHeader>
              <CardTitle className="text-lg font-semibold flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-emerald-500" />
                Integration Status
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
                Once you approve this component, we can easily wire it into the main authenticated patient layout ([layout.tsx](file:///home/arya/Projects/MediSync/frontend/app/%28patient%29/layout.tsx)) to make it persistent across all patient pages.
              </p>
              <div className="text-xs text-muted-foreground border-l-2 border-primary pl-3 py-1 font-mono">
                Component Location: frontend/components/SidebarNav.tsx
              </div>
            </CardContent>
          </Card>
        </main>
      </div>
    </div>
  );
}
