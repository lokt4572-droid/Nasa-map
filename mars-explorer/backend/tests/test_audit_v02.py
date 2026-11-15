"""v0.2 audit: DEM resolution suitability, routing input-data quality, unknown terrain,
product-file integrity, and the real MOLA dataset."""
import math
from io import StringIO
from pathlib import Path

import numpy as np
from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.datasets.models import Dataset
from apps.routing.profiles import ASTRONAUT_SCALE_MAX_CELL_M, assess_resolution

from .raster_fixtures import TempDirMixin, requires_raster, write_geotiff

REAL_MOLA = Path(settings.MARS_DATA_DIR) / "raw" / "mola" / "megt90n000cb.xml"


def pt(lon, lat):
    return {"lon_east_deg": lon, "lat_deg": lat, "crs": "ESRI:104971", "latitude_convention": "PLANETOCENTRIC"}


class ResolutionAssessmentTests(SimpleTestCase):
    def test_global_mola_is_regional_only_and_never_safe(self):
        a = assess_resolution(14817.845, 14817.845)
        self.assertEqual(a["class"], "REGIONAL_PLANNING_ONLY")
        self.assertEqual(a["astronaut_scale_route_safety"], "NOT_SUITABLE")
        self.assertFalse(a["suitable_for_astronaut_scale_route_safety"])
        self.assertAlmostEqual(a["smallest_resolvable_feature_m"], 29635.7, places=1)

    def test_classes_and_coarsest_cell_wins(self):
        self.assertEqual(assess_resolution(20.0, 20.0)["class"], "SITE_RECONNAISSANCE")
        self.assertEqual(assess_resolution(1.0, 1.0)["class"], "DETAILED_TRAVERSE_STUDY")
        # a fine DEM decimated to a coarse grid is judged by the grid
        self.assertEqual(assess_resolution(500.0, 1.0)["class"], "REGIONAL_PLANNING_ONLY")

    def test_no_resolution_is_ever_declared_safe(self):
        for cell in (0.1, 0.5, ASTRONAUT_SCALE_MAX_CELL_M, 2.0, 50.0, 463.0, 14817.8):
            a = assess_resolution(cell, cell)
            self.assertFalse(a["suitable_for_astronaut_scale_route_safety"], cell)
            self.assertIn(a["astronaut_scale_route_safety"], ("NOT_SUITABLE", "NOT_ASSESSED_NO_VALIDATED_MODEL"))
        self.assertEqual(assess_resolution(0.5, 0.5)["astronaut_scale_route_safety"], "NOT_ASSESSED_NO_VALIDATED_MODEL")


@requires_raster
class RoutingDataQualityTests(TempDirMixin, TestCase):
    def load(self, z, pix, name):
        p = write_geotiff(self.tmp / f"{name}.tif", z.astype("float32"), west=70.0, north=20.0, pixel_deg=pix)
        call_command("import_dem", "--file", str(p), "--name", name, "--vertical-datum", "test datum", stdout=StringIO(), stderr=StringIO())

    def plan(self, a, b, profile="CONSERVATIVE"):
        return APIClient().post("/api/v1/routes/plan/", {"start": a, "end": b, "profile": profile, "include_alternative": False}, format="json")

    def test_coarse_grid_reports_regional_only(self):
        self.load(np.zeros((20, 20)), 0.25, "coarse")  # 0.25 deg ~ MOLA meg004
        r = self.plan(pt(70.6, 19.4), pt(73.4, 16.6))
        self.assertEqual(r.status_code, 201, r.content)
        q = r.json()["data_quality"]
        self.assertEqual(q["resolution_assessment"]["class"], "REGIONAL_PLANNING_ONLY")
        self.assertEqual(q["resolution_assessment"]["astronaut_scale_route_safety"], "NOT_SUITABLE")
        self.assertEqual(q["latitude_handling"], "NONE")
        self.assertEqual(q["dem"]["vertical_datum"], "test datum")
        self.assertGreater(q["grid_cell_size_m"]["dy_mean"], 14000)

    def test_metre_scale_grid_is_detailed_but_still_not_safe(self):
        self.load(np.zeros((40, 40)), 0.00001, "fine")  # ~0.59 m cells
        r = self.plan(pt(70.00005, 19.99995), pt(70.00035, 19.99965), "STANDARD")
        self.assertEqual(r.status_code, 201, r.content)
        a = r.json()["data_quality"]["resolution_assessment"]
        self.assertEqual(a["class"], "DETAILED_TRAVERSE_STUDY")
        self.assertEqual(a["astronaut_scale_route_safety"], "NOT_ASSESSED_NO_VALIDATED_MODEL")
        self.assertFalse(a["suitable_for_astronaut_scale_route_safety"])

    def test_unknown_terrain_rejected_with_quality_report(self):
        z = np.zeros((30, 30))
        z[:, 15] = -9999.0  # band without DEM data
        self.load(z, 0.01, "gap")
        r = self.plan(pt(70.055, 19.895), pt(70.255, 19.895), "CONSERVATIVE")
        self.assertEqual(r.status_code, 422)
        body = r.json()
        self.assertEqual((body["status"], body["route"]), ("INSUFFICIENT_TERRAIN_DATA", None))
        q = body["details"]["data_quality"]
        self.assertGreater(q["window_nodata_fraction"], 0.0)
        self.assertEqual(q["resolution_assessment"]["astronaut_scale_route_safety"], "NOT_SUITABLE")

    def test_start_on_unknown_cell_rejected(self):
        z = np.zeros((30, 30))
        z[10, 5] = -9999.0
        self.load(z, 0.01, "hole")
        r = self.plan(pt(70.055, 19.895), pt(70.255, 19.895), "CONSERVATIVE")
        self.assertEqual(r.json()["status"], "INSUFFICIENT_TERRAIN_DATA")
        self.assertIn("no DEM elevation", r.json()["reason"])


@requires_raster
class ProductIntegrityTests(TempDirMixin, TestCase):
    def test_checksum_and_size_cover_all_product_files(self):
        p = write_geotiff(self.tmp / "d.tif", np.zeros((5, 5), "float32"), west=0, north=5, pixel_deg=1)
        call_command("import_dem", "--file", str(p), "--name", "d", "--vertical-datum", "x", stdout=StringIO(), stderr=StringIO())
        ds = Dataset.objects.get(name="d")
        files = ds.metadata["product_files"]
        self.assertEqual(ds.file_size, sum(f["bytes"] for f in files))
        self.assertTrue(all(f["sha256"].startswith("sha256:") for f in files))


@requires_raster
class RealMolaAuditTests(TestCase):
    def setUp(self):
        if not REAL_MOLA.is_file():
            self.skipTest("real MOLA MEGDR not downloaded")
        call_command("import_dem", "--file", str(REAL_MOLA), "--name", "mola-global", stdout=StringIO(), stderr=StringIO())

    def test_metadata_resolution_and_integrity(self):
        ds = Dataset.objects.get(name="mola-global")
        self.assertAlmostEqual(ds.resolution_meters, 14817.845349, places=3)  # 0.25 deg on R = 3 396 000 m
        self.assertAlmostEqual(ds.resolution_meters, math.radians(0.25) * 3_396_000, places=3)
        names = sorted(Path(f["path"]).name for f in ds.metadata["product_files"])
        self.assertEqual(names, ["megt90n000cb.img", "megt90n000cb.xml"])
        self.assertEqual(ds.file_size, 2_073_600 + 15_509)

    def test_real_route_is_regional_only(self):
        r = APIClient().post("/api/v1/routes/plan/", {"start": pt(70, 15), "end": pt(85, 22), "profile": "CONSERVATIVE", "include_alternative": False}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        a = r.json()["data_quality"]["resolution_assessment"]
        self.assertEqual(a["class"], "REGIONAL_PLANNING_ONLY")
        self.assertEqual(a["astronaut_scale_route_safety"], "NOT_SUITABLE")
        self.assertGreaterEqual(a["effective_cell_m"], 14817.8)
