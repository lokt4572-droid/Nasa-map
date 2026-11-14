"""Check the local Mars data directory and the raster backend.

Usage (PowerShell, project root, backend venv active):
    python scripts\\check_data.py
    python scripts\\check_data.py --data-dir D:\\mars-data

Reports: whether the expected folder layout exists, which raster/label files are in
raw/ and processed/, whether GDAL can open each one, and whether GDAL/PROJ are usable.
It never modifies files. Registration is done with `python manage.py import_dem`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from services import dem_reader  # noqa: E402

EXPECTED = [
    "raw/mola", "raw/hirise", "raw/hrsc", "raw/ctx",
    "processed/dem", "processed/slope", "processed/hillshade", "processed/roughness",
    "metadata",
]
# Files GDAL can open directly. PDS3 .IMG are opened through their .LBL/.lbl label;
# PDS4 products through their .xml label.
RASTER_EXT = {".tif", ".tiff", ".img", ".lbl", ".xml", ".cub", ".jp2", ".vrt"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", type=Path, default=ROOT / "data" / "mars")
    args = p.parse_args()
    d: Path = args.data_dir.resolve()

    print(f"Data directory: {d}")
    if not d.is_dir():
        print("  MISSING — create it (see data/mars/README.md)")
        return 1
    for sub in EXPECTED:
        print(f"  [{'ok' if (d / sub).is_dir() else 'MISSING'}] {sub}")

    st = dem_reader.raster_backend_status()
    print(f"\nRaster backend: {'available — ' + st['backend'] + ', GDAL ' + st['gdal_version'] if st['available'] else 'NOT AVAILABLE'}")
    if st["available"]:
        print(f"  planetary drivers: {', '.join(st['planetary_drivers'])}")
    else:
        print(f"  {st['error']}")

    files = [f for f in d.rglob("*") if f.is_file() and f.suffix.lower() in RASTER_EXT]
    print(f"\nCandidate raster/label files: {len(files)}")
    for f in sorted(files):
        size_mb = f.stat().st_size / 1e6
        line = f"  {f.relative_to(d)}  ({size_mb:,.1f} MB)"
        if st["available"]:
            try:
                info = dem_reader.inspect_raster(f)
                line += f"  -> {info.driver} {info.width}x{info.height} {info.dtype} crs={info.crs_name or 'NONE'} units={info.band_units or '?'}"
            except Exception as exc:  # noqa: BLE001 - report and continue
                line += f"  -> not a raster GDAL can open ({type(exc).__name__})"
        print(line)
    if not files:
        print("  none — download a DEM first (see data/mars/README.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
