"""v0.2 terrain metrics + render endpoints on synthetic rasters with analytic answers."""
import math
import struct
import zlib
from io import StringIO

import numpy as np
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.datasets.models import Dataset
from services import raster_render

from .raster_fixtures import MARS_SPHERE, TempDirMixin, requires_raster, write_geotiff

WEST, NORTH, PIX = 77.30, 18.50, 0.01


def centre(row, col):
    return WEST + (col + 0.5) * PIX, NORTH - (row + 0.5) * PIX


def decode_png(data: bytes) -> np.ndarray:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(data):
        (ln,) = struct.unpack(">I", data[pos : pos + 4])
        tag = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + ln]
        if tag == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
        elif tag == b"IDAT":
            idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat)
    rows = [raw[y * (w * 4 + 1) + 1 : (y + 1) * (w * 4 + 1)] for y in range(h)]
    return np.frombuffer(b"".join(rows), np.uint8).reshape(h, w, 4)


class PngEncoderTests(SimpleTestCase):
    def test_roundtrip(self):
        img = np.random.default_rng(1).integers(0, 255, (7, 5, 4), dtype=np.uint8)
        self.assertTrue(np.array_equal(decode_png(raster_render.encode_png_rgba(img)), img))


@requires_raster
class TerrainMetricV02Tests(TempDirMixin, TestCase):
    def setUp(self):
        super().setUp()
        # z rises 1 m per cell eastwards, 10 m per cell southwards; one nodata cell.
        r, c = np.mgrid[0:10, 0:10]
        z = (1000.0 + 10.0 * r + c).astype("float32")
        z[7, 7] = -9999.0
        path = write_geotiff(self.tmp / "dem.tif", z, west=WEST, north=NORTH, pixel_deg=PIX)
        call_command("import_dem", "--file", str(path), "--name", "t", "--vertical-datum", "test datum", stdout=StringIO(), stderr=StringIO())
        self.ds = Dataset.objects.get(name="t")
        self.c = APIClient()

    def get(self, ep, lon, lat, **extra):
        return self.c.get(f"/api/v1/terrain/{ep}/", {"lon": lon, "lat": lat, "crs": MARS_SPHERE, **extra})

    def test_result_schema(self):
        body = self.get("aspect", *centre(2, 2)).json()
        res = body["result"]
        for key in ("value", "units", "dataset_id", "source", "resolution_m", "crs", "nodata_status", "processing_method"):
            self.assertIn(key, res)
        self.assertEqual(res["dataset_id"], self.ds.id)
        self.assertEqual(res["nodata_status"], "OK")

    def test_aspect_direction(self):
        # Elevation grows to the south and east -> steepest descent points roughly north (slightly west).
        v = self.get("aspect", *centre(2, 2)).json()["result"]["value"]
        lat = centre(2, 2)[1]
        dx = math.radians(PIX) * 3396190 * math.cos(math.radians(lat))
        dy = math.radians(PIX) * 3396190
        expected = (math.degrees(math.atan2(-(1 / dx), -(-10 / dy))) + 360) % 360
        self.assertAlmostEqual(v, expected, places=6)
        self.assertTrue(v > 350)

    def test_roughness_tri(self):
        # neighbours differ by -11,-10,-9,-1,+1,+9,+10,+11 -> sqrt(2*(121+100+81+1)) = sqrt(606)
        v = self.get("roughness", *centre(2, 2)).json()["result"]["value"]
        self.assertAlmostEqual(v, math.sqrt(606), places=6)

    def test_local_relief_radius_2(self):
        v = self.get("relief", *centre(3, 3), radius=2).json()["result"]["value"]
        self.assertEqual(v, (1000 + 50 + 5) - (1000 + 10 + 1))

    def test_nodata_partial_and_never_zero(self):
        body = self.get("roughness", *centre(6, 6)).json()
        self.assertIsNone(body["result"]["value"])
        self.assertEqual(body["result"]["nodata_status"], "PARTIAL_NODATA")
        self.assertEqual(body["status"], "NOT_AVAILABLE")
        cov = self.get("nodata", *centre(6, 6), radius=1).json()["result"]["value"]
        self.assertAlmostEqual(cov, 1 / 9)

    def test_elevation_difference(self):
        a, b = centre(1, 1), centre(4, 6)
        r = self.c.get("/api/v1/terrain/difference/", {"lon": a[0], "lat": a[1], "lon2": b[0], "lat2": b[1], "crs": MARS_SPHERE}).json()
        self.assertEqual(r["result"]["value"], (1046.0) - (1011.0))
        self.assertEqual(r["result"]["elevation_a_m"], 1011.0)

    def test_difference_outside(self):
        r = self.c.get("/api/v1/terrain/difference/", {"lon": 0, "lat": 0, "lon2": 1, "lat2": 1, "crs": MARS_SPHERE})
        self.assertEqual(r.status_code, 404)

    def test_area_statistics(self):
        r = self.c.get("/api/v1/terrain/area/", {"dataset": self.ds.id, "bbox": f"{WEST},{NORTH - 0.1},{WEST + 0.1},{NORTH}", "crs": MARS_SPHERE}).json()
        st = r["result"]["statistics"]
        self.assertEqual(st["min"], 1000.0)
        self.assertEqual(st["max"], 1099.0)  # cell (9,9)
        self.assertAlmostEqual(st["nodata_fraction"], 1 / 100)

    def test_radius_validation(self):
        self.assertEqual(self.get("relief", *centre(3, 3), radius=99).status_code, 400)

    def test_render_png(self):
        r = self.c.get("/api/v1/terrain/render/", {
            "dataset": self.ds.id, "product": "elevation", "bbox": f"{WEST},{NORTH - 0.1},{WEST + 0.1},{NORTH}",
            "width": 10, "height": 10, "crs": MARS_SPHERE,
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertEqual(r["X-Value-Min"], "1000.0000")
        img = decode_png(r.content)
        self.assertEqual(img.shape, (10, 10, 4))
        self.assertEqual(img[7, 7, 3], 0)  # nodata transparent
        self.assertEqual(img[0, 0, 3], 255)

    def test_render_all_products_and_validation(self):
        for p in raster_render.PRODUCTS:
            r = self.c.get("/api/v1/terrain/render/", {"dataset": self.ds.id, "product": p, "bbox": f"{WEST},{NORTH - 0.1},{WEST + 0.1},{NORTH}", "width": 20, "height": 20, "crs": MARS_SPHERE})
            self.assertEqual(r.status_code, 200, p)
        bad = self.c.get("/api/v1/terrain/render/", {"dataset": self.ds.id, "product": "rgb", "bbox": "0,0,1,1", "width": 2, "height": 2, "crs": MARS_SPHERE})
        self.assertEqual(bad.status_code, 400)
        huge = self.c.get("/api/v1/terrain/render/", {"dataset": self.ds.id, "bbox": "0,0,1,1", "width": 5000, "height": 2, "crs": MARS_SPHERE})
        self.assertEqual(huge.status_code, 400)
