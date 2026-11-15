"""Network baseline for map layers (server side of map performance; no browser involved).

For each WMTS layer it reads the REAL GetCapabilities, derives the tile grid (TileMatrix ids,
matrix sizes, top-left corner, tile size, bounding box) and requests the tiles a 1280x800
viewport would need at three views: GLOBAL, REGIONAL and LOCAL (centred on a point inside the
layer's coverage). It records HTTP status, duration and size per tile and prints per-layer
statistics. Results are written as JSON for docs/PERFORMANCE_REPORT_V0.3.md.

Usage (PowerShell, from mars-explorer/):
    backend\\.venv\\Scripts\\python.exe scripts\\benchmark_tiles.py --out docs\\perf\\baseline.json

Polite by design: sequential-per-layer with a small thread pool (4), a hard cap of 60 tiles per
view, and it never touches tile.openstreetmap.org (OSMF policy forbids benchmarking/bulk use).
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = "MARS-EXPLORER/0.3 benchmark (planetary GIS prototype; local)"
NS = {"w": "http://www.opengis.net/wmts/1.0", "ows": "http://www.opengis.net/ows/1.1"}
VIEW_W, VIEW_H, TILE = 1280, 800, 256
MAX_TILES = 60

TREK = "https://trek.nasa.gov/tiles"
LAYERS = [
    # body, caps URL, layer id, point of interest inside coverage (lon, lat)
    ("MARS", f"{TREK}/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/WMTSCapabilities.xml", "Mars_MGS_MOLA_ClrShade_merge_global_463m", (77.4, 18.4)),
    ("MARS", f"{TREK}/Mars/EQ/Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw/1.0.0/WMTSCapabilities.xml", "Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw", (77.4, 18.4)),
    ("MARS", f"{TREK}/Mars/EQ/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0/1.0.0/WMTSCapabilities.xml", "JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0", (77.43, 18.47)),
    ("MARS", f"{TREK}/Mars/EQ/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd/1.0.0/WMTSCapabilities.xml", "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd", (77.40, 18.47)),
    ("MOON", f"{TREK}/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/WMTSCapabilities.xml", "LRO_WAC_Mosaic_Global_303ppd_v02", (23.47, 0.67)),
    ("MERCURY", f"{TREK}/Mercury/EQ/Mercury_MESSENGER_mosaic_global_250m_2013/1.0.0/WMTSCapabilities.xml", "Mercury_MESSENGER_mosaic_global_250m_2013", (0.0, 0.0)),
]


def fetch(url: str, timeout: float = 20.0) -> tuple[int, float, int, str]:
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, (time.perf_counter() - t0) * 1000, len(body), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, (time.perf_counter() - t0) * 1000, 0, ""
    except Exception as e:  # noqa: BLE001
        return -1, (time.perf_counter() - t0) * 1000, 0, type(e).__name__


def parse_grid(xml: bytes, layer_id: str) -> dict:
    root = ET.fromstring(xml)
    layer = next(l for l in root.iterfind(".//w:Contents/w:Layer", NS) if l.findtext("ows:Identifier", namespaces=NS) == layer_id)
    tms_id = layer.findtext("w:TileMatrixSetLink/w:TileMatrixSet", namespaces=NS)
    style = next((s.findtext("ows:Identifier", namespaces=NS) for s in layer.iterfind("w:Style", NS)), "default")
    template = layer.find("w:ResourceURL", NS).get("template")
    lc = [float(v) for v in layer.findtext("ows:BoundingBox/ows:LowerCorner", namespaces=NS).split()]
    uc = [float(v) for v in layer.findtext("ows:BoundingBox/ows:UpperCorner", namespaces=NS).split()]
    tms = next(t for t in root.iterfind(".//w:Contents/w:TileMatrixSet", NS) if t.findtext("ows:Identifier", namespaces=NS) == tms_id)
    matrices = []
    for m in tms.iterfind("w:TileMatrix", NS):
        tl = [float(v) for v in m.findtext("w:TopLeftCorner", namespaces=NS).split()]
        mw = int(float(m.findtext("w:MatrixWidth", namespaces=NS)))
        mh = int(float(m.findtext("w:MatrixHeight", namespaces=NS)))
        tw = int(float(m.findtext("w:TileWidth", namespaces=NS)))
        # degrees per tile from matrix size (decimal-degree grids over 360 x 180)
        matrices.append({"id": m.findtext("ows:Identifier", namespaces=NS), "tl": tl, "w": mw, "h": mh, "tile": tw, "deg_per_tile": 360.0 / mw})
    limits = layer.find("w:TileMatrixSetLink/w:TileMatrixSetLimits", NS)
    return {"tms": tms_id, "style": style, "template": template, "bbox": lc + uc, "matrices": matrices, "has_limits": limits is not None}


def tiles_for_view(grid: dict, level: int, lon: float, lat: float) -> list[tuple[int, int]]:
    m = grid["matrices"][level]
    d = m["deg_per_tile"]
    deg_px = d / m["tile"]
    half_w, half_h = VIEW_W * deg_px / 2, VIEW_H * deg_px / 2
    w, s, e, n = lon - half_w, lat - half_h, lon + half_w, lat + half_h
    bw, bs, be, bn = grid["bbox"]
    w, s, e, n = max(w, bw), max(s, bs), min(e, be), min(n, bn)  # stay inside declared coverage
    if w >= e or s >= n:
        return []
    c0, c1 = int((w - m["tl"][0]) // d), int((e - m["tl"][0]) // d)
    r0, r1 = int((m["tl"][1] - n) // d), int((m["tl"][1] - s) // d)
    out = [(r, c) for r in range(max(r0, 0), min(r1, m["h"] - 1) + 1) for c in range(max(c0, 0), min(c1, m["w"] - 1) + 1)]
    return out[:MAX_TILES]


def pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    return round(s[min(len(s) - 1, int(math.ceil(p / 100 * len(s))) - 1)], 1)


def run_layer(body: str, caps_url: str, layer_id: str, poi: tuple[float, float]) -> dict:
    st, ms, size, _ = fetch(caps_url)
    res = {"body": body, "layer": layer_id, "capabilities": {"status": st, "ms": round(ms, 1), "bytes": size}, "views": {}}
    if st != 200:
        return res
    grid = parse_grid(urllib.request.urlopen(urllib.request.Request(caps_url, headers={"User-Agent": UA}), timeout=30).read(), layer_id)
    res["grid"] = {"tms": grid["tms"], "levels": len(grid["matrices"]), "ids": [m["id"] for m in grid["matrices"]], "bbox": grid["bbox"], "TileMatrixSetLimits": grid["has_limits"]}
    n = len(grid["matrices"])
    views = {"GLOBAL": 1, "REGIONAL": max(1, n // 2), "LOCAL": n - 1}
    for vname, level in views.items():
        tiles = tiles_for_view(grid, level, *poi)
        urls = [grid["template"].replace("{Style}", grid["style"]).replace("{TileMatrixSet}", grid["tms"]).replace("{TileMatrix}", grid["matrices"][level]["id"]).replace("{TileRow}", str(r)).replace("{TileCol}", str(c)) for r, c in tiles]
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(fetch, urls))
        wall = (time.perf_counter() - t0) * 1000
        ok = [r for r in results if r[0] == 200]
        durs = [r[1] for r in ok]
        statuses: dict[str, int] = {}
        for r in results:
            statuses[str(r[0])] = statuses.get(str(r[0]), 0) + 1
        res["views"][vname] = {
            "matrix": grid["matrices"][level]["id"], "tiles": len(urls), "status_counts": statuses,
            "success_pct": round(100 * len(ok) / len(urls), 1) if urls else None,
            "avg_ms": round(statistics.mean(durs), 1) if durs else None, "p95_ms": pct(durs, 95),
            "wall_ms_4_parallel": round(wall, 1), "avg_kb": round(statistics.mean([r[2] for r in ok]) / 1024, 1) if ok else None,
        }
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out = {"started_utc": started, "viewport_px": [VIEW_W, VIEW_H], "layers": []}
    for spec in LAYERS:
        r = run_layer(*spec)
        out["layers"].append(r)
        print(f"{r['body']:8} {r['layer'][:46]:46} caps {r['capabilities']['status']} {r['capabilities']['ms']:.0f}ms")
        for v, d in r.get("views", {}).items():
            print(f"   {v:8} m={d['matrix']:>3} tiles={d['tiles']:>3} ok={d['success_pct']}% status={d['status_counts']} avg={d['avg_ms']}ms p95={d['p95_ms']}ms wall={d['wall_ms_4_parallel']:.0f}ms")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print("written", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
