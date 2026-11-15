"""Public smoke test for a MARS EXPLORER deployment (standard library only).

    python scripts/smoke_test.py --frontend https://your-frontend.example.org --api https://your-backend.example.org/api/v1

Checks what a judge's first visit needs: the site and its page paths load, static files load,
the API and its database answer, the planet list and a real map tile are reachable, Cesium's
status is reported, and a location without elevation data returns a clear "no data" answer
instead of an error. Prints one line per check and exits 1 if any check fails.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse

UA = "MARS-EXPLORER-smoke-test/0.4"


def fetch(url: str, *, method: str = "GET", headers: dict | None = None, body: bytes | None = None, timeout: float = 90.0):
    req = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": UA, **(headers or {})})
    t = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - URLs given by the operator
            return r.status, dict(r.headers), r.read(5_000_000), time.monotonic() - t
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(1_000_000), time.monotonic() - t


class Report:
    def __init__(self):
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}{' - ' + detail if detail else ''}", flush=True)
        return ok

    def info(self, name: str, detail: str):
        print(f"INFO  {name} - {detail}", flush=True)

    @property
    def failed(self) -> int:
        return sum(1 for _, ok, _ in self.rows if not ok)


def run(frontend: str, api: str) -> int:
    rep = Report()
    frontend = frontend.rstrip("/") + "/"
    api = api.rstrip("/")

    # 1-3 frontend, page paths (SPA fallback) and static files
    st, _, html, dt = fetch(frontend)
    page = html.decode("utf-8", "replace")
    rep.check("frontend responds", st == 200 and 'id="root"' in page, f"HTTP {st} in {dt:.1f} s")
    for path in ("map/", "rover/"):
        st2, _, h2, _ = fetch(urljoin(frontend, path))
        rep.check(f"/{path} opens the app (SPA fallback)", st2 == 200 and 'id="root"' in h2.decode("utf-8", "replace"), f"HTTP {st2}")
    assets = re.findall(r'<script[^>]*\ssrc="([^"]+)"', page) + re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', page)
    if assets:
        st3, hd, _, _ = fetch(urljoin(frontend, assets[0]))
        rep.check("static files load", st3 == 200, f"{assets[0]} HTTP {st3} {hd.get('Content-Type', '')}")
    else:
        rep.check("static files load", False, "no script/style found in index.html")

    # 4-5 API, database, version
    st, _, b, dt = fetch(f"{api}/health/")
    try:
        h = json.loads(b)
    except json.JSONDecodeError:
        h = {}
    rep.check("API health responds", st == 200 and h.get("status") == "ok", f"HTTP {st} in {dt:.1f} s (a sleeping free instance can take ~1 min)")
    rep.check("database connection", h.get("database") == "ok", str(h.get("database")))
    rep.check("API version reported", bool(h.get("version")), str(h.get("version")))
    rep.check("raster backend (GDAL) available", bool((h.get("raster_backend") or {}).get("available")), str((h.get("raster_backend") or {}).get("backend")))

    # 6 CORS from the frontend origin
    origin = f"{urlparse(frontend).scheme}://{urlparse(frontend).netloc}"
    st, hd, _, _ = fetch(f"{api}/health/", headers={"Origin": origin})
    allowed = {k.lower(): v for k, v in hd.items()}.get("access-control-allow-origin")
    same_origin = urlparse(api).netloc in ("", urlparse(frontend).netloc)
    rep.check("CORS allows the frontend origin", same_origin or allowed in (origin, "*"), f"allow-origin={allowed!r}")

    # 7 planet selector data and a real map layer tile
    st, _, b, _ = fetch(f"{api}/planets/")
    planets = [p.get("id") for p in json.loads(b)] if st == 200 else []
    rep.check("planet selector data", "MARS" in planets and "EARTH" in planets, ", ".join(planets))
    st, _, b, _ = fetch(f"{api}/planets/MARS/layers/")
    layers = json.loads(b) if st == 200 else []
    if layers:
        tile = layers[0]["capabilities_url"].replace("/1.0.0/WMTSCapabilities.xml", "/1.0.0/default/default028mm/0/0/0.jpg")
        st, hd, _, dt = fetch(tile)
        rep.check("a map layer tile loads (NASA Trek)", st == 200 and hd.get("Content-Type", "").startswith("image/"), f"HTTP {st} in {dt:.1f} s")
    else:
        rep.check("a map layer tile loads (NASA Trek)", False, "no Mars layer listed")

    # 8 Cesium status (the token lives in the browser bundle; the backend never holds it)
    st, _, b, _ = fetch(f"{api}/health/providers/")
    ces = (json.loads(b).get("sources") or {}).get("Cesium ion", {}) if st == 200 else {}
    rep.check("Cesium status reported", ces.get("status") == "NOT_PROBED", ces.get("reason", "missing"))
    rep.info("Cesium in the browser", "open /map/ -> Mars -> 3D TILES: 'STREAMING' with a token, 'REQUIRES_USER_CONFIGURATION' without")

    # 9 missing DEM is a clear answer, not a crash
    st, _, b, _ = fetch(f"{api}/terrain/sample/?planet=MOON&lon=10&lat=10")
    try:
        code = json.loads(b).get("error", {}).get("code")
    except json.JSONDecodeError:
        code = None
    rep.check("missing DEM returns NO DATA (not a crash)", st == 404 and code == "DEM_NOT_AVAILABLE", f"HTTP {st} {code}")

    # 10 public demo protection (informational: depends on PUBLIC_READ_ONLY)
    st, _, b, _ = fetch(f"{api}/missions/", method="POST", headers={"Content-Type": "application/json"},
                        body=json.dumps({"name": "smoke-test", "description": "", "status": "PLANNED"}).encode())
    if st == 403:
        rep.info("public demo protection", "read-only: shared records cannot be changed (PUBLIC_READ_ONLY)")
    else:
        rep.info("public demo protection", f"OFF (POST /missions/ -> HTTP {st}); set PUBLIC_READ_ONLY=True for a public demo")
        if st in (200, 201):
            mid = json.loads(b).get("id")
            if mid:
                fetch(f"{api}/missions/{mid}/", method="DELETE")  # remove the smoke-test record it just created

    print(f"\n{len(rep.rows) - rep.failed}/{len(rep.rows)} checks passed")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--frontend", required=True, help="public frontend URL, e.g. https://example.org/")
    ap.add_argument("--api", required=True, help="API base URL ending in /api/v1")
    a = ap.parse_args()
    sys.exit(run(a.frontend, a.api))
