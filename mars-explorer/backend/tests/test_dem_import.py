import math
from io import StringIO

import numpy as np
from django.core.management import CommandError, call_command
from django.test import TestCase
from rest_framework.test import APIClient

from apps.datasets.models import Dataset

from .raster_fixtures import EARTH_WGS84, MARS_SPHERE, TempDirMixin, requires_raster, write_geotiff

# Fixture grid: 10 x 10 cells of 0.01 deg, north-west corner at (77.30 E, 18.50 N).
WEST, NORTH, PIX = 77.30, 18.50, 0.01


def ramp_dem() -> np.ndarray:
    # z = 1000 + 10*row + col  (metres) -> each cell has a unique, predictable value
    rows, cols = np.mgrid[0:10, 0:10]
    return (1000.0 + 10.0 * rows + cols).astype("float32")


def cell_center(row: int, col: int) -> tuple[float, float]:
    return WEST + (col + 0.5) * PIX, NORTH - (row + 0.5) * PIX


def import_dem(path, name="test-dem", **kw):
    out, err = StringIO(), StringIO()
    call_command("import_dem", "--file", str(path), "--name", name, stdout=out, stderr=err, **kw)
    return out.getvalue(), err.getvalue()


@requires_raster
class ImportDemCommandTests(TempDirMixin, TestCase):
    def test_valid_geotiff_registers(self):
        path = write_geotiff(self.tmp / "dem.tif", ramp_dem(), west=WEST, north=NORTH, pixel_deg=PIX)
        out, _ = import_dem(path, vertical_datum="test datum")
        self.assertIn("Registered dataset", out)
        ds = Dataset.objects.get(name="test-dem")
        self.assertEqual(ds.status, Dataset.Status.VALID)
        self.assertTrue(ds.is_validated)
        self.assertEqual((ds.width, ds.height), (10, 10))
        self.assertEqual(ds.units, "m")
        self.assertEqual(ds.nodata_value, -9999.0)
        self.assertEqual(ds.latitude_convention, "PLANETOCENTRIC")
        self.assertEqual(ds.longitude_convention, "EAST_POSITIVE_180")
        self.assertTrue(ds.checksum.startswith("sha256:"))
        # 0.01 deg on a 3396190 m sphere
        self.assertAlmostEqual(ds.resolution_meters, math.radians(0.01) * 3396190.0, places=3)
        self.assertAlmostEqual(ds.coverage_bbox["left"], WEST)
        self.assertAlmostEqual(ds.coverage_bbox["top"], NORTH)

    def test_source_file_is_not_modified(self):
        path = write_geotiff(self.tmp / "dem.tif", ramp_dem(), west=WEST, north=NORTH, pixel_deg=PIX)
        before = path.read_bytes()
        import_dem(path)
        self.assertEqual(path.read_bytes(), before)

    def test_missing_file(self):
        with self.assertRaisesMessage(CommandError, "File not found"):
            import_dem(self.tmp / "nope.tif")
        self.assertFalse(Dataset.objects.exists())

    def test_no_crs_is_rejected_not_guessed(self):
        path = write_geotiff(self.tmp / "nocrs.tif", ramp_dem(), west=WEST, north=NORTH, pixel_deg=PIX, crs=None)
        with self.assertRaisesMessage(CommandError, "No CRS found"):
            import_dem(path)
        self.assertFalse(Dataset.objects.exists())

    def test_earth_crs_rejected(self):
        path = write_geotiff(self.tmp / "earth.tif", ramp_dem(), west=WEST, north=NORTH, pixel_deg=PIX, crs=EARTH_WGS84)
        with self.assertRaisesMessage(CommandError, "does not describe Mars"):
            import_dem(path)

    def test_missing_units_requires_explicit_flag(self):
        path = write_geotiff(self.tmp / "nounits.tif", ramp_dem(), west=WEST, north=NORTH, pixel_deg=PIX, units=None)
        with self.assertRaisesMessage(CommandError, "units are not stated"):
            import_dem(path)
        out, _ = import_dem(path, units="m")
        self.assertIn("Registered", out)

    def test_rgb_image_rejected(self):
        rgb = np.zeros((3, 10, 10), dtype="uint8")
        path = write_geotiff(self.tmp / "rgb.tif", rgb, west=WEST, north=NORTH, pixel_deg=PIX, nodata=None)
        with self.assertRaisesMessage(CommandError, "RGB"):
            import_dem(path, units="m")

    def test_missing_nodata_is_a_warning(self):
        path = write_geotiff(self.tmp / "nond.tif", ramp_dem(), west=WEST, north=NORTH, pixel_deg=PIX, nodata=None)
        _, err = import_dem(path)
        self.assertIn("No nodata value", err)

    def test_contradicting_latitude_convention(self):
        path = write_geotiff(self.tmp / "dem.tif", ramp_dem(), west=WEST, north=NORTH, pixel_deg=PIX)
        with self.assertRaisesMessage(CommandError, "contradicts"):
            import_dem(path, latitude_convention="PLANETOGRAPHIC")

    def test_dry_run_registers_nothing(self):
        path = write_geotiff(self.tmp / "dem.tif", ramp_dem(), west=WEST, north=NORTH, pixel_deg=PIX)
        out, _ = import_dem(path, dry_run=True)
        self.assertIn("Dry run", out)
        self.assertFalse(Dataset.objects.exists())


@requires_raster
class TerrainWithDemTests(TempDirMixin, TestCase):
    def setUp(self):
        super().setUp()
        dem = ramp_dem()
        dem[5, 5] = -9999.0  # nodata cell
        self.path = write_geotiff(self.tmp / "dem.tif", dem, west=WEST, north=NORTH, pixel_deg=PIX)
        import_dem(self.path, vertical_datum="test datum")
        self.client = APIClient()

    def get(self, url, lon, lat, crs=MARS_SPHERE):
        return self.client.get(url, {"lon": lon, "lat": lat, "crs": crs})

    def test_elevation_at_known_cell(self):
        lon, lat = cell_center(3, 7)
        r = self.get("/api/v1/terrain/sample/", lon, lat)
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["status"], "AVAILABLE")
        self.assertEqual(body["elevation_m"], 1000.0 + 30.0 + 7.0)
        self.assertEqual((body["pixel"]["row"], body["pixel"]["col"]), (3, 7))
        self.assertEqual(body["dataset"]["name"], "test-dem")

    def test_longitude_out_of_accepted_range_rejected(self):
        # Accepted input range is -180..360 east; 437 deg is not silently wrapped.
        lon, lat = cell_center(2, 2)
        r = self.get("/api/v1/terrain/sample/", lon + 360.0, lat)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "VALIDATION_ERROR")

    def test_nodata_cell(self):
        lon, lat = cell_center(5, 5)
        body = self.get("/api/v1/terrain/sample/", lon, lat).json()
        self.assertEqual(body["status"], "NODATA")
        self.assertIsNone(body["elevation_m"])
        self.assertEqual(body["elevation_display"], "DATA NOT AVAILABLE")

    def test_outside_coverage(self):
        r = self.get("/api/v1/terrain/sample/", 10.0, 10.0)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"]["code"], "DEM_NOT_AVAILABLE")

    def test_trek_crs_unverified_latitude_is_flagged(self):
        lon, lat = cell_center(3, 7)
        body = self.get("/api/v1/terrain/sample/", lon, lat, crs="urn:ogc:def:crs:EPSG::104905").json()
        self.assertEqual(body["query"]["crs_resolution"]["resolved_as"], "ESRI:104905")
        self.assertEqual(body["latitude_handling"]["status"], "NOT_VERIFIED")
        self.assertIsNotNone(body["latitude_handling"]["warning"])
        self.assertEqual(body["elevation_m"], 1037.0)

    def test_planetographic_query_is_converted_to_dem_planetocentric(self):
        # Coarse fixture: 10x10 cells of 0.1 deg, NW corner (77.0 E, 19.0 N).
        rows, cols = np.mgrid[0:10, 0:10]
        write_geotiff(self.tmp / "coarse.tif", (500.0 + 10 * rows + cols).astype("float32"), west=77.0, north=19.0, pixel_deg=0.1)
        import_dem(self.tmp / "coarse.tif", name="coarse")
        lat_g = 18.85
        lat_c = math.degrees(math.atan((3376200.0 / 3396190.0) ** 2 * math.tan(math.radians(lat_g))))
        expected_row = int((19.0 - lat_c) / 0.1)  # 3; without conversion it would be row 1
        r = self.client.get(
            "/api/v1/terrain/sample/",
            {"lon": 77.85, "lat": lat_g, "crs": "urn:ogc:def:crs:EPSG::104905", "lat_convention": "PLANETOGRAPHIC"},
        ).json()
        self.assertEqual(r["latitude_handling"]["status"], "CONVERTED_PLANETOGRAPHIC_TO_PLANETOCENTRIC")
        self.assertAlmostEqual(r["latitude_handling"]["lat_used_deg"], lat_c, places=9)
        self.assertEqual(r["pixel"]["row"], expected_row)
        self.assertEqual(expected_row, 3)
        self.assertEqual(r["elevation_m"], 500.0 + 10 * 3 + 8)

    def test_slope_matches_analytic_value(self):
        # z = 1000 + 10*row + col: +1 m per cell eastwards, -10 m per cell northwards.
        lon, lat_c = cell_center(2, 2)
        body = self.get("/api/v1/terrain/slope/", lon, lat_c).json()
        self.assertEqual(body["status"], "AVAILABLE", body)
        R = 3396190.0
        dx = math.radians(PIX) * R * math.cos(math.radians(lat_c))
        dy = math.radians(PIX) * R
        expected = math.degrees(math.atan(math.hypot(1.0 / dx, 10.0 / dy)))
        self.assertAlmostEqual(body["slope_deg"], expected, places=6)
        self.assertAlmostEqual(body["cell_size_m"]["dx"], dx, places=3)
        # Elevation grows southwards (and slightly eastwards): downslope is roughly north.
        self.assertTrue(body["aspect_deg"] > 270 or body["aspect_deg"] < 10)

    def test_slope_next_to_nodata(self):
        lon, lat = cell_center(4, 4)
        body = self.get("/api/v1/terrain/slope/", lon, lat).json()
        self.assertEqual(body["status"], "NODATA")
        self.assertIsNone(body["slope_deg"])
        self.assertAlmostEqual(body["nodata_fraction"], 1 / 9)

    def test_coverage_lists_dataset(self):
        lon, lat = cell_center(1, 1)
        body = self.get("/api/v1/terrain/coverage/", lon, lat).json()
        self.assertEqual(body["terrain_analysis_status"], "AVAILABLE")
        self.assertEqual([d["name"] for d in body["datasets"]], ["test-dem"])

    def test_missing_file_marks_dataset_missing(self):
        self.path.unlink()
        lon, lat = cell_center(1, 1)
        r = self.get("/api/v1/terrain/sample/", lon, lat)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(Dataset.objects.get(name="test-dem").status, Dataset.Status.MISSING)

    def test_dataset_endpoints(self):
        ds = Dataset.objects.get(name="test-dem")
        r = self.client.get("/api/v1/datasets/")
        self.assertEqual(r.json()["results"][0]["name"], "test-dem")
        self.assertTrue(r.json()["results"][0]["file_exists"])
        r = self.client.get(f"/api/v1/datasets/{ds.id}/metadata/")
        self.assertEqual(r.json()["metadata"]["driver"], "GTiff")
        self.assertIn("Mars_2000_(Sphere)", r.json()["crs"])
        self.assertIn("3396190", r.json()["crs"])
