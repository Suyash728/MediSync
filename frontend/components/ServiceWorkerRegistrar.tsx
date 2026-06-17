"use client";

import { useEffect } from "react";

/** Registers /sw.js once the page is interactive. No-ops on browsers without SW support. */
export default function ServiceWorkerRegistrar() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch((err) => {
        console.warn("SW registration failed:", err);
      });
    }
  }, []);

  return null;
}
