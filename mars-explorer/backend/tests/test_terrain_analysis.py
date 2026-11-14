import math

import numpy as np
from django.test import SimpleTestCase
from pyproj import CRS

from services import terrain_analysis as ta


class HornSlopeTests(SimpleTestCase):
    def test_flat_surface(self):
        r = ta.horn_slope_aspect(np.full((3, 3), 1200.0), 100.0, 100.0)
        self.assertEqual(r.slope_deg, 0.0)
        self.assertIsNone(r.aspect_deg)

    def test_plane_rising_to_east_faces_west(self):
        # z increases by 100 m per 100 m eastwards -> 45 deg slope, downslope to the west (270).
        cols = np.arange(3) * 100.0
        z = np.tile(cols, (3, 1))
        r = ta.horn_slope_aspect(z, 100.0, 100.0)
        self.assertAlmostEqual(r.slope_deg, 45.0, places=9)
        self.assertAlmostEqual(r.aspect_deg, 270.0, places=9)

    def test_plane_rising_to_north_faces_south(self):
        # Row 0 is north. 10 m per 50 m northwards -> atan(0.2).
        rows = np.array([[20.0], [10.0], [0.0]])
        z = np.tile(rows, (1, 3))
        r = ta.horn_slope_aspect(z, 30.0, 50.0)
        self.assertAlmostEqual(r.slope_deg, math.degrees(math.atan(0.2)), places=9)
        self.assertAlmostEqual(r.aspect_deg, 180.0, places=9)

    def test_anisotropic_cell_size_matters(self):
        z = np.tile(np.arange(3) * 10.0, (3, 1))
        r1 = ta.horn_slope_aspect(z, 10.0, 10.0)
        r2 = ta.horn_slope_aspect(z, 20.0, 10.0)
        self.assertAlmostEqual(r1.slope_deg, 45.0)
        self.assertAlmostEqual(r2.slope_deg, math.degrees(math.atan(0.5)))

    def test_nodata_gives_no_slope(self):
        z = np.zeros((3, 3))
        z[0, 0] = np.nan
        self.assertIsNone(ta.horn_slope_aspect(z, 1.0, 1.0).slope_deg)
        self.assertAlmostEqual(ta.nodata_fraction(z), 1 / 9)

    def test_wrong_shape(self):
        with self.assertRaises(ValueError):
            ta.horn_slope_aspect(np.zeros((5, 5)), 1.0, 1.0)


class CellSizeTests(SimpleTestCase):
    def test_sphere_equator(self):
        cs = ta.cell_size_m(1.0, 1.0, CRS("ESRI:104971"), 0.0)
        expected = math.radians(1.0) * 3396190.0
        self.assertAlmostEqual(cs.dx_m, expected, places=6)
        self.assertAlmostEqual(cs.dy_m, expected, places=6)

    def test_sphere_east_west_shrinks_with_cos_latitude(self):
        cs = ta.cell_size_m(1.0, 1.0, CRS("ESRI:104971"), 60.0)
        self.assertAlmostEqual(cs.dx_m, math.radians(1.0) * 3396190.0 * 0.5, places=6)
        self.assertAlmostEqual(cs.dy_m, math.radians(1.0) * 3396190.0, places=6)

    def test_ellipsoid_meridional_radius_smaller_at_equator(self):
        cs = ta.cell_size_m(1.0, 1.0, CRS("ESRI:104905"), 0.0)
        a, b = 3396190.0, 3376200.0
        self.assertAlmostEqual(cs.dx_m, math.radians(1.0) * a, places=3)
        self.assertAlmostEqual(cs.dy_m, math.radians(1.0) * b * b / a, delta=0.01)

    def test_geographic_requires_latitude(self):
        with self.assertRaises(ValueError):
            ta.cell_size_m(1.0, 1.0, CRS("ESRI:104971"))


class RoughnessTests(SimpleTestCase):
    def test_tri_known_value(self):
        z = np.zeros((3, 3))
        z[0, 0] = 3.0
        z[2, 2] = 4.0
        self.assertAlmostEqual(ta.terrain_ruggedness_index(z), 5.0)

    def test_elevation_difference(self):
        self.assertEqual(ta.elevation_difference(-2500.0, -2400.0), 100.0)
        self.assertIsNone(ta.elevation_difference(None, 1.0))
