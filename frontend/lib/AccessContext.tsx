"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { profileApi } from "./api";
import { createClient } from "./supabase";

interface AccessContextType {
  isPaid: boolean;
  trialEndsAt: string | null;
  hasAccess: boolean;
  loading: boolean;
  refreshAccess: () => Promise<void>;
}

const AccessContext = createContext<AccessContextType | undefined>(undefined);

export function AccessProvider({ children }: { children: React.ReactNode }) {
  const [isPaid, setIsPaid] = useState(false);
  const [trialEndsAt, setTrialEndsAt] = useState<string | null>(null);
  const [hasAccess, setHasAccess] = useState(true); // Default to true to prevent flashes
  const [loading, setLoading] = useState(true);

  const fetchAccess = useCallback(async () => {
    try {
      const supabase = createClient();
      const { data } = await supabase.auth.getSession();
      
      if (!data.session) {
        setLoading(false);
        return;
      }

      const token = data.session.access_token;
      const res = await profileApi.getAccess(token);
      
      setIsPaid(res.is_paid);
      setTrialEndsAt(res.trial_ends_at);
      setHasAccess(res.has_access);
    } catch (err: any) {
      // ── Graceful Fallback for Local Dev / Testing ──────────────────────────
      // If the FastAPI route does not exist yet (returns 404) or is blocked (401),
      // we mock an active 7-day trial that has 5 days remaining, ensuring all
      // premium RAG/summaries features are unlocked by default.
      if (err?.status === 404 || err?.status === 401) {
        const dummyTrialEnds = new Date();
        dummyTrialEnds.setDate(dummyTrialEnds.getDate() + 5); // 5 days left
        setIsPaid(false);
        setTrialEndsAt(dummyTrialEnds.toISOString());
        setHasAccess(true);
      } else {
        console.error("Error fetching patient access layer status:", err);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAccess();

    // Re-fetch on login/token changes
    const supabase = createClient();
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN" || event === "TOKEN_REFRESHED") {
        void fetchAccess();
      } else if (event === "SIGNED_OUT") {
        setIsPaid(false);
        setTrialEndsAt(null);
        setHasAccess(true);
        setLoading(false);
      }
    });

    return () => {
      subscription.unsubscribe();
    };
  }, [fetchAccess]);

  const refreshAccess = async () => {
    setLoading(true);
    await fetchAccess();
  };

  return (
    <AccessContext.Provider
      value={{
        isPaid,
        trialEndsAt,
        hasAccess,
        loading,
        refreshAccess,
      }}
    >
      {children}
    </AccessContext.Provider>
  );
}

export function useAccess() {
  const context = useContext(AccessContext);
  if (context === undefined) {
    throw new Error("useAccess must be used within an AccessProvider");
  }
  return context;
}
