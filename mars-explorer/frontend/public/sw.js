/* MARS EXPLORER service worker — app shell only.
 *
 * Caches: same-origin index.html and built static files (/assets/*, /cesiumStatic/*, /images1/*).
 * Every page path (/, /rover/, /map/) is the same single-page app: offline navigations get the
 * cached index.html, and the app picks the page from the URL.
 * Never caches: cross-origin requests (OpenStreetMap, NASA GIBS/Trek tiles — their terms
 * do not allow offline prefetch/redistribution), and /api/* (data lives in IndexedDB).
 * This does NOT make the map work offline: tiles always need the network.
 */
const VERSION = "mars-explorer-shell-v4"; // bump on every change to what is cached

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
  if (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/cesiumStatic/") || url.pathname.startsWith("/images1/")) {
    // Hashed / versioned static files: cache first, fill on use.
    // The copy must be taken BEFORE the response is returned: once the page starts reading the
    // body, clone() throws and nothing would be cached (v0.3 bug: offline start had no scripts).
    event.respondWith(
      caches.match(req).then(
        (hit) => hit || fetch(req).then((res) => {
          if (res.ok) {
            const copy = res.clone();
            event.waitUntil(caches.open(VERSION).then((c) => c.put(req, copy)));
          }
          return res;
        }),
      ),
    );
  }
});
