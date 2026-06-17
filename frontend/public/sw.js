/**
 * MediSync service worker — minimal app-shell caching strategy.
 *
 * Cache-first: /icons/* and /_next/static/* (fingerprinted, never changes)
 * Network-first: everything else (API, pages, dynamic content)
 *
 * This intentionally does NOT cache API responses or patient records —
 * medical data must always come from the server to stay accurate.
 */

const SHELL_CACHE = "medisync-shell-v1";

const CACHE_FIRST_PATTERNS = [
  /^\/icons\//,
  /^\/_next\/static\//,
];

self.addEventListener("install", (event) => {
  // Skip waiting so the new SW activates immediately on first install.
  self.skipWaiting();
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) =>
      cache.addAll(["/icons/icon-192.png", "/icons/icon-512.png"])
    )
  );
});

self.addEventListener("activate", (event) => {
  // Remove any old cache versions.
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== SHELL_CACHE)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin GET requests.
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  const isCacheFirst = CACHE_FIRST_PATTERNS.some((re) => re.test(url.pathname));

  if (isCacheFirst) {
    event.respondWith(
      caches.match(request).then(
        (cached) => cached ?? fetch(request).then((resp) => {
          const clone = resp.clone();
          caches.open(SHELL_CACHE).then((c) => c.put(request, clone));
          return resp;
        })
      )
    );
  } else {
    // Network-first: try network, fall back to cache for navigations only.
    event.respondWith(
      fetch(request).catch(() => caches.match(request))
    );
  }
});
