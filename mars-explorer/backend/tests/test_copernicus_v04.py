"""Earth elevation via Copernicus DEM GLO-30 (tile-list adapter). MOCKED: the tile list is a
fixture and the "remote" COG is a local synthetic EPSG:4326 raster. Not a check of the live bucket."""
from contextlib import contextmanager
from unittest import mock

import numpy as np
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.datasets.services import catalogues, copernicus_client as cop, dataset_discovery
from services import remote_raster, terrain_patch

from .raster_fixtures import TempDirMixin, requires_raster, write_geotiff

ALPS = "Copernicus_DSM_COG_10_N46_00_E007_00_DEM"
ANDES = "Copernicus_DSM_COG_10_S33_00_W070_00_DEM"
TILES = frozenset({ALPS, ANDES, "Copernicus_DSM_COG_10_N46_00_E008_00_DEM"})


class TileSchemeTests(SimpleTestCase):
    def test_tile_names_follow_the_published_scheme(self):
        self.assertEqual(cop.tile_id(7.5, 46.5), ALPS)
        self.assertEqual(cop.tile_id(-69.9, -32.1), ANDES)
        self.assertEqual(cop.tile_id(367.5, 46.5), ALPS)  # 0..360 longitudes accepted
        self.assertEqual(cop.tile_id(7.0, 46.0), ALPS)  # tile edges belong to the tile to the north-east
        self.assertIsNone(cop.tile_id(0, 90))
        self.assertEqual(cop.tile_bounds(ANDES), (-70.0, -33.0, -69.0, -32.0))

    def test_search_uses_the_tile_list_and_never_invents_ocean_tiles(self):
        with mock.patch.object(cop, "tile_list", return_value=TILES):
            r = catalogues.search("EARTH", point=(7.5, 46.5), data_type="DEM")
            self.assertEqual([p["product_id"] for p in r["products"]], [ALPS])
            p = r["products"][0]
            self.assertEqual((p["planet_id"], p["latitude_type"], p["effective_accuracy"]), ("EARTH", "PLANETOGRAPHIC", "NOT_DOCUMENTED"))
            self.assertIn("EGM2008", p["vertical_datum"])
            self.assertIn("SURFACE", p["quality"]["note"])
            self.assertTrue(p["assets"]["dem"].startswith("https://copernicus-dem-30m.s3.amazonaws.com/"))
            self.assertEqual(catalogues.search("EARTH", point=(-30.5, 0.5))["products"], [])  # mid-Atlantic: no tile
            self.assertEqual(len(catalogues.search("EARTH", bbox=(6.5, 45.5, 9.5, 47.5))["products"]), 2)
            with self.assertRaises(catalogues.StacError):
                catalogues.search("EARTH", bbox=(-180, -90, 180, 90))  # too many cells
            self.assertEqual(catalogues.get_product("copernicus_dem_glo30", ALPS)["product_id"], ALPS)
            with self.assertRaises(catalogues.StacError):
                catalogues.get_product("copernicus_dem_glo30", "Copernicus_DSM_COG_10_N00_00_W030_00_DEM")
        self.assertEqual(catalogues.provider_name("EARTH"), cop.PROVIDER)
        self.assertEqual([c.id for c in catalogues.collections_for("EARTH")], ["copernicus_dem_glo30"])
        self.assertEqual(catalogues.collections_for("EARTH", "ORTHOIMAGE"), [])

    def test_host_is_allow_listed(self):
        self.assertTrue(remote_raster.file_available(cop.record(ALPS)["assets"]["dem"]))


@requires_raster
class EarthRemoteDemTests(TempDirMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        r, c = np.mgrid[0:360, 0:360]
        self.z = (1000.0 + 2.0 * r + c).astype("float32")  # synthetic, 10 arc-second cells over N46 E007
        self.local = write_geotiff(self.tmp / "cop.tif", self.z, west=7.0, north=47.0, pixel_deg=1 / 360, crs="EPSG:4326",
                                   nodata=None, units=None)  # like the real files: no nodata, no unit tag
        real_open = remote_raster.open_raster
        url = cop.record(ALPS)["assets"]["dem"]

        @contextmanager
        def opener(path):
            with real_open(self.local if str(path) == url else path) as src:
                yield src

        for p in (mock.patch.object(remote_raster, "open_raster", opener), mock.patch.object(cop, "tile_list", return_value=TILES)):
            p.start()
            self.addCleanup(p.stop)

    def test_register_validates_with_documented_units_and_datum(self):
        ds = dataset_discovery.register_remote_dem(cop.record(ALPS))
        self.assertEqual((ds.planet, ds.status, ds.units, ds.access), ("EARTH", "VALID", "m", "REMOTE_COG"))
        self.assertIn("EGM2008", ds.vertical_datum)
        self.assertEqual(ds.latitude_convention, "PLANETOGRAPHIC")  # geodetic on WGS 84

    def test_earth_local_terrain_patch_from_copernicus(self):
        r = APIClient().get("/api/v1/terrain/patch/", {"planet": "EARTH", "lon": 7.5, "lat": 46.5, "source": "auto", "max_dimension": 16})
        self.assertEqual(r.status_code, 200, r.content)
        b = r.json()
        self.assertEqual(b["dataset"]["product_id"], ALPS)
        z = terrain_patch.decode_elevation(b["elevation"], b["width"], b["height"])
        self.assertTrue(np.isin(z, self.z).all())

    def test_ocean_point_has_no_elevation(self):
        r = APIClient().get("/api/v1/terrain/patch/", {"planet": "EARTH", "lon": -30.5, "lat": 0.5, "source": "auto"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"]["code"], "DEM_NOT_AVAILABLE")

    def test_earth_coverage_endpoint_lists_the_catalogue(self):
        b = APIClient().get("/api/v1/coverage/EARTH/").json()
        self.assertEqual(b["catalogues"][0]["collection"], "copernicus_dem_glo30")
        r = APIClient().get("/api/v1/datasets/search/", {"planet": "EARTH", "bbox": "6.5,45.5,9.5,47.5"}).json()
        self.assertEqual(r["count"], 2)
