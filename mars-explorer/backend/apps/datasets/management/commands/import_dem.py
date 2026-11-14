"""Validate a local DEM file and register it in the database.

    python manage.py import_dem --file "PATH_TO_DEM" --name "dataset-name"

The source file is opened read-only and never modified or moved.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from services import dataset_manager
from services.dem_reader import RasterBackendUnavailable, RasterReadError
from services.mars_coordinates import LatitudeConvention


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(f"Invalid date {value!r}, expected YYYY-MM-DD") from exc


class Command(BaseCommand):
    help = "Validate and register a DEM raster (GeoTIFF, PDS3 .IMG/.LBL, PDS4 .xml label, ISIS3 .cub)."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to the raster or its PDS label")
        parser.add_argument("--name", required=True, help="Unique dataset name (slug)")
        parser.add_argument("--source", default="", help="e.g. 'NASA PDS Geosciences Node'")
        parser.add_argument("--instrument", default="", help="e.g. 'MGS MOLA' or 'MRO HiRISE'")
        parser.add_argument("--product-id", default="")
        parser.add_argument("--data-type", default="DEM", choices=["DEM", "SLOPE", "ROUGHNESS", "OTHER"])
        parser.add_argument("--vertical-datum", default=None, help="As stated in the product label, e.g. 'MOLA areoid'")
        parser.add_argument("--units", default=None, help="Elevation units, only if the file does not state them")
        parser.add_argument(
            "--latitude-convention",
            default=None,
            choices=[LatitudeConvention.PLANETOCENTRIC.value, LatitudeConvention.PLANETOGRAPHIC.value],
            help="Only to confirm what the product label states; must agree with the CRS",
        )
        parser.add_argument("--observation-date", type=_date, default=None)
        parser.add_argument("--download-date", type=_date, default=None)
        parser.add_argument("--no-checksum", action="store_true", help="Skip sha256 (faster for huge files)")
        parser.add_argument("--dry-run", action="store_true", help="Validate only, do not register")

    def handle(self, *args, **opts):
        path = Path(opts["file"]).expanduser()
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        if not path.is_file():
            raise CommandError(f"Not a file: {path}")
        name = slugify(opts["name"])
        if not name:
            raise CommandError("--name must contain letters or digits")

        self.stdout.write(f"Inspecting {path} ...")
        try:
            dataset, report, warnings = dataset_manager.register_dataset(
                path=path,
                name=name,
                source=opts["source"],
                instrument=opts["instrument"],
                product_id=opts["product_id"],
                data_type=opts["data_type"],
                vertical_datum=opts["vertical_datum"],
                units=opts["units"],
                latitude_convention=opts["latitude_convention"],
                observation_date=opts["observation_date"],
                download_date=opts["download_date"],
                compute_checksum=not opts["no_checksum"],
                dry_run=opts["dry_run"],
            )
        except RasterBackendUnavailable as exc:
            raise CommandError(str(exc)) from exc
        except RasterReadError as exc:
            raise CommandError(f"Unreadable raster: {exc}") from exc
        except dataset_manager.DatasetValidationError as exc:
            for w in exc.warnings:
                self.stderr.write(self.style.WARNING(f"WARNING: {w}"))
            lines = "\n".join(f"  - {e}" for e in exc.errors)
            raise CommandError(f"Dataset is INVALID, nothing registered:\n{lines}") from exc

        info = report.info
        summary = {
            "driver": info.driver,
            "size": f"{info.width} x {info.height} x {info.band_count} band(s)",
            "dtype": info.dtype,
            "crs": info.crs_name,
            "bounds": info.bounds,
            "pixel_size": [info.pixel_size_x, info.pixel_size_y],
            "resolution_meters (derived)": report.resolution_meters,
            "units": report.units,
            "nodata": info.nodata,
            "latitude_convention": str(report.latitude_convention),
            "longitude_convention": str(report.longitude_convention),
        }
        self.stdout.write(json.dumps(summary, indent=2, default=str))
        for w in warnings:
            self.stderr.write(self.style.WARNING(f"WARNING: {w}"))
        if opts["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run: file is valid, nothing registered."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Registered dataset '{dataset.name}' (id={dataset.id}) status={dataset.status}"))
