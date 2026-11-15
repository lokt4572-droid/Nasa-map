/* MARS EXPLORER service worker — app shell only.
 *
 * Caches: same-origin index.html and built static files (/assets/*, /cesiumStatic/*).
 * Never caches: cross-origin requests (OpenStreetMap, NASA GIBS/Trek tiles — their terms
 * do not allow offline prefetch/redistribution), and /api/* (data lives in IndexedDB).
 * This does NOT make the map work offline: tiles always need the network.
 */
const VERSION = "mars-explorer-shell-v2";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(["/", "/index.html"])).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return; // network only
  if (req.mode === "navigate") {
    // Network first; offline -> cached shell.
    event.respondWith(fetch(req).catch(() => caches.match("/index.html")));
    return;
  }
  if (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/cesiumStatic/")) {
    // Hashed / versioned static files: cache first, fill on use.
    event.respondWith(
      caches.match(req).then(
        (hit) => hit || fetch(req).then((res) => {
          if (res.ok) caches.open(VERSION).then((c) => c.put(req, res.clone()));
          return res;
        }),
      ),
    );
  }
});
