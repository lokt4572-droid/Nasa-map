"""v0.2 importer checks: vertical datum, radius guard, planet/CRS match, valid values,
control points, PDS label parsing, and an opt-in test on the real NASA MOLA file."""
from io import StringIO
from pathlib import Path

import numpy as np
from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.datasets.models import Dataset
from services.dataset_manager import label_statements

from .raster_fixtures import TempDirMixin, requires_raster, write_geotiff

WEST, NORTH, PIX = 77.30, 18.50, 0.01
REAL_MOLA = Path(settings.MARS_DATA_DIR) / "raw" / "mola" / "megt90n000cb.xml"


def run(path, *args, **kw):
    out, err = StringIO(), StringIO()
    call_command("import_dem", "--file", str(path), *args, stdout=out, stderr=err, **kw)
    return out.getvalue(), err.getvalue()


def ramp():
    r, c = np.mgrid[0:10, 0:10]
    return (1000.0 + 10.0 * r + c).astype("float32")


class LabelParsingTests(SimpleTestCase):
    def test_mola_label_sentence_across_line_breaks(self):
        text = "<description>Topography is the planetary radius minus the\n   areoid radius at a given longitude. Map uses areoid defined by the Goddard Mars potential model GMM3 (mgm1025) evaluated.</description>"
        stmts, hint = label_statements(text)
        self.assertEqual(hint, "MOLA areoid (GMM3 (mgm1025))")
        self.assertTrue(any("radius minus the areoid" in s for s in stmts))

    def test_no_label(self):
        self.assertEqual(label_statements(None), ([], None))

    def test_radius_product_gives_no_datum_hint(self):
        _, hint = label_statements("Radius is the distance from the center of mass of the planet.")
        self.assertIsNone(hint)


@requires_raster
class ImporterV02Tests(TempDirMixin, TestCase):
    def test_missing_vertical_datum_is_an_error(self):
        p = write_geotiff(self.tmp / "d.tif", ramp(), west=WEST, north=NORTH, pixel_deg=PIX)
        with self.assertRaisesMessage(CommandError, "Vertical datum is unknown"):
            run(p, "--name", "x")
        self.assertFalse(Dataset.objects.exists())

    def test_radius_values_are_rejected(self):
        radius = (3_396_000.0 + ramp()).astype("float64")
        p = write_geotiff(self.tmp / "r.tif", radius, west=WEST, north=NORTH, pixel_deg=PIX)
        with self.assertRaisesMessage(CommandError, "looks like planetary radius"):
            run(p, "--name", "x", "--vertical-datum", "none")

    def test_all_nodata_rejected(self):
        p = write_geotiff(self.tmp / "n.tif", np.full((10, 10), -9999.0, "float32"), west=WEST, north=NORTH, pixel_deg=PIX)
        with self.assertRaisesMessage(CommandError, "no valid values"):
            run(p, "--name", "x", "--vertical-datum", "d")

    def test_mars_dem_cannot_be_registered_as_moon(self):
        p = write_geotiff(self.tmp / "m.tif", ramp(), west=WEST, north=NORTH, pixel_deg=PIX)
        with self.assertRaisesMessage(CommandError, "does not describe Moon"):
            run(p, "--name", "x", "--vertical-datum", "d", "--planet", "MOON")

    def test_moon_dem_registers_for_moon(self):
        p = write_geotiff(self.tmp / "moon.tif", ramp(), west=10, north=10, pixel_deg=0.1, crs="ESRI:104903")
        run(p, "--name", "moon-test", "--vertical-datum", "d", "--planet", "MOON")
        ds = Dataset.objects.get(name="moon-test")
        self.assertEqual(ds.planet, "MOON")
        # Earth/Mars point queries must not see a lunar DEM.
        r = APIClient().get("/api/v1/terrain/coverage/", {"lon": 10.05, "lat": 9.95, "crs": "ESRI:104971"})
        self.assertEqual(r.json()["datasets"], [])

    def test_report_steps_and_control_points_stored(self):
        p = write_geotiff(self.tmp / "d.tif", ramp(), west=WEST, north=NORTH, pixel_deg=PIX)
        out, _ = run(p, "--name", "steps", "--vertical-datum", "test datum")
        self.assertIn("CHECK_VERTICAL_DATUM", out)
        ds = Dataset.objects.get(name="steps")
        steps = {s["step"]: s["status"] for s in ds.metadata["import_steps"]}
        self.assertEqual(steps["READY"], "OK")
        self.assertEqual(steps["CHECK_VALUES"], "OK")
        cp = ds.metadata["control_points"]
        self.assertEqual(len(cp), 5)
        # centre cell (5,5) of the ramp = 1000 + 50 + 5
        self.assertEqual(cp[0]["value"], 1055.0)
        self.assertEqual(ds.metadata["statistics"]["valid_fraction"], 1.0)


@requires_raster
class RealMolaTests(TestCase):
    """Uses the real NASA PDS file if present in data/mars/raw/mola (not shipped in Git)."""

    def setUp(self):
        if not REAL_MOLA.is_file():
            self.skipTest("real MOLA MEGDR megt90n000cb not downloaded (see data/mars/README.md)")

    def test_real_import_and_sample(self):
        out, _ = run(REAL_MOLA, "--name", "mola-global", "--no-checksum")
        self.assertIn("MOLA areoid", out)
        ds = Dataset.objects.get(name="mola-global")
        self.assertEqual(ds.driver, "PDS4")
        self.assertEqual((ds.width, ds.height), (1440, 720))
        self.assertEqual(ds.latitude_convention, "PLANETOCENTRIC")
        self.assertAlmostEqual(ds.resolution_meters, 14817.845349, places=3)
        # Cross-check the API against a direct GDAL read of the same cell.
        import rasterio

        r = APIClient().get(
            "/api/v1/terrain/sample/",
            {"lon": 77.45, "lat": 18.44, "crs": "ESRI:104971", "lat_convention": "PLANETOCENTRIC"},
        ).json()
        with rasterio.open(REAL_MOLA) as src:
            direct = float(src.read(1)[r["pixel"]["row"], r["pixel"]["col"]])
        self.assertEqual(r["elevation_m"], direct)
        self.assertEqual(r["latitude_handling"]["status"], "NONE")
        # Jezero crater floor lies well below the areoid.
        self.assertLess(r["elevation_m"], -1500)
