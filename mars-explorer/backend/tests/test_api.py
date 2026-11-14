from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from apps.hazards.models import Hazard
from apps.missions.models import Mission
from services.mars_coordinates import TREK_DECLARED_CRS


class HealthTests(TestCase):
    def test_health_ok(self):
        r = APIClient().get("/api/v1/health/")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "ok")
        self.assertIn("available", body["raster_backend"])
        self.assertIn("path", body["data_dir"])


class HazardApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.payload = {
            "title": "Boulder field on crater rim",
            "hazard_type": "BOULDER_FIELD",
            "severity": "MEDIUM",
            "lon_east_deg": 77.4,
            "lat_deg": 18.45,
            "reference_layer": "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd",
        }

    def test_create_and_list(self):
        r = self.client.post("/api/v1/hazards/", self.payload, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual(body["crs"], TREK_DECLARED_CRS)
        self.assertEqual(body["latitude_convention"], "AS_DECLARED_BY_SOURCE")
        self.assertEqual(body["verification"], "UNVERIFIED")
        r = self.client.get("/api/v1/hazards/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 1)

    def test_longitude_normalized_to_east_180(self):
        r = self.client.post("/api/v1/hazards/", {**self.payload, "lon_east_deg": 282.55}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertAlmostEqual(r.json()["lon_east_deg"], -77.45, places=9)

    def test_invalid_latitude_rejected(self):
        r = self.client.post("/api/v1/hazards/", {**self.payload, "lat_deg": 95}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("lat_deg", r.json()["error"]["details"])

    def test_earth_crs_rejected(self):
        r = self.client.post("/api/v1/hazards/", {**self.payload, "crs": "EPSG:4326"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("crs", r.json()["error"]["details"])

    def test_patch_and_delete(self):
        hid = self.client.post("/api/v1/hazards/", self.payload, format="json").json()["id"]
        r = self.client.patch(f"/api/v1/hazards/{hid}/", {"verification": "CONFIRMED"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Hazard.objects.get(pk=hid).verification, "CONFIRMED")
        self.assertEqual(self.client.delete(f"/api/v1/hazards/{hid}/").status_code, 204)
        self.assertEqual(self.client.get(f"/api/v1/hazards/{hid}/").status_code, 404)

    def test_put_not_allowed(self):
        hid = self.client.post("/api/v1/hazards/", self.payload, format="json").json()["id"]
        self.assertEqual(self.client.put(f"/api/v1/hazards/{hid}/", self.payload, format="json").status_code, 405)


class MissionApiTests(TestCase):
    def test_crud_and_waypoints(self):
        c = APIClient()
        r = c.post("/api/v1/missions/", {"name": "Jezero traverse study"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        mid = r.json()["id"]
        self.assertTrue(r.json()["demo_mode"])
        r = c.post(
            "/api/v1/waypoints/",
            {"mission": mid, "name": "Base A", "kind": "BASE", "lon_east_deg": 77.4, "lat_deg": 18.4},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        r = c.get(f"/api/v1/missions/{mid}/")
        self.assertEqual(len(r.json()["waypoints"]), 1)
        r = c.patch(f"/api/v1/missions/{mid}/", {"status": "ACTIVE"}, format="json")
        self.assertEqual(r.json()["status"], "ACTIVE")
        self.assertEqual(c.delete(f"/api/v1/missions/{mid}/").status_code, 204)
        self.assertFalse(Mission.objects.exists())

    def test_blank_name_rejected(self):
        r = APIClient().post("/api/v1/missions/", {"name": "   "}, format="json")
        self.assertEqual(r.status_code, 400)


class RoutingApiTests(TestCase):
    def test_plan_is_not_implemented_and_returns_no_route(self):
        r = APIClient().post(
            "/api/v1/routes/plan/",
            {"start": {"lon_east_deg": 77.4, "lat_deg": 18.4}, "end": {"lon_east_deg": 77.5, "lat_deg": 18.5}},
            format="json",
        )
        self.assertEqual(r.status_code, 501)
        body = r.json()
        self.assertEqual(body["error"]["code"], "NOT_IMPLEMENTED")
        self.assertNotIn("route", body)

    def test_plan_validates_input(self):
        r = APIClient().post("/api/v1/routes/plan/", {"start": {"lon_east_deg": 1}}, format="json")
        self.assertEqual(r.status_code, 400)


class TerrainWithoutDemTests(TestCase):
    def test_sample_without_dem_reports_not_available(self):
        r = APIClient().get("/api/v1/terrain/sample/", {"lon": 77.45, "lat": 18.44})
        self.assertIn(r.status_code, (404, 503))
        body = r.json()
        self.assertIn(body["error"]["code"], ("DEM_NOT_AVAILABLE", "DEM_BACKEND_UNAVAILABLE"))
        self.assertNotIn("elevation_m", body)

    def test_sample_backend_missing(self):
        with mock.patch(
            "services.dem_reader.raster_backend_status",
            return_value={"available": False, "error": "rasterio not installed", "backend": None, "gdal_version": None},
        ):
            r = APIClient().get("/api/v1/terrain/sample/", {"lon": 77.45, "lat": 18.44})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"]["code"], "DEM_BACKEND_UNAVAILABLE")

    def test_coverage_no_data(self):
        r = APIClient().get("/api/v1/terrain/coverage/", {"lon": 0, "lat": 0})
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.json()["terrain_analysis_status"], ("NO DATA", "ERROR"))
        self.assertEqual(r.json()["datasets"], [])
        self.assertEqual(r.json()["query"]["crs_resolution"]["resolved_as"], "ESRI:104905")

    def test_bad_query(self):
        r = APIClient().get("/api/v1/terrain/sample/", {"lon": "abc", "lat": 18})
        self.assertEqual(r.status_code, 400)
        r = APIClient().get("/api/v1/terrain/sample/", {"lon": 10, "lat": 18, "crs": "EPSG:3857"})
        self.assertEqual(r.status_code, 400)
