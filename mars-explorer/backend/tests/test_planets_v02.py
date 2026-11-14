"""Planet registry: radii vs PROJ, CRS aliases per body, API."""
from django.test import SimpleTestCase, TestCase
from pyproj import CRS
from rest_framework.test import APIClient

from services.mars_coordinates import UnknownCRSError, resolve_crs
from services.planet_registry import PLANETS, crs_matches_planet, get_planet, layers_for, planet_for_semi_major


class RegistryTests(SimpleTestCase):
    def test_reference_crs_radii_match_proj(self):
        for p in PLANETS.values():
            crs = CRS(p.reference_crs)
            self.assertAlmostEqual(crs.ellipsoid.semi_major_metre, p.radius_equatorial_m, places=3, msg=p.id)
            self.assertAlmostEqual(crs.ellipsoid.semi_minor_metre, p.radius_polar_m, places=3, msg=p.id)
            self.assertTrue(crs_matches_planet(crs, p.id), p.id)

    def test_bodies_are_distinguishable(self):
        self.assertEqual(planet_for_semi_major(6_378_137).id, "EARTH")
        self.assertEqual(planet_for_semi_major(6_051_800).id, "VENUS")
        self.assertEqual(planet_for_semi_major(1_737_400).id, "MOON")
        self.assertEqual(planet_for_semi_major(2_439_400).id, "MERCURY")  # ESRI:104974 value also accepted
        self.assertIsNone(planet_for_semi_major(1_000_000))

    def test_trek_declared_crs_resolve_to_their_own_body_only(self):
        cases = {
            "MARS": "urn:ogc:def:crs:EPSG::104905",
            "MOON": "urn:ogc:def:crs:EPSG::104903",
            "MERCURY": "urn:ogc:def:crs:IAU2000::19900",
        }
        for body, urn in cases.items():
            crs, alias = resolve_crs(urn, planet=body)
            self.assertIsNotNone(alias, body)
            for other in cases:
                if other != body:
                    with self.assertRaises(UnknownCRSError, msg=f"{urn} accepted for {other}"):
                        resolve_crs(urn, planet=other)

    def test_wgs84_never_applied_to_mars(self):
        with self.assertRaises(UnknownCRSError):
            resolve_crs("EPSG:4326", planet="MARS")
        crs, _ = resolve_crs("EPSG:4326", planet="EARTH")
        self.assertEqual(crs.ellipsoid.semi_major_metre, 6378137.0)

    def test_mars_is_primary_and_venus_experimental(self):
        self.assertEqual(get_planet("mars").status, "PRIMARY")
        self.assertEqual(get_planet("VENUS").status, "EXPERIMENTAL")
        self.assertEqual(layers_for("VENUS"), [])
        self.assertTrue(get_planet("EARTH").browser_geolocation_allowed)
        self.assertFalse(get_planet("MARS").browser_geolocation_allowed)
        self.assertFalse(get_planet("MOON").browser_geolocation_allowed)

    def test_layers_declare_their_body_crs_and_are_not_elevation(self):
        for body in ("MARS", "MOON", "MERCURY"):
            for layer in layers_for(body):
                self.assertFalse(layer["pixels_are_elevation"])
                resolve_crs(layer["crs"], planet=body)  # must not raise
                self.assertIn(f"/{body.capitalize()}/EQ/{layer['layer_id']}/", layer["capabilities_url"])


class PlanetApiTests(TestCase):
    def test_list_detail_layers(self):
        c = APIClient()
        ids = [p["id"] for p in c.get("/api/v1/planets/").json()]
        self.assertEqual(set(ids), {"MARS", "EARTH", "MOON", "MERCURY", "VENUS"})
        moon = c.get("/api/v1/planets/moon/").json()
        self.assertEqual(moon["radius_equatorial_m"], 1737400.0)
        self.assertEqual(len(moon["layers"]), 2)
        self.assertEqual(len(c.get("/api/v1/planets/MERCURY/layers/").json()), 2)
        self.assertEqual(c.get("/api/v1/planets/pluto/").status_code, 404)

    def test_moon_point_query_uses_moon_crs(self):
        r = APIClient().get("/api/v1/terrain/coverage/", {"lon": 10, "lat": 5, "planet": "MOON"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["query"]["crs_resolution"]["resolved_as"], "ESRI:104903")
        bad = APIClient().get("/api/v1/terrain/coverage/", {"lon": 10, "lat": 5, "planet": "MOON", "crs": "urn:ogc:def:crs:EPSG::104905"})
        self.assertEqual(bad.status_code, 400)
