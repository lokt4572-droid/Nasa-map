"""v0.4 backend benchmark: terrain patches (local and remote DEMs, cold and warm), elevation
profiles, catalogue searches and route planning, against a RUNNING backend.

    python scripts/benchmark_v04.py --api http://127.0.0.1:8000/api/v1 --out docs/perf/v04_backend.json

"cold" = first request for that DEM in this server process (remote: includes reading the COG
header and, for a new product, validation); "warm" = median of 3 repeats. Provider latency is
part of the remote numbers and varies between runs.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request

CRS = "urn:ogc:def:crs:EPSG::104905"


def call(url: str, body: dict | None = None, timeout: float = 300.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json", "User-Agent": "mars-explorer-benchmark"})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - operator-given URL
            payload = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        payload, status = e.read(), e.code
    dt = (time.perf_counter() - t) * 1000
    try:
        doc = json.loads(payload)
    except json.JSONDecodeError:
        doc = {}
    return status, dt, doc, len(payload)


def measure(name: str, fn, repeats: int = 3) -> dict:
    s, cold, doc, size = fn()
    warm = [fn()[1] for _ in range(repeats)]
    row = {"case": name, "status": s, "cold_ms": round(cold), "warm_median_ms": round(statistics.median(warm)), "bytes": size}
    print(f"{name:55s} HTTP {s}  cold {row['cold_ms']:>7} ms  warm {row['warm_median_ms']:>6} ms  {size:>8} B", flush=True)
    return {**row, "doc": doc}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    ap.add_argument("--out")
    a = ap.parse_args()
    api = a.api.rstrip("/")
    P = lambda lon, lat, planet="MARS", crs=CRS: {"lon_east_deg": lon, "lat_deg": lat, "crs": crs, "latitude_convention": "AS_DECLARED_BY_SOURCE", "planet": planet}
    cases = [
        ("patch MOLA 4 px/deg (local file), 256²", lambda: call(f"{api}/terrain/patch/?planet=MARS&lon=70&lat=10&max_dimension=256")),
        ("patch HiRISE Jezero (remote COG), 256²", lambda: call(f"{api}/terrain/patch/?planet=MARS&lon=77.45&lat=18.44&source=auto&max_dimension=256")),
        ("patch CTX/HiRISE Gusev (remote, new product), 256²", lambda: call(f"{api}/terrain/patch/?planet=MARS&lon=175.47&lat=-14.57&source=auto&max_dimension=256")),
        ("patch Kaguya TC Moon (remote), 256²", lambda: call(f"{api}/terrain/patch/?planet=MOON&lon=23.47&lat=0.67&source=auto&max_dimension=256")),
        ("patch Copernicus GLO-30 Alps (remote), 256²", lambda: call(f"{api}/terrain/patch/?planet=EARTH&lon=7.66&lat=45.98&source=auto&max_dimension=256")),
        ("profile HiRISE Jezero, 200 samples", lambda: call(f"{api}/terrain/profile/?planet=MARS&from_lon=77.44&from_lat=18.43&to_lon=77.46&to_lat=18.45&samples=200")),
        ("catalogue search USGS STAC (point)", lambda: call(f"{api}/datasets/coverage/?planet=MARS&longitude=137.4&latitude=-4.6")),
        ("catalogue search Copernicus (bbox)", lambda: call(f"{api}/datasets/search/?planet=EARTH&bbox=6.5,45.5,9.5,47.5")),
        ("route MOLA regional 740 km", lambda: call(f"{api}/routes/plan/", {"start": P(70, 15), "end": P(80, 22), "include_return": False})),
        ("route MOLA across lon 0 (seam)", lambda: call(f"{api}/routes/plan/", {"start": P(-2, 10), "end": P(2, 10), "include_return": False, "include_alternative": False})),
        ("route HiRISE Jezero 380 m (+return, alternative)", lambda: call(f"{api}/routes/plan/", {"start": P(77.4475, 18.4385), "end": P(77.4525, 18.4425), "terrain_source": "auto"})),
    ]
    rows = []
    for name, fn in cases:
        r = measure(name, fn)
        d = r.pop("doc")
        if "grid" in d and isinstance(d.get("grid"), dict) and "rows" in d["grid"]:
            r["route_grid"] = f"{d['grid']['rows']}x{d['grid']['cols']} cells, decimation {d['grid'].get('decimation_factor')}"
        if "dataset" in d and isinstance(d["dataset"], dict):
            r["dataset"] = d["dataset"].get("name") or d["dataset"].get("product_id")
        if "width" in d:
            r["grid"] = f"{d['width']}x{d['height']}, {d.get('resolution_m')} m DEM, nodata {d.get('nodata_percentage')} %"
        rows.append(r)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump({"date_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "api": api, "results": rows}, f, indent=2)
        print("written", a.out)


if __name__ == "__main__":
    main()
