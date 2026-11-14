"""Unified catalog, safe dataset registration, offline-sync idempotency and conflicts."""
import uuid
from io import StringIO
from pathlib import Path

import numpy as np
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .raster_fixtures import TempDirMixin, requires_raster, write_geotiff


class CatalogTests(TestCase):
    def test_all_planets_and_filters(self):
        c = APIClient()
        b = c.get("/api/v1/datasets/catalog/").json()
        self.assertEqual(set(b["types"]), {"IMAGERY", "DEM", "TOPOGRAPHY", "WEATHER", "GEOLOGY", "BATHYMETRY"})
        planets = {e["planet"] for e in b["results"]}
        self.assertEqual(planets, {"MARS", "MOON", "MERCURY", "VENUS", "EARTH"})
        for e in b["results"]:
            for k in ("dataset", "source", "instrument", "product_id", "data_type", "resolution", "spatial_coverage",
                      "temporal_coverage", "crs", "units", "vertical_datum", "license", "url", "status", "facts"):
                self.assertIn(k, e, (e["key"], k))
        moon_dem = c.get("/api/v1/datasets/catalog/", {"planet": "MOON", "type": "DEM"}).json()["results"]
        self.assertEqual([e["key"] for e in moon_dem], ["moon-gld100"])
        self.assertEqual(moon_dem[0]["status"], "NOT_DOWNLOADED")
        self.assertEqual(c.get("/api/v1/datasets/catalog/", {"type": "NOPE"}).status_code, 400)

    def test_online_sources_and_unverified_facts_are_labelled(self):
        res = APIClient().get("/api/v1/datasets/catalog/").json()["results"]
        gibs = next(e for e in res if e["key"] == "earth-gibs")
        self.assertEqual(gibs["status"], "ONLINE_SOURCE")
        usgs = next(e for e in res if e["key"] == "mercury-usgs-dem-665m")
        self.assertIn("from specification", usgs["facts"])


@requires_raster
class CatalogLocalStatusTests(TempDirMixin, TestCase):
    def test_registered_mola_marks_catalog_valid(self):
        r, c = np.mgrid[0:5, 0:5]
        p = write_geotiff(self.tmp / "m.tif", (r + c).astype("float32"), west=10, north=10, pixel_deg=0.1)
        call_command("import_dem", "--file", str(p), "--name", "mola-x", "--instrument", "MGS MOLA", "--vertical-datum", "d", stdout=StringIO(), stderr=StringIO())
        e = next(x for x in APIClient().get("/api/v1/datasets/catalog/", {"planet": "MARS"}).json()["results"] if x["key"] == "mars-mola-megdr")
        self.assertEqual(e["status"], "VALID")
        self.assertEqual(e["local_datasets"][0]["name"], "mola-x")
        Path(p).unlink()
        e = next(x for x in APIClient().get("/api/v1/datasets/catalog/", {"planet": "MARS"}).json()["results"] if x["key"] == "mars-mola-megdr")
        self.assertEqual(e["status"], "UNAVAILABLE")


class RegisterSafetyTests(TempDirMixin, TestCase):
    def post(self, rel):
        return APIClient().post("/api/v1/datasets/register/", {"file_path": rel, "name": "x"}, format="json")

    def test_path_traversal_rejected(self):
        with override_settings(MARS_DATA_DIR=self.tmp):
            r = self.post("../../etc/passwd")
        self.assertEqual(r.json()["error"]["code"], "PATH_OUTSIDE_DATA_DIR")

    def test_wrong_extension_and_fake_content_rejected(self):
        (self.tmp / "notes.txt").write_text("hello")
        (self.tmp / "fake.tif").write_text("this is not a tiff")
        with override_settings(MARS_DATA_DIR=self.tmp):
            self.assertEqual(self.post("notes.txt").json()["error"]["code"], "UNSUPPORTED_FILE_TYPE")
            self.assertEqual(self.post("fake.tif").json()["error"]["code"], "UNSUPPORTED_FILE_TYPE")
            self.assertEqual(self.post("missing.tif").status_code, 404)

    def test_size_limit(self):
        (self.tmp / "big.tif").write_bytes(b"II*\x00" + b"\x00" * 2000)
        with override_settings(MARS_DATA_DIR=self.tmp, MAX_REGISTER_FILE_BYTES=1000):
            r = self.post("big.tif")
        self.assertEqual(r.status_code, 413)


class SyncTests(TestCase):
    def setUp(self):
        self.c = APIClient()
        self.hz = {"title": "Rim boulders", "lon_east_deg": 77.4, "lat_deg": 18.4}

    def test_create_with_client_id_is_idempotent(self):
        cid = str(uuid.uuid4())
        a = self.c.post("/api/v1/hazards/", {**self.hz, "client_id": cid}, format="json")
        b = self.c.post("/api/v1/hazards/", {**self.hz, "client_id": cid}, format="json")
        self.assertEqual(a.status_code, 201)
        self.assertEqual(b.status_code, 200)
        self.assertTrue(b.json()["replayed"])
        self.assertEqual(a.json()["id"], b.json()["id"])
        self.assertEqual(self.c.get("/api/v1/hazards/").json()["count"], 1)

    def test_version_increments_and_stale_update_conflicts(self):
        h = self.c.post("/api/v1/hazards/", self.hz, format="json").json()
        self.assertEqual(h["version"], 1)
        ok = self.c.patch(f"/api/v1/hazards/{h['id']}/", {"severity": "HIGH", "version": 1}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["version"], 2)
        stale = self.c.patch(f"/api/v1/hazards/{h['id']}/", {"severity": "LOW", "version": 1}, format="json")
        self.assertEqual(stale.status_code, 409)
        body = stale.json()["error"]
        self.assertEqual(body["code"], "CONFLICT")
        self.assertEqual(body["details"]["server"]["severity"], "HIGH")  # server copy returned, not overwritten
        self.assertEqual(self.c.get(f"/api/v1/hazards/{h['id']}/").json()["severity"], "HIGH")

    def test_mission_sync_fields(self):
        m = self.c.post("/api/v1/missions/", {"name": "Sync test", "client_id": str(uuid.uuid4())}, format="json").json()
        self.assertEqual(m["version"], 1)
        r = self.c.patch(f"/api/v1/missions/{m['id']}/", {"status": "ACTIVE", "version": 1}, format="json")
        self.assertEqual(r.json()["version"], 2)
        self.assertEqual(self.c.patch(f"/api/v1/missions/{m['id']}/", {"status": "ABORTED", "version": 1}, format="json").status_code, 409)
        # PATCH without version keeps v0.1 behaviour (last write wins)
        self.assertEqual(self.c.patch(f"/api/v1/missions/{m['id']}/", {"status": "COMPLETED"}, format="json").status_code, 200)
