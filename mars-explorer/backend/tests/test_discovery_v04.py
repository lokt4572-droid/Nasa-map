"""v0.4 dataset discovery, remote rasters, coverage and profile.

MOCKED INTEGRATION TESTS: the STAC documents below are hand-written in the provider's shape
and the "remote" raster is a local synthetic GeoTIFF. Nothing here proves that the USGS
service is up or that real planetary values are right — see scripts/check_providers.py for
live checks."""
from contextlib import contextmanager
from io import StringIO
from unittest import mock

import numpy as np
from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from apps.datasets.models import Dataset
from apps.datasets.services import coverage_service, dataset_discovery, stac_client
from services import remote_raster, terrain_patch

from .raster_fixtures import TempDirMixin, requires_raster, write_geotiff

HOST = "astrogeo-ard.s3-us-west-2.amazonaws.com"
URL = f"https://{HOST}/mars/fixture/FIXTURE_dtm.tif"
WEST, NORTH, PIX = 77.0, 19.0, 0.001  # 400 x 400 cells of ~59 m


def stac_item(pid="FIXTURE_A", collection="mro_ctx_controlled_usgs_dtms", gsd=20.0, valid=95.0, ring=None, href=URL):
    ring = ring or [[77.0, 18.6], [77.4, 18.6], [77.4, 19.0], [77.0, 19.0], [77.0, 18.6]]
    return {
        "id": pid, "collection": collection, "bbox": [77.0, 18.6, 77.4, 19.0],
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"gsd": gsd, "license": "CC0-1.0", "datetime": "2010-01-01T00:00:00Z", "missions": ["MRO"],
                       "proj:wkt2": 'PROJCS["Mars (2015) - Sphere / Ocentric / Equirectangular, clon = 0",...]'},
        "assets": {
            "dtm": {"href": href, "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                    "raster:bands": [{"statistics": {"valid_percent": valid, "minimum": -10, "maximum": 10}}]},
            "orthoimage": {"href": href.replace("_dtm", "_ortho"), "type": "image/tiff; application=geotiff"},
            "thumbnail": {"href": "https://example.invalid/t.jpg", "type": "image/jpeg"},
        },
        "links": [{"rel": "self", "href": "https://example.invalid/items/" + pid}],
    }


def fake_fetch(items):
    def _f(params):
        feats = [i for i in items if i["collection"] == params["collections"] and ("ids" not in params or i["id"] == params["ids"])]
        return {"features": feats, "numberMatched": len(feats)}
    return _f


class StacClientTests(SimpleTestCase):
    def test_normalize_item_keeps_provider_metadata(self):
        rec = stac_client.normalize_item(stac_item())
        self.assertEqual((rec["planet_id"], rec["data_type"], rec["resolution_m"]), ("MARS", "DEM", 20.0))
        self.assertEqual(rec["assets"]["dem"], URL)
        self.assertEqual(rec["effective_accuracy"], "NOT_DOCUMENTED")  # resolution is not accuracy
        self.assertEqual(rec["quality_status"], "MOSTLY_COMPLETE")
        self.assertIn("MOLA", rec["vertical_datum"])
        self.assertTrue(rec["imagery_available"])
        self.assertEqual(rec["latitude_type"], "PLANETOCENTRIC")

    def test_item_without_dtm_asset_is_not_a_dem(self):
        item = stac_item()
        del item["assets"]["dtm"]  # imagery only: must not become a DEM record
        self.assertIsNone(stac_client.normalize_item(item))
        self.assertIsNone(stac_client.normalize_item({**stac_item(), "collection": "unknown"}))

    def test_quality_classes(self):
        for pct, cls in ((95, "MOSTLY_COMPLETE"), (60, "PARTIAL_GAPS"), (10, "LARGE_GAPS")):
            self.assertEqual(stac_client.normalize_item(stac_item(valid=pct))["quality_status"], cls)
        item = stac_item()
        item["assets"]["dtm"].pop("raster:bands")
        self.assertEqual(stac_client.normalize_item(item)["quality_status"], "NOT_DOCUMENTED")

    def test_longitude_normalisation_and_seam_split(self):
        self.assertAlmostEqual(stac_client.normalize_lon(350), -10)
        self.assertAlmostEqual(stac_client.normalize_lon(-190), 170)
        self.assertEqual(stac_client.split_bbox(10, -5, 20, 5), [(10, -5, 20, 5)])
        self.assertEqual(stac_client.split_bbox(170, -5, 190, 5), [(170, -5, 180.0, 5), (-180.0, -5, -170, 5)])
        self.assertEqual(stac_client.split_bbox(350, -5, 370, 5), [(-10, -5, 10, 5)])  # crosses 0/360 only
        self.assertEqual(stac_client.split_bbox(0, -90, 360, 90), [(-180.0, -90, 180.0, 90)])

    def test_point_in_footprint_uses_the_polygon_not_the_bbox(self):
        tri = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [0, 10], [0, 0]]]}
        self.assertTrue(stac_client.point_in_footprint(tri, 2, 2))
        self.assertFalse(stac_client.point_in_footprint(tri, 9, 9))  # inside the bbox, outside the footprint
        self.assertTrue(stac_client.point_in_footprint(tri, 362, 2))  # 0..360 longitude accepted
        multi = {"type": "MultiPolygon", "coordinates": [tri["coordinates"], [[[20, 20], [30, 20], [30, 30], [20, 30], [20, 20]]]]}
        self.assertTrue(stac_client.point_in_footprint(multi, 25, 25))
        self.assertFalse(stac_client.point_in_footprint(None, 0, 0))

    def test_search_filters_by_footprint_and_resolution(self):
        cache.clear()
        far = stac_item("FAR", ring=[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]])
        fine = stac_item("FINE", collection="mro_hirise_socet_dtms", gsd=1.0)
        with mock.patch.object(stac_client, "_fetch", side_effect=fake_fetch([stac_item(), far, fine])):
            out = stac_client.search("MARS", point=(77.2, 18.8))
            self.assertEqual([p["product_id"] for p in out["products"]], ["FINE", "FIXTURE_A"])  # finest first
            out = stac_client.search("MARS", point=(77.2, 18.8), max_resolution_m=5)
            self.assertEqual([p["product_id"] for p in out["products"]], ["FINE"])
            self.assertEqual(stac_client.search("MERCURY", point=(0, 0))["products"], [])  # no catalogue: no request

    def test_provider_failure_is_a_typed_error(self):
        from services import http_client

        cache.clear()
        with mock.patch.object(http_client, "get_json", side_effect=http_client.ProviderTimeout("x", "slow")):
            with self.assertRaises(stac_client.StacError) as ctx:
                stac_client.search("MARS", point=(1, 1))
        self.assertEqual(ctx.exception.code, "PROVIDER_TIMEOUT")
        with mock.patch.object(http_client, "get_json", return_value=["not", "a", "catalogue"]):
            with self.assertRaises(stac_client.StacError):
                stac_client.search("MARS", point=(2, 2))


class RemoteRasterRulesTests(SimpleTestCase):
    def test_only_allow_listed_https_geotiffs(self):
        self.assertEqual(remote_raster.check_remote_url(URL), URL)
        for bad in (
            "http://" + HOST + "/a.tif",  # not https
            "https://evil.example/a.tif",  # host not allow-listed
            f"https://{HOST}.evil.example/a.tif",
            f"https://user:pw@{HOST}/a.tif",  # credentials
            f"https://{HOST}/a.tif?x=1",
            f"https://{HOST}/a.exe",
            "file:///etc/passwd",
        ):
            with self.assertRaises(remote_raster.RemoteRasterError, msg=bad):
                remote_raster.check_remote_url(bad)

    def test_file_available_and_disable_switch(self):
        self.assertTrue(remote_raster.file_available(URL))
        self.assertFalse(remote_raster.file_available("https://evil.example/a.tif"))
        with override_settings(REMOTE_DEM_ENABLED=False):
            self.assertFalse(remote_raster.file_available(URL))
            with self.assertRaises(remote_raster.RemoteRasterError):
                with remote_raster.open_raster(URL):
                    pass


@requires_raster
class RemoteDemTests(TempDirMixin, TestCase):
    """The 'remote' COG is a local synthetic raster served through a patched opener."""

    def setUp(self):
        super().setUp()
        cache.clear()
        r, cc = np.mgrid[0:400, 0:400]
        self.z = (500.0 + r + 0.5 * cc).astype("float32")
        self.local = write_geotiff(self.tmp / "remote.tif", self.z, west=WEST, north=NORTH, pixel_deg=PIX)
        real_open = remote_raster.open_raster

        @contextmanager
        def opener(path):
            with real_open(self.local if str(path) == URL else path) as src:
                yield src

        p = mock.patch.object(remote_raster, "open_raster", opener)
        p.start()
        self.addCleanup(p.stop)
        self.c = APIClient()
        self.product = stac_client.normalize_item(stac_item())

    def _with_catalogue(self, items):
        return mock.patch.object(stac_client, "_fetch", side_effect=fake_fetch(items))

    def test_register_remote_dem_validates_and_is_idempotent(self):
        ds = dataset_discovery.register_remote_dem(self.product)
        self.assertEqual((ds.status, ds.access, ds.file_path), ("VALID", "REMOTE_COG", URL))
        self.assertEqual(ds.units, "m")
        self.assertIn("MOLA", ds.vertical_datum)
        self.assertAlmostEqual(ds.resolution_meters, 59.27, delta=0.1)  # from the file, not from the catalogue gsd
        self.assertEqual(ds.footprint["type"], "Polygon")
        self.assertEqual(dataset_discovery.register_remote_dem(self.product).id, ds.id)
        self.assertEqual(Dataset.objects.count(), 1)

    def test_wrong_body_is_rejected_and_remembered(self):
        moon = {**self.product, "planet_id": "MOON", "product_id": "WRONG_BODY"}
        with self.assertRaises(dataset_discovery.DiscoveryError):
            dataset_discovery.register_remote_dem(moon)
        self.assertEqual(Dataset.objects.get(product_id="WRONG_BODY").status, "INVALID")
        with self.assertRaises(dataset_discovery.DiscoveryError):  # not re-read
            dataset_discovery.register_remote_dem(moon)

    def test_host_outside_allow_list_is_never_registered(self):
        bad = {**self.product, "assets": {**self.product["assets"], "dem": "https://evil.example/x_dtm.tif"}}
        with self.assertRaises(dataset_discovery.DiscoveryError) as ctx:
            dataset_discovery.register_remote_dem(bad)
        self.assertEqual(ctx.exception.code, "REMOTE_HOST_NOT_ALLOWED")
        self.assertEqual(Dataset.objects.count(), 0)

    def test_patch_local_source_never_asks_the_catalogue(self):
        with mock.patch.object(stac_client, "_fetch", side_effect=AssertionError("catalogue must not be called")):
            r = self.c.get("/api/v1/terrain/patch/", {"planet": "MARS", "lon": 77.2, "lat": 18.8})
        self.assertEqual(r.status_code, 404)

    def test_patch_auto_uses_the_catalogue_dtm_with_true_values(self):
        with self._with_catalogue([stac_item()]):
            r = self.c.get("/api/v1/terrain/patch/", {"planet": "MARS", "lon": 77.2, "lat": 18.8, "source": "auto", "max_dimension": 16})
        self.assertEqual(r.status_code, 200, r.content)
        b = r.json()
        self.assertEqual((b["dataset"]["access"], b["coverage_status"], b["processing_status"]), ("REMOTE_COG", "AVAILABLE", "READY"))
        self.assertEqual(b["dataset"]["effective_accuracy"], "NOT_DOCUMENTED")
        self.assertAlmostEqual(b["radius_m"], b["resolution_m"] * 8, delta=1)  # native resolution by default
        z = terrain_patch.decode_elevation(b["elevation"], b["width"], b["height"])
        self.assertTrue(np.isin(z, self.z).all())  # every value is a real cell of the raster
        row, col = int((NORTH - 18.8) / PIX), int((77.2 - WEST) / PIX)
        self.assertLess(abs(float(z[8, 8]) - float(self.z[row, col])), 3.0)

    def test_patch_auto_prefers_a_finer_registered_dem(self):
        fine = write_geotiff(self.tmp / "fine.tif", self.z, west=77.15, north=18.84, pixel_deg=0.0002)  # ~12 m cells: finer than the 20 m product
        call_command("import_dem", "--file", str(fine), "--name", "fine-local", "--vertical-datum", "test datum", stdout=StringIO(), stderr=StringIO())
        with self._with_catalogue([stac_item()]):
            r = self.c.get("/api/v1/terrain/patch/", {"planet": "MARS", "lon": 77.2, "lat": 18.8, "source": "auto", "max_dimension": 16})
        self.assertEqual(r.json()["dataset"]["name"], "fine-local")
        self.assertFalse(Dataset.objects.filter(access="REMOTE_COG").exists())  # coarser product not even registered

    def test_patch_auto_skips_unreadable_product_and_reports_it(self):
        broken = stac_item("BROKEN", collection="mro_hirise_socet_dtms", gsd=1.0, href=f"https://{HOST}/mars/missing_dtm.tif")
        with self._with_catalogue([broken, stac_item()]):
            r = self.c.get("/api/v1/terrain/patch/", {"planet": "MARS", "lon": 77.2, "lat": 18.8, "source": "auto", "max_dimension": 16})
        self.assertEqual(r.status_code, 200, r.content)
        sel = r.json()["selection"]
        self.assertEqual([s["product_id"] for s in sel["skipped_products"]], ["BROKEN"])
        self.assertEqual(r.json()["dataset"]["product_id"], "FIXTURE_A")

    def test_no_coverage_is_reported_not_invented(self):
        with self._with_catalogue([]):
            r = self.c.get("/api/v1/terrain/patch/", {"planet": "MARS", "lon": 10, "lat": 10, "source": "auto"})
            self.assertEqual(r.status_code, 404)
            self.assertEqual(r.json()["error"]["code"], "DEM_NOT_AVAILABLE")
            cov = self.c.get("/api/v1/terrain/coverage/", {"planet": "MARS", "lon": 10, "lat": 10, "remote": "1"}).json()
        self.assertEqual(cov["coverage_status"], "NO_DATA_COVERAGE")

    def test_coverage_lists_catalogue_products_without_reading_them(self):
        with self._with_catalogue([stac_item()]), mock.patch.object(dataset_discovery, "register_remote_dem", side_effect=AssertionError):
            cov = self.c.get("/api/v1/terrain/coverage/", {"planet": "MARS", "lon": 77.2, "lat": 18.8, "remote": "1"}).json()
        self.assertEqual(cov["coverage_status"], "AVAILABLE_REMOTE")
        self.assertEqual(cov["catalogue"]["products"][0]["product_id"], "FIXTURE_A")
        self.assertEqual(cov["datasets"], [])

    def test_provider_down_is_reported(self):
        with mock.patch.object(stac_client, "_fetch", side_effect=stac_client.StacError("down", "PROVIDER_TIMEOUT")):
            cov = self.c.get("/api/v1/datasets/coverage/", {"planet": "MARS", "lon": 77.2, "lat": 18.8}).json()
            self.assertEqual((cov["coverage_status"], cov["provider"]["status"]), ("PROVIDER_ERROR", "ERROR"))
            r = self.c.get("/api/v1/datasets/search/", {"planet": "MARS", "bbox": "77,18,78,19"})
        self.assertEqual(r.status_code, 504)

    def test_search_endpoint_validation_and_filters(self):
        items = [stac_item(), stac_item("GAPPY", valid=20.0)]
        with self._with_catalogue(items):
            r = self.c.get("/api/v1/datasets/search/", {"planet": "MARS", "bbox": "77,18,78,19"})
            self.assertEqual(r.json()["count"], 2)
            r = self.c.get("/api/v1/coverage/MARS/search/", {"longitude": 77.2, "latitude": 18.8, "radius_m": 5000, "minimum_quality": "PARTIAL_GAPS"})
            self.assertEqual([p["product_id"] for p in r.json()["products"]], ["FIXTURE_A"])
            self.assertEqual(self.c.get("/api/v1/datasets/search/", {"planet": "MERCURY", "bbox": "0,0,1,1"}).json()["provider"]["status"], "NO_CATALOGUE_FOR_BODY")
        for bad in ({"planet": "PLUTO", "bbox": "0,0,1,1"}, {"planet": "MARS", "bbox": "5,0,1,1"}, {"planet": "MARS"},
                    {"planet": "MARS", "bbox": "0,0,1,1", "data_type": "MAGIC"}, {"planet": "MARS", "lon": "nan", "lat": 0}):
            self.assertEqual(self.c.get("/api/v1/datasets/search/", bad).status_code, 400, bad)

    def test_register_remote_endpoint_takes_ids_not_urls(self):
        with self._with_catalogue([stac_item()]):
            r = self.c.post("/api/v1/datasets/register-remote/", {"collection": "mro_ctx_controlled_usgs_dtms", "product_id": "FIXTURE_A"}, format="json")
            self.assertEqual(r.status_code, 201, r.content)
            self.assertIsNone(r.json()["local_file"])
            self.assertEqual(self.c.post("/api/v1/datasets/register-remote/", {"collection": "mro_ctx_controlled_usgs_dtms", "product_id": "NOPE"}, format="json").status_code, 404)
            self.assertEqual(self.c.post("/api/v1/datasets/register-remote/", {"collection": "x", "product_id": "y"}, format="json").status_code, 404)

    def test_planet_coverage_levels(self):
        dataset_discovery.register_remote_dem(self.product)
        b = self.c.get("/api/v1/coverage/MARS/").json()
        self.assertEqual([d["product_id"] for d in b["levels"]["REGIONAL"]], ["FIXTURE_A"])
        self.assertEqual({c["collection"] for c in b["catalogues"]}, {"mro_hirise_socet_dtms", "mro_ctx_controlled_usgs_dtms"})
        self.assertEqual(self.c.get("/api/v1/coverage/MOON/").json()["catalogues"][0]["instrument"], "Kaguya/SELENE Terrain Camera")
        self.assertEqual(self.c.get("/api/v1/coverage/NOWHERE/").status_code, 400)

    def test_profile_reads_true_cells_and_geodesic_distance(self):
        dataset_discovery.register_remote_dem(self.product)
        q = {"planet": "MARS", "from_lon": 77.1, "from_lat": 18.9, "to_lon": 77.3, "to_lat": 18.9, "samples": 21}
        r = self.c.get("/api/v1/terrain/profile/", q)
        self.assertEqual(r.status_code, 200, r.content)
        b = r.json()
        self.assertEqual(len(b["points"]), 21)
        import math
        expected = math.radians(0.2) * 3396190 * math.cos(math.radians(18.9))
        self.assertAlmostEqual(b["distance_m"], expected, delta=expected * 0.005)
        zs = [p["elevation_m"] for p in b["points"]]
        self.assertTrue(all(z is not None for z in zs))
        self.assertAlmostEqual(zs[-1] - zs[0], 0.5 * 200, delta=3)  # raster rises 0.5 m per column
        self.assertAlmostEqual(b["statistics"]["total_ascent_m"], zs[-1] - zs[0], delta=3)
        r = self.c.get("/api/v1/terrain/profile/", {**q, "to_lon": 120})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.c.get("/api/v1/terrain/profile/", {**q, "samples": 5000}).status_code, 400)

    def test_health_providers_lists_stac_without_probing_cesium(self):
        from services import http_client

        with mock.patch.object(http_client, "get_bytes", return_value=b"{}"):
            b = self.c.get("/api/v1/health/providers/", {"refresh": "1"}).json()
        self.assertEqual(b["sources"]["USGS Astrogeology STAC"]["status"], "UP")
        self.assertEqual(b["sources"]["Cesium ion"]["status"], "NOT_PROBED")
