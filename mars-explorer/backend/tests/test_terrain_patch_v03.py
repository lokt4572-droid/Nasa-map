"""v0.3 local terrain patch endpoint + DEM seam wrap, on synthetic rasters (fixtures only)."""
import math
from io import StringIO

import numpy as np
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.datasets.models import Dataset
from services import terrain_patch

from .raster_fixtures import TempDirMixin, requires_raster, write_geotiff

WEST, NORTH, PIX = 77.0, 19.0, 0.01  # 100 x 100 cells, ~593 m on Mars


def get_patch(c, **q):
    return c.get("/api/v1/terrain/patch/", {"planet": "MARS", **q})


@requires_raster
class TerrainPatchTests(TempDirMixin, TestCase):
    def setUp(self):
        super().setUp()
        r, cc = np.mgrid[0:100, 0:100]
        self.z = (1000.0 + 10.0 * r + cc).astype("float32")
        self.z[50, 50] = -9999.0  # one NoData cell at the centre
        path = write_geotiff(self.tmp / "dem.tif", self.z, west=WEST, north=NORTH, pixel_deg=PIX)
        call_command("import_dem", "--file", str(path), "--name", "patch-fixture", "--vertical-datum", "test datum", stdout=StringIO(), stderr=StringIO())
        self.ds = Dataset.objects.get(name="patch-fixture")
        self.c = APIClient()

    def test_patch_values_come_only_from_the_dem(self):
        r = get_patch(self.c, longitude=77.5, latitude=18.5, radius_m=10_000, max_dimension=16)
        self.assertEqual(r.status_code, 200, r.content)
        b = r.json()
        g = b["grid"]
        self.assertEqual((g["width"], g["height"]), (16, 16))
        z = terrain_patch.decode_elevation(b["elevation"], 16, 16)
        valid = z[np.isfinite(z)]
        dem_values = set(self.z[self.z != -9999.0].tolist())
        self.assertTrue(set(valid.tolist()) <= dem_values)  # nothing interpolated or invented
        # north row has smaller row index -> lower values; east column higher values
        self.assertLess(np.nanmean(z[0]), np.nanmean(z[-1]))
        self.assertLess(np.nanmean(z[:, 0]), np.nanmean(z[:, -1]))
        self.assertEqual(b["dataset"]["id"], self.ds.id)
        for k in ("native_resolution_m", "vertical_datum", "units", "latitude_convention", "instrument", "source"):
            self.assertIn(k, b["dataset"])
        self.assertAlmostEqual(b["statistics"]["min"], float(valid.min()))
        self.assertIn("NaN = NoData", b["encoding"])

    def test_grid_is_never_finer_than_the_dem(self):
        b = get_patch(self.c, lon=77.5, lat=18.5, radius_m=3000, max_dimension=512).json()
        cells = int(math.floor(2 * 3000 / self.ds.resolution_meters))
        self.assertEqual(b["grid"]["width"], cells)  # capped by native cells, not 512
        self.assertGreaterEqual(b["grid"]["cell_size_y_m"], self.ds.resolution_meters * 0.95)

    def test_nodata_is_reported_not_filled(self):
        b = get_patch(self.c, lon=WEST + 50.5 * PIX, lat=NORTH - 50.5 * PIX, radius_m=1500, max_dimension=64).json()
        self.assertGreater(b["statistics"]["nodata_fraction"], 0)
        z = terrain_patch.decode_elevation(b["elevation"], b["grid"]["width"], b["grid"]["height"])
        self.assertTrue(np.isnan(z).any())

    def test_patch_partly_outside_the_dem_has_nodata_edges(self):
        b = get_patch(self.c, lon=WEST + 0.02, lat=18.5, radius_m=10_000, max_dimension=32).json()
        self.assertGreater(b["statistics"]["nodata_fraction"], 0.2)

    def test_too_coarse_says_minimum_radius(self):
        r = get_patch(self.c, lon=77.5, lat=18.5, radius_m=500)
        self.assertEqual(r.status_code, 422)
        e = r.json()["error"]
        self.assertEqual(e["code"], "DEM_TOO_COARSE_FOR_PATCH")
        self.assertEqual(e["details"]["min_radius_m"], math.ceil(terrain_patch.MIN_NATIVE_CELLS * self.ds.resolution_meters / 2))

    def test_no_dem_is_404_not_fake_terrain(self):
        r = get_patch(self.c, lon=-120, lat=-30, radius_m=10_000)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"]["code"], "DEM_NOT_AVAILABLE")
        self.assertEqual(self.c.get("/api/v1/terrain/patch/", {"planet": "MOON", "lon": 0, "lat": 0}).status_code, 404)

    def test_validation(self):
        for q in ({"lon": 77.5, "lat": 18.5, "radius_m": 50}, {"lon": 77.5, "lat": 18.5, "radius_m": 1e7},
                  {"lon": 77.5, "lat": 18.5, "max_dimension": 4}, {"lon": 77.5, "lat": 95}, {"lat": 18.5},
                  {"lon": 77.5, "lat": 18.5, "radius_m": "abc"}):
            self.assertEqual(get_patch(self.c, **q).status_code, 400, q)


@requires_raster
class SeamWrapTests(TempDirMixin, TestCase):
    """A projected equirectangular DEM centred on 180 E that spans the whole circumference (like
    MOLA MEGDR): lon 0 lies exactly on its seam and must still be inside the DEM."""

    def setUp(self):
        super().setUp()
        R = 3_396_000.0
        width = 2 * math.pi * R
        pix = width / 360  # ~59 km cells
        z = np.tile(np.arange(360, dtype="float32"), (180, 1))  # value = column index
        path = write_geotiff(
            self.tmp / "megdr_like.tif", z, west=-width / 2, north=pix * 90, pixel_deg=pix,
            crs="+proj=eqc +lon_0=180 +R=3396000 +units=m +no_defs",
        )
        call_command("import_dem", "--file", str(path), "--name", "seam", "--vertical-datum", "test datum", "--planet", "MARS",
                     stdout=StringIO(), stderr=StringIO())
        self.ds = Dataset.objects.get(name="seam")
        self.c = APIClient()

    def test_lon_zero_on_the_seam_is_covered(self):
        r = self.c.get("/api/v1/terrain/sample/", {"planet": "MARS", "lon": 0, "lat": 0, "crs": "ESRI:104971"})
        self.assertEqual(r.status_code, 200, r.content)

    def test_patch_across_the_seam_has_no_gap(self):
        r = get_patch(self.c, lon=0, lat=0, radius_m=300_000, max_dimension=64, crs="ESRI:104971")
        self.assertEqual(r.status_code, 200, r.content)
        b = r.json()
        self.assertEqual(b["statistics"]["nodata_fraction"], 0.0)
        z = terrain_patch.decode_elevation(b["elevation"], b["grid"]["width"], b["grid"]["height"])
        vals = set(np.unique(z).tolist())
        self.assertIn(0.0, vals)  # east of the seam (first column)
        self.assertIn(359.0, vals)  # west of the seam (last column)


class PatchHelperTests(SimpleTestCase):
    def test_bbox_and_dimensions(self):
        w, s, e, n = terrain_patch.patch_bbox(0, 60, 10_000, 3_396_190)
        self.assertAlmostEqual(n - s, 2 * math.degrees(10_000 / 3_396_190))
        self.assertAlmostEqual((e - w) * math.cos(math.radians(60)), n - s, places=9)
        self.assertEqual(terrain_patch.grid_dimensions(30_000, 14_818, 256), (4, 4))
        self.assertEqual(terrain_patch.grid_dimensions(1e6, 100, 256), (20_000, 256))

    def test_pole_is_refused(self):
        with self.assertRaises(terrain_patch.PatchError) as ctx:
            terrain_patch.patch_bbox(0, 89.5, 100_000, 3_396_190)
        self.assertEqual(ctx.exception.code, "PATCH_CROSSES_POLE")
