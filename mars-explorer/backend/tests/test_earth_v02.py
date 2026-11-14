"""Earth backend: weather proxy, NASA POWER, geocoding, GIBS discovery, source health.

Providers are MOCKED here (unit tests must not depend on the internet). Real availability
is proven separately by the live checks (GET /api/v1/health/sources/, scripts) documented
in docs/IMPLEMENTATION_REPORT_V0.2.md.
"""
import datetime as dt
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.weather.models import WeatherSnapshot
from services import gibs, http_client

OM = {
    "latitude": 55.7817, "longitude": 37.570797, "elevation": 152.0, "timezone": "Europe/Moscow",
    "current_units": {"time": "iso8601", "interval": "seconds", "temperature_2m": "°C", "wind_speed_10m": "km/h"},
    "current": {"time": "2026-11-14T11:15", "interval": 900, "temperature_2m": 2.3, "wind_speed_10m": 12.8},
    "hourly_units": {"time": "iso8601", "temperature_2m": "°C"},
    "hourly": {"time": ["2026-11-14T00:00", "2026-11-14T01:00"], "temperature_2m": [1.0, 1.5]},
    "daily_units": {"time": "iso8601", "sunrise": "iso8601"},
    "daily": {"time": ["2026-11-14"], "sunrise": ["2026-11-14T08:02"], "sunset": ["2026-11-14T16:24"], "precipitation_probability_max": [100]},
}
POWER = {
    "header": {"fill_value": -999.0, "time_standard": "LST", "sources": ["MERRA2", "POWER"]},
    "parameters": {"T2M": {"units": "C", "longname": "Temperature at 2 Meters"}, "RH2M": {"units": "%"}, "PRECTOTCORR": {"units": "mm/day"}, "WS10M": {"units": "m/s"}},
    "properties": {"parameter": {"T2M": {"20260101": -14.86, "20260102": -999.0}, "RH2M": {"20260101": 80.0, "20260102": 81.0},
                                 "PRECTOTCORR": {"20260101": 0.1, "20260102": 0.0}, "WS10M": {"20260101": 3.0, "20260102": 2.0}}},
}


class WeatherApiTests(TestCase):
    def setUp(self):
        self.c = APIClient()

    @mock.patch("services.http_client.get_json", return_value=OM)
    def test_current_envelope_and_cache(self, m):
        r = self.c.get("/api/v1/weather/current/", {"lat": 55.75, "lon": 37.62})
        self.assertEqual(r.status_code, 200, r.content)
        b = r.json()
        self.assertEqual((b["provider"], b["data_type"]), ("Open-Meteo", "forecast_model"))
        self.assertEqual(b["valid_time"], "2026-11-14T11:15")
        self.assertEqual(b["units"]["temperature_2m"], "°C")
        self.assertEqual(b["data"]["temperature_2m"], 2.3)
        self.assertEqual(b["model_grid_cell"]["latitude"], 55.7817)
        self.assertEqual(b["missing_variables"][:2], ["relative_humidity_2m", "apparent_temperature"])
        self.assertIn("Open-Meteo", b["attribution"])
        self.assertIsNotNone(b["retrieved_at"])
        self.assertFalse(b["from_cache"])
        # second call for the same (rounded) point uses the cache, not the provider, and says so
        b2 = self.c.get("/api/v1/weather/forecast/", {"lat": 55.751, "lon": 37.621}).json()
        self.assertEqual(m.call_count, 1)
        self.assertTrue(b2["from_cache"])

    @mock.patch("services.http_client.get_json", return_value=OM)
    def test_expired_cache_is_refreshed_not_relabelled(self, m):
        self.c.get("/api/v1/weather/current/", {"lat": 10, "lon": 10})
        WeatherSnapshot.objects.update(expires_at=dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc))
        self.c.get("/api/v1/weather/current/", {"lat": 10, "lon": 10})
        self.assertEqual(m.call_count, 2)

    def test_coordinate_validation(self):
        self.assertEqual(self.c.get("/api/v1/weather/current/", {"lat": 91, "lon": 0}).status_code, 400)
        self.assertEqual(self.c.get("/api/v1/weather/forecast/", {"lat": 0, "lon": 181}).status_code, 400)
        self.assertEqual(self.c.get("/api/v1/weather/current/").status_code, 400)

    @mock.patch("services.http_client.get_json", side_effect=http_client.ProviderTimeout("Open-Meteo", "Open-Meteo did not answer within 15 s"))
    def test_provider_timeout(self, _):
        r = self.c.get("/api/v1/weather/current/", {"lat": 1, "lon": 1})
        self.assertEqual(r.status_code, 504)
        self.assertEqual(r.json()["error"]["code"], "PROVIDER_TIMEOUT")

    @mock.patch("services.http_client.get_json", side_effect=http_client.ProviderHTTPError("Open-Meteo", "HTTP 429", 429))
    def test_provider_http_error(self, _):
        r = self.c.get("/api/v1/weather/current/", {"lat": 1, "lon": 1})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["error"]["details"]["upstream_status"], 429)

    @mock.patch("services.http_client.get_json", return_value={"unexpected": True})
    def test_bad_provider_json(self, _):
        self.assertEqual(self.c.get("/api/v1/weather/current/", {"lat": 2, "lon": 2}).status_code, 502)

    @mock.patch("services.http_client.get_json", return_value=POWER)
    def test_historical_fill_value_becomes_null(self, m):
        r = self.c.get("/api/v1/weather/historical/", {"lat": 1, "lon": 1, "start": "2026-01-01", "end": "2026-01-02"})
        self.assertEqual(r.status_code, 200, r.content)
        b = r.json()
        self.assertEqual(b["data"]["dates"], ["2026-01-01", "2026-01-02"])
        self.assertEqual(b["data"]["series"]["T2M"], [-14.86, None])  # -999 is missing, never a temperature
        self.assertEqual(b["units"]["PRECTOTCORR"], "mm/day")
        self.assertEqual(b["data_type"], "historical_reanalysis")
        self.assertEqual(m.call_args[0][2]["start"], "20260101")

    def test_historical_date_validation(self):
        bad = [
            {"start": "2026-02-01", "end": "2026-01-01"},
            {"start": "1970-01-01", "end": "1970-01-02"},
            {"start": "2024-01-01", "end": "2025-06-01"},
            {"start": "2026-13-01", "end": "2026-01-02"},
            {"start": "2026-01-01", "end": (dt.date.today() + dt.timedelta(days=3)).isoformat()},
        ]
        for q in bad:
            self.assertEqual(self.c.get("/api/v1/weather/historical/", {"lat": 1, "lon": 1, **q}).status_code, 400, q)

    def test_status(self):
        b = self.c.get("/api/v1/weather/status/").json()
        self.assertIn("Open-Meteo", b["providers"])
        self.assertIn("non-commercial", b["terms"]["Open-Meteo"])


class GeocodingTests(TestCase):
    def setUp(self):
        cache.clear()

    @mock.patch("services.http_client.get_json", return_value=[
        {"display_name": "Jezero, Montenegro", "lat": "42.1", "lon": "19.2", "category": "place", "type": "village", "boundingbox": ["42.0", "42.2", "19.1", "19.3"]},
        {"display_name": "broken"},
    ])
    def test_search_normalized_and_cached(self, m):
        c = APIClient()
        b = c.get("/api/v1/geocoding/search/", {"q": "Jezero"}).json()
        self.assertEqual(len(b["results"]), 1)
        self.assertEqual(b["results"][0]["bbox"]["west"], 19.1)
        self.assertIn("OpenStreetMap", b["attribution"])
        b2 = c.get("/api/v1/geocoding/search/", {"q": "jezero"}).json()
        self.assertTrue(b2["from_cache"])
        self.assertEqual(m.call_count, 1)
        self.assertEqual(m.call_args[0][2]["format"], "jsonv2")

    def test_query_validation(self):
        self.assertEqual(APIClient().get("/api/v1/geocoding/search/", {"q": "a"}).status_code, 400)

    @mock.patch("services.http_client.get_json", side_effect=http_client.ProviderError("Nominatim", "unreachable"))
    def test_provider_down(self, _):
        self.assertEqual(APIClient().get("/api/v1/geocoding/search/", {"q": "Paris"}).status_code, 502)


CAPS = b"""<?xml version="1.0"?>
<Capabilities xmlns="http://www.opengis.net/wmts/1.0" xmlns:ows="http://www.opengis.net/ows/1.1"><Contents>
<Layer><ows:Identifier>IMERG_Precipitation_Rate</ows:Identifier><Format>image/png</Format>
 <Dimension><ows:Identifier>Time</ows:Identifier><Default>2026-11-12</Default>
  <Value>2000-06-01/2025-10-22/P1D</Value><Value>2026-05-27/2026-11-12/P1D</Value></Dimension>
 <TileMatrixSetLink><TileMatrixSet>GoogleMapsCompatible_Level6</TileMatrixSet></TileMatrixSetLink>
 <ResourceURL format="image/png" resourceType="tile" template="https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/IMERG_Precipitation_Rate/default/{Time}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.png"/></Layer>
<Layer><ows:Identifier>BlueMarble_NextGeneration</ows:Identifier><Format>image/jpeg</Format>
 <TileMatrixSetLink><TileMatrixSet>GoogleMapsCompatible_Level8</TileMatrixSet></TileMatrixSetLink>
 <ResourceURL format="image/jpeg" resourceType="tile" template="https://x/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.jpeg"/></Layer>
<Layer><ows:Identifier>Unrelated_Layer</ows:Identifier><Format>image/png</Format>
 <TileMatrixSetLink><TileMatrixSet>GoogleMapsCompatible_Level6</TileMatrixSet></TileMatrixSetLink></Layer>
</Contents></Capabilities>"""


class GibsTests(SimpleTestCase):
    def test_parse_keeps_published_time_domain(self):
        caps = gibs.parse_capabilities(CAPS)
        self.assertEqual(set(caps), {"IMERG_Precipitation_Rate", "BlueMarble_NextGeneration"})
        t = caps["IMERG_Precipitation_Rate"]["time"]
        self.assertEqual(t["latest"], "2026-11-12")  # not "today"
        self.assertEqual(len(t["intervals"]), 2)  # gap preserved
        self.assertTrue(t["daily"])
        self.assertIsNone(caps["BlueMarble_NextGeneration"]["time"])
        self.assertEqual(caps["IMERG_Precipitation_Rate"]["max_zoom"], 6)
        self.assertAlmostEqual(caps["IMERG_Precipitation_Rate"]["pixel_size_at_equator_m"], 2445.98, delta=0.1)

    def test_discover_marks_missing_layers(self):
        with mock.patch.object(gibs, "_load_caps_bytes", return_value=(CAPS, 0.0)):
            out = gibs.discover(refresh=True)
        status = {l["id"]: l["status"] for l in out["layers"]}
        self.assertEqual(status["IMERG_Precipitation_Rate"], "AVAILABLE")
        self.assertEqual(status["MODIS_Terra_CorrectedReflectance_TrueColor"], "NOT_IN_CAPABILITIES")
        gibs._parsed["layers"] = None  # do not leak the fake caps into other tests


class SourceHealthTests(TestCase):
    def test_down_sources_reported_and_nominatim_not_probed(self):
        cache.clear()
        with mock.patch("services.http_client.get_bytes", side_effect=http_client.ProviderTimeout("x", "timeout")):
            b = APIClient().get("/api/v1/health/sources/", {"refresh": "1"}).json()
        self.assertEqual(b["sources"]["Open-Meteo"]["status"], "DOWN")
        self.assertEqual(b["sources"]["Nominatim"]["status"], "NOT_PROBED")
        cache.clear()
