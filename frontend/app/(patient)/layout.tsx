/**
 * Patient layout — Server Component that:
 *   1. Verifies the Supabase session (middleware already guards the route, but
 *      we verify again here to get user data for the AppShell).
 *   2. Fetches the patient's profile (full_name) for the nav avatar.
 *   3. Renders AppShell + page content.
 *
 * We redirect to /login if the session is missing (belt-and-suspenders; the
 * middleware should have already caught unauthenticated requests).
 */

import { redirect } from "next/navigation";
import { SidebarNav } from "@/components/SidebarNav";
import { FloatingChat } from "@/components/FloatingChat";
import { createServerSupabaseClient } from "@/lib/supabase";

export default async function PatientLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createServerSupabaseClient();

  // getUser() verifies the JWT on the server — never trust getSession() alone
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Fetch the patient's display name from the profiles table
  const { data: profile } = await supabase
    .from("profiles")
    .select("full_name")
    .eq("id", user.id)
    .single();

  const fullName = profile?.full_name ?? "Patient";
  // Build initials from first and last word of the name
  const initials = fullName
    .split(" ")
    .filter(Boolean)
    .map((n: string) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="min-h-screen flex flex-col lg:flex-row bg-slate-50">
      <SidebarNav userName={fullName} userInitials={initials} />
      <div className="flex-1 lg:pl-60 flex flex-col min-h-screen">
        <main className="flex-1 container py-8">
          {children}
        </main>
        <FloatingChat />
      </div>
    </div>
  );
}
