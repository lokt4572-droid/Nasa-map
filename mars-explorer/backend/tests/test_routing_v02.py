"""A* route planner: synthetic terrains with known answers + API behaviour."""
import math
from io import StringIO

import numpy as np
from django.core.management import call_command
from django.test import TestCase
from pyproj import Geod
from rest_framework.test import APIClient

from apps.hazards.models import Hazard
from apps.routing.models import Route

from .raster_fixtures import MARS_SPHERE, TempDirMixin, requires_raster, write_geotiff

WEST, NORTH, PIX, N = 70.0, 20.0, 0.01, 40


def lonlat(row, col):
    return WEST + (col + 0.5) * PIX, NORTH - (row + 0.5) * PIX


def pt(row, col):
    lon, lat = lonlat(row, col)
    return {"lon_east_deg": lon, "lat_deg": lat, "crs": MARS_SPHERE, "latitude_convention": "PLANETOCENTRIC"}


def rowcol(lon, lat):
    return int((NORTH - lat) / PIX), int((lon - WEST) / PIX)


@requires_raster
class RoutePlannerTests(TempDirMixin, TestCase):
    def load(self, z, name="dem"):
        p = write_geotiff(self.tmp / f"{name}.tif", z.astype("float32"), west=WEST, north=NORTH, pixel_deg=PIX)
        call_command("import_dem", "--file", str(p), "--name", name, "--vertical-datum", "test datum", stdout=StringIO(), stderr=StringIO())

    def plan(self, start, end, **kw):
        return APIClient().post("/api/v1/routes/plan/", {"start": start, "end": end, **kw}, format="json")

    def test_flat_straight_route_distance_matches_geodesic(self):
        self.load(np.zeros((N, N)))
        r = self.plan(pt(10, 5), pt(10, 35), profile="STANDARD", include_alternative=False)
        self.assertEqual(r.status_code, 201, r.content)
        route = r.json()["route"]
        a, b = lonlat(10, 5), lonlat(10, 35)
        geo = Geod(a=3396190, b=3396190).inv(a[0], a[1], b[0], b[1])[2]
        self.assertAlmostEqual(route["distance_m"], geo, delta=geo * 0.01)
        self.assertEqual(route["total_ascent_m"], 0.0)
        self.assertEqual(route["unknown_terrain_fraction"], 0.0)
        self.assertEqual(r.json()["status"], "ROUTE_FOUND")
        self.assertNotIn(r.json()["status"], ("SAFE", "SAFE_ROUTE"))
        self.assertIn("Not a validated traversability or safety assessment", r.json()["disclaimer"])

    def test_wall_with_gap_forces_detour(self):
        z = np.zeros((N, N))
        z[:, 20] = 2000.0          # ~73 degree wall
        z[28:35, 20] = 0.0         # gap in rows 28..34
        self.load(z)
        for profile in ("CONSERVATIVE", "STANDARD"):
            r = self.plan(pt(10, 5), pt(10, 35), profile=profile, include_alternative=False)
            self.assertEqual(r.status_code, 201, (profile, r.content))
            rows = [rowcol(lon, lat)[0] for lon, lat in r.json()["route"]["geometry"]["coordinates"][1:-1]]
            self.assertGreaterEqual(max(rows), 28, profile)
            self.assertLess(r.json()["route"]["max_step_grade_deg"], 25.0)

    def test_closed_wall_no_passable_route(self):
        z = np.zeros((N, N))
        z[:, 20] = 2000.0
        self.load(z)
        r = self.plan(pt(10, 5), pt(10, 35), profile="STANDARD")
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["status"], "NO_PASSABLE_ROUTE")
        self.assertIsNone(r.json()["route"])

    def test_unknown_band_conservative_refuses_standard_reports(self):
        z = np.zeros((N, N))
        z[:, 20] = -9999.0  # nodata column across the whole map
        self.load(z)
        r = self.plan(pt(10, 5), pt(10, 35), profile="CONSERVATIVE")
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json(), {**r.json(), "status": "INSUFFICIENT_TERRAIN_DATA", "route": None})
        r = self.plan(pt(10, 5), pt(10, 35), profile="STANDARD", include_alternative=False)
        self.assertEqual(r.status_code, 201, r.content)
        frac = r.json()["route"]["unknown_terrain_fraction"]
        self.assertGreater(frac, 0.0)
        self.assertLess(frac, 0.2)
        self.assertIsNone(next(p for p in r.json()["route"]["elevation_profile"] if p["elevation_m"] is None)["elevation_m"])

    def test_hazard_is_avoided(self):
        self.load(np.zeros((N, N)))
        mid_lon, mid_lat = lonlat(10, 20)
        Hazard.objects.create(title="crater", lon_east_deg=mid_lon, lat_deg=mid_lat, crs=MARS_SPHERE,
                              latitude_convention="PLANETOCENTRIC", radius_m=1500)
        r = self.plan(pt(10, 5), pt(10, 35), profile="STANDARD", include_alternative=False)
        self.assertEqual(r.status_code, 201, r.content)
        g = Geod(a=3396190, b=3396190)
        dmin = min(g.inv(lon, lat, mid_lon, mid_lat)[2] for lon, lat in r.json()["route"]["geometry"]["coordinates"])
        self.assertGreater(dmin, 1500 + 100 - 600)  # radius + STANDARD buffer, minus one cell
        self.assertEqual(r.json()["hazards_considered"], 1)

    def test_waypoint_return_alternative_and_crud(self):
        self.load(np.zeros((N, N)))
        r = self.plan(pt(5, 5), pt(5, 35), waypoints=[pt(30, 20)], profile="STANDARD")
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        rows = [rowcol(lon, lat)[0] for lon, lat in body["route"]["geometry"]["coordinates"]]
        self.assertIn(30, rows)  # passes through the waypoint cell
        self.assertIsNotNone(body["return_route"])
        self.assertAlmostEqual(body["return_route"]["distance_m"], body["route"]["distance_m"], delta=1.0)
        self.assertIn("alternative_route", body)
        rid = body["id"]
        self.assertEqual(APIClient().get(f"/api/v1/routes/{rid}/").json()["id"], rid)
        self.assertEqual(APIClient().delete(f"/api/v1/routes/{rid}/").status_code, 204)
        self.assertFalse(Route.objects.filter(pk=rid).exists())
        self.assertEqual(APIClient().get(f"/api/v1/routes/{rid}/").status_code, 404)

    def test_profiles_documented_and_json_safe(self):
        profiles = APIClient().get("/api/v1/routes/profiles/").json()
        self.assertEqual({p["id"] for p in profiles}, {"CONSERVATIVE", "STANDARD"})
        for p in profiles:
            self.assertIn("not a validated", p["disclaimer"])
            self.assertTrue(all(v is None or not isinstance(v, float) or math.isfinite(v) for v in p.values()))
