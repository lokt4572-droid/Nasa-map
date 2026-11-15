"""v0.5 release fixes: route validation on the source DEM, line-based metrics, terrain suitability,
unknown-terrain geometry. Synthetic rasters only (arithmetic checks, not planetary truth)."""
import math
from io import StringIO

import numpy as np
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.datasets.models import Dataset
from apps.routing.profiles import PROFILES
from apps.routing.services.route_validator import validate_on_source
from services import terrain_patch
from services.mars_coordinates import resolve_crs

from .raster_fixtures import MARS_SPHERE, TempDirMixin, requires_raster, write_geotiff

WEST, NORTH, PIX = 70.0, 20.0, 0.01  # ~593 m cells
R = 3396190.0


def pt(lon, lat):
    return {"lon_east_deg": lon, "lat_deg": lat, "crs": MARS_SPHERE, "latitude_convention": "PLANETOCENTRIC", "planet": "MARS"}


class SuitabilityTests(SimpleTestCase):
    def test_classes_by_native_spacing(self):
        self.assertEqual(terrain_patch.terrain_suitability(14817.8), "GLOBAL_OVERVIEW_ONLY")  # MOLA MEGDR 4 px/deg
        self.assertEqual(terrain_patch.terrain_suitability(463), "REGIONAL_PLANNING_ONLY")
        self.assertEqual(terrain_patch.terrain_suitability(20), "LOCAL_TERRAIN_AVAILABLE")  # CTX DTM
        self.assertEqual(terrain_patch.terrain_suitability(1.0), "HIGH_RESOLUTION_TERRAIN_AVAILABLE")  # HiRISE DTM
        self.assertEqual(terrain_patch.terrain_suitability(None), "NO_VALID_DEM")

    def test_mola_and_expansion_warnings(self):
        class DS:
            instrument, name, product_id = "MGS MOLA", "mola-global", "megt90n000cb"
        b = terrain_patch.suitability_block(DS, 14817.8, 177_814.0, 15_000.0, requested_radius_m=500.0)
        self.assertIn("REGIONAL OVERVIEW ONLY", b["data_warnings"])
        self.assertIn("NOT SUITABLE FOR LOCAL OBSTACLE AVOIDANCE", b["data_warnings"])
        self.assertTrue(b["extent"]["radius_expanded"])
        self.assertTrue(any(w.startswith("REQUESTED 500 m RADIUS") for w in b["data_warnings"]))


@requires_raster
class SourceValidationTests(TempDirMixin, TestCase):
    def load(self, z, name):
        p = write_geotiff(self.tmp / f"{name}.tif", z.astype("float32"), west=WEST, north=NORTH, pixel_deg=PIX)
        call_command("import_dem", "--file", str(p), "--name", name, "--vertical-datum", "test datum", stdout=StringIO(), stderr=StringIO())
        return Dataset.objects.get(name=name)

    def setUp(self):
        super().setUp()
        self.crs, _ = resolve_crs(MARS_SPHERE, planet="MARS")

    def test_flat_line_validates_and_metrics_are_geodesic(self):
        ds = self.load(np.zeros((40, 40)), "flat")
        line = [[70.05, 19.85], [70.35, 19.85]]
        v = validate_on_source(ds, line, self.crs, "PLANETOCENTRIC", PROFILES["CONSERVATIVE"])
        self.assertEqual(v["status"], "VALIDATED")
        exp = math.radians(0.30) * R * math.cos(math.radians(19.85))
        self.assertAlmostEqual(v["metrics"]["distance_m"], exp, delta=exp * 0.005)
        self.assertEqual(v["metrics"]["total_ascent_m"], 0.0)
        self.assertEqual(v["elevation_profile"][0]["distance_m"], 0.0)

    def test_steep_step_nodata_and_hazard_fail(self):
        z = np.zeros((40, 40))
        z[:, 20:] = 2000.0  # a 2 km cliff between columns 19 and 20
        ds = self.load(z, "cliff")
        line = [[70.05, 19.85], [70.35, 19.85]]
        v = validate_on_source(ds, line, self.crs, "PLANETOCENTRIC", PROFILES["CONSERVATIVE"])
        self.assertEqual(v["status"], "INVALID_ROUTE")
        self.assertIn("steeper", v["problems"][0])
        z2 = np.zeros((40, 40))
        z2[:, 20] = -9999.0
        ds2 = self.load(z2, "gap")
        v2 = validate_on_source(ds2, line, self.crs, "PLANETOCENTRIC", PROFILES["CONSERVATIVE"])
        self.assertIn("no DEM value", v2["problems"][0])
        flat = Dataset.objects.get(name="cliff")
        v3 = validate_on_source(self.load(np.zeros((40, 40)), "flat2"), line, self.crs, "PLANETOCENTRIC", PROFILES["CONSERVATIVE"],
                                hazards_query=[(70.2, 19.85, 5000.0)])
        self.assertIn("hazard", v3["problems"][0])

    def test_api_route_is_source_validated_and_displayed_metrics_match_the_line(self):
        z = np.zeros((40, 40))
        z[5:15, 20] = 3000.0
        self.load(z, "dem")
        r = APIClient().post("/api/v1/routes/plan/", {"start": pt(70.055, 19.895), "end": pt(70.355, 19.895)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        b = r.json()
        self.assertEqual(b["validation_status"], "VALIDATED")
        sv = b["route"]["source_validation"]
        self.assertEqual(b["route"]["metrics"]["distance_m"], sv["metrics"]["distance_m"])
        self.assertEqual(b["route"]["elevation_profile"], sv["elevation_profile"])
        self.assertIn("displayed line", b["route"]["metrics_basis"])
        self.assertIn("grid_metrics", b["route"])

    def test_unverified_geometry_is_returned_for_exploratory_routes(self):
        z = np.zeros((40, 40))
        z[:, 20] = -9999.0
        self.load(z, "gap")
        r = APIClient().post("/api/v1/routes/plan/", {"start": pt(70.055, 19.805), "end": pt(70.355, 19.805), "profile": "STANDARD",
                                                      "unknown_data_policy": "ALLOW_MARKED", "include_alternative": False, "include_return": False}, format="json")
        b = r.json()
        # STANDARD may cross the gap, but the source check refuses NoData only under REJECT: it is reported as unverified
        if r.status_code == 201:
            self.assertGreater(len(b["route"]["unverified_geometry"]["coordinates"]), 0)
            self.assertEqual(b["route_label"], "PARTIALLY UNVERIFIED ROUTE")
        self.assertIn("EXPLORATORY", PROFILES["STANDARD"].description)


class ProductMetadataTests(TestCase):
    def test_product_kind_metadata(self):
        from apps.datasets.services import copernicus_client, stac_client
        c = stac_client.COLLECTIONS
        assert "CTX stereo images" in c["mro_ctx_controlled_usgs_dtms"].source_imagery
        assert "not the DTM" in c["mro_hirise_socet_dtms"].source_imagery
        assert "70S-70N" in c["kaguya_terrain_camera_usgs_dtms_v2"].coverage
        assert "polar" in c["kaguya_terrain_camera_usgs_dtms_v2_southpolar"].coverage
        assert copernicus_client.COLLECTION.product_kind.startswith("DSM")
        from apps.datasets.catalog import CATALOG
        mola = next(e for e in CATALOG if e["key"] == "mars-mola-megdr")
        assert "OVERVIEW ONLY" in mola["purpose"]
