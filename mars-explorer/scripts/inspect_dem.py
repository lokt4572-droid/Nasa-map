"""Inspect a DEM raster with GDAL (via rasterio) without registering it.

Usage (PowerShell, from the project root, backend venv active):
    python scripts\\inspect_dem.py "data\\mars\\raw\\mola\\<product>.xml"
    python scripts\\inspect_dem.py FILE --sample 77.45 18.44 --crs ESRI:104971

Prints the metadata the importer will check (driver, size, CRS, bounds, units, nodata)
and the validation result. With --sample it reads the nearest cell value at a point.
The file is opened read-only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from services import dem_reader  # noqa: E402
from services.dataset_manager import validate_dem  # noqa: E402
from services.mars_coordinates import resolve_crs  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", type=Path)
    p.add_argument("--units", default=None, help="Elevation units if absent from the file")
    p.add_argument("--sample", nargs=2, type=float, metavar=("LON", "LAT"))
    p.add_argument("--crs", default="ESRI:104971", help="CRS of --sample coordinates (default Mars 2000 sphere)")
    args = p.parse_args()

    status = dem_reader.raster_backend_status()
    if not status["available"]:
        print(status["error"], file=sys.stderr)
        return 2
    if not args.file.is_file():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 1

    report = validate_dem(args.file, units_override=args.units)
    info = report.info.to_dict()
    info.pop("crs_wkt", None)
    print(json.dumps(info, indent=2, default=str))
    print(f"\nlatitude convention (from CRS geometry): {report.latitude_convention}")
    print(f"longitude convention (from bounds):      {report.longitude_convention}")
    print(f"derived resolution:                      {report.resolution_meters} m")
    for w in report.warnings:
        print(f"WARNING: {w}")
    for e in report.errors:
        print(f"ERROR:   {e}")
    print("\nRESULT:", "VALID for import" if report.ok else "INVALID")

    if args.sample:
        crs, _ = resolve_crs(args.crs)
        try:
            s = dem_reader.sample_point(args.file, args.sample[0], args.sample[1], crs)
            print(f"\nSample at {args.sample}: value={s.value} units={s.units} nodata={s.is_nodata} row={s.row} col={s.col}")
        except dem_reader.PointOutsideRaster as exc:
            print(f"\nSample: {exc}")
    return 0 if report.ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
