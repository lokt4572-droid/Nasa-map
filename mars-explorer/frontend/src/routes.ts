/**
 * Site pages and URL routing (no router dependency).
 *
 *   /        landing page        (components/LandingPage.tsx)
 *   /rover/  Curiosity profile   (components/RoverProfile.tsx)
 *   /map/    the planetary GIS workspace (components/layout/Explorer.tsx)
 *
 * To add a page (e.g. About): add an entry to PAGES and a case in App.tsx. Paths are relative
 * to Vite's BASE_URL, so the site also works when deployed under a sub-path. A static host must
 * serve index.html for every page path (SPA fallback; see docs/DEPLOYMENT.md).
 */
import { useEffect, useState } from "react";

export const PAGES = {
  home: { path: "/", title: "Nova" },
  rover: { path: "/rover/", title: "Curiosity rover — Nova" },
  map: { path: "/map/", title: "Map — Nova" },
} as const;

export type PageId = keyof typeof PAGES | "notfound";

const NAV_EVENT = "mars-explorer:navigate";

function base(): string {
  const b = (import.meta.env?.BASE_URL as string | undefined) ?? "/";
  return b.endsWith("/") ? b.slice(0, -1) : b;
}

/** Page for a URL pathname. Trailing slash optional; index.html accepted; unknown -> notfound. */
export function pageFor(pathname: string, basePath = base()): PageId {
  let p = pathname;
  if (basePath && p.startsWith(basePath)) p = p.slice(basePath.length);
  p = p.replace(/index\.html$/, "");
  if (!p.startsWith("/")) p = `/${p}`;
  if (!p.endsWith("/")) p = `${p}/`;
  for (const [id, page] of Object.entries(PAGES)) {
    if (page.path === p) return id as PageId;
  }
  return "notfound";
}

export function hrefFor(id: keyof typeof PAGES, basePath = base()): string {
  return `${basePath}${PAGES[id].path}`;
}

/** Client-side navigation (history entry; back/forward and refresh keep the page). */
export function navigate(id: keyof typeof PAGES): void {
  const href = hrefFor(id);
  if (window.location.pathname !== href) window.history.pushState({}, "", href);
  window.dispatchEvent(new Event(NAV_EVENT));
  window.scrollTo(0, 0);
}

export function usePage(): PageId {
  const [page, setPage] = useState<PageId>(() => pageFor(window.location.pathname));
  useEffect(() => {
    const update = () => setPage(pageFor(window.location.pathname));
    window.addEventListener("popstate", update);
    window.addEventListener(NAV_EVENT, update);
    return () => {
      window.removeEventListener("popstate", update);
      window.removeEventListener(NAV_EVENT, update);
    };
  }, []);
  useEffect(() => {
    document.title = page === "notfound" ? "Page not found — Nova" : PAGES[page].title;
  }, [page]);
  return page;
}
