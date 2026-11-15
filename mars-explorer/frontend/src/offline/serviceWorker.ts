/**
 * Service Worker registration (production builds only: in development it would cache
 * Vite modules and break hot reload). See public/sw.js for what is (and is not) cached.
 */
export type SwStatus = "UNSUPPORTED" | "DEV_DISABLED" | "REGISTERING" | "ACTIVE" | "FAILED";

let status: SwStatus = "REGISTERING";
const listeners = new Set<(s: SwStatus) => void>();
const set = (s: SwStatus) => {
  status = s;
  listeners.forEach((l) => l(s));
};

export function serviceWorkerStatus(): SwStatus {
  return status;
}
export function onServiceWorkerStatus(fn: (s: SwStatus) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function registerServiceWorker(isProd: boolean = import.meta.env.PROD, nav: Navigator | undefined = typeof navigator === "undefined" ? undefined : navigator): void {
  if (!nav || !("serviceWorker" in nav)) return set("UNSUPPORTED");
  if (!isProd) return set("DEV_DISABLED");
  nav.serviceWorker
    .register(`${import.meta.env.BASE_URL}sw.js`)
    .then(() => set("ACTIVE"))
    .catch(() => set("FAILED"));
}
