"""Shared elevation stretch for terrain renders (synthetic raster; checks the colour arithmetic)."""
import struct
import zlib
from io import StringIO

import numpy as np
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from apps.datasets.models import Dataset

from .raster_fixtures import TempDirMixin, requires_raster, write_geotiff


def first_pixel(png: bytes) -> tuple[int, int, int, int]:
    data = b""
    i = 8
    while i < len(png):
        (n,) = struct.unpack(">I", png[i : i + 4])
        tag = png[i + 4 : i + 8]
        if tag == b"IDAT":
            data += png[i + 8 : i + 8 + n]
        i += 12 + n
    raw = zlib.decompress(data)
    return tuple(raw[1:5])  # filter byte, then RGBA of pixel (0, 0)


@requires_raster
class RenderRangeTests(TempDirMixin, TestCase):
    def setUp(self):
        super().setUp()
        z = np.full((20, 20), 1000.0, dtype="float32")
        z[10:, :] = 2000.0
        p = write_geotiff(self.tmp / "d.tif", z, west=70.0, north=20.0, pixel_deg=0.01)
        call_command("import_dem", "--file", str(p), "--name", "r", "--vertical-datum", "test datum", stdout=StringIO(), stderr=StringIO())
        self.q = {"dataset": Dataset.objects.get(name="r").id, "product": "elevation", "bbox": "70,19.8,70.2,20", "width": 20, "height": 20}

    def test_fixed_range_changes_only_the_colours(self):
        c = APIClient()
        own = c.get("/api/v1/terrain/render/", self.q)
        shared = c.get("/api/v1/terrain/render/", {**self.q, "range": "0,4000"})
        self.assertEqual(own.status_code, 200)
        self.assertEqual(shared.status_code, 200)
        # The reported values are the data, whatever the stretch.
        self.assertEqual((own["X-Value-Min"], own["X-Value-Max"]), (shared["X-Value-Min"], shared["X-Value-Max"]))
        self.assertEqual(first_pixel(own.content)[:3], (40, 60, 140))  # 1000 m = bottom of its own range
        self.assertNotEqual(first_pixel(shared.content)[:3], (40, 60, 140))  # 1000 m = 25 % of 0..4000

    def test_invalid_range(self):
        for bad in ("5,1", "a,b", "1", "0,1e9"):
            self.assertEqual(APIClient().get("/api/v1/terrain/render/", {**self.q, "range": bad}).status_code, 400, bad)
