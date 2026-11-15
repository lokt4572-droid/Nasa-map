"""Unified data registry: shape, vocabulary and honesty rules (no network)."""
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from services import data_registry as reg


class ResolutionParsingTests(SimpleTestCase):
    def test_metres_only(self):
        self.assertEqual(reg.resolution_m("463 m/px"), 463.0)
        self.assertEqual(reg.resolution_m("25 cm/px"), 0.25)
        self.assertEqual(reg.resolution_m("≈5 × 5 km/px"), 5000.0)
        self.assertEqual(reg.resolution_m("1″ (≈30 m) / 3″ (≈90 m)"), 30.0)
        self.assertIsNone(reg.resolution_m("303 px/deg"))
        self.assertIsNone(reg.resolution_m(None))


class RegistryTests(TestCase):
    def test_every_record_has_the_full_vocabulary_and_no_invented_accuracy(self):
        for planet in ("MARS", "MOON", "MERCURY", "EARTH", "VENUS"):
            b = APIClient().get("/api/v1/datasets/registry/", {"planet": planet}).json()
            self.assertEqual(b["fields"], reg.FIELDS)
            for r in b["datasets"]:
                self.assertEqual(set(r), set(reg.FIELDS), r["dataset_id"])
                self.assertIn(r["provider"], set(reg.ADAPTERS), r["dataset_id"])  # adapter ids only
                if r["effective_accuracy"] != reg.NOT_DOCUMENTED:
                    self.fail(f"{r['dataset_id']}: accuracy must come from a source, not from resolution")
                self.assertNotIn(":\\\\", str(r["local_file"]))  # never a server path

    def test_providers_per_body(self):
        def providers(planet):
            return {r["provider"] for r in APIClient().get("/api/v1/datasets/registry/", {"planet": planet}).json()["datasets"]}

        self.assertTrue({"NASA_TREK", "USGS_ASTROGEOLOGY", "CESIUM_ION", "NASA_PDS"} <= providers("MARS"))
        self.assertTrue({"NASA_GIBS", "COPERNICUS", "CESIUM_ION"} <= providers("EARTH"))
        self.assertNotIn("CESIUM_ION", providers("MERCURY"))  # no Cesium asset exists for Mercury

    def test_adapters_state_their_protocol_and_status(self):
        b = APIClient().get("/api/v1/datasets/registry/", {"planet": "MARS"}).json()
        a = b["adapters"]
        self.assertEqual(set(a), {"NASA_TREK", "NASA_GIBS", "NASA_PDS", "USGS_ASTROGEOLOGY", "STAC", "COPERNICUS", "CESIUM_ION", "OPENPLANETARYMAP", "LOCAL", "MANUAL_DOWNLOAD", "OTHER_ONLINE"})
        self.assertEqual(a["OPENPLANETARYMAP"]["status"], "NOT_IMPLEMENTED")
        self.assertIn("never analysis", a["CESIUM_ION"]["used_for"])

    def test_filters_and_validation(self):
        c = APIClient()
        b = c.get("/api/v1/datasets/registry/", {"planet": "MARS", "provider": "NASA_TREK"}).json()
        self.assertTrue(b["count"] > 5 and all(r["provider"] == "NASA_TREK" for r in b["datasets"]))
        self.assertEqual(c.get("/api/v1/datasets/registry/", {"planet": "MARS", "provider": "NOPE"}).status_code, 400)
        self.assertEqual(c.get("/api/v1/datasets/registry/", {"planet": "PLUTO"}).status_code, 400)
