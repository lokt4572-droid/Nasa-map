import math

from django.test import SimpleTestCase

from services import mars_coordinates as mc


class EllipsoidConstantsTests(SimpleTestCase):
    def test_polar_radius_matches_iau2000(self):
        # IAU 2000 Mars: a = 3396190 m, b = 3376200 m. rf in ESRI:104905 must reproduce b.
        self.assertAlmostEqual(mc.MARS_POLAR_RADIUS_M, 3_376_200.0, delta=0.01)

    def test_proj_database_definition_matches_constants(self):
        from pyproj import CRS

        crs = CRS("ESRI:104905")
        self.assertEqual(crs.ellipsoid.semi_major_metre, mc.MARS_EQUATORIAL_RADIUS_M)
        self.assertAlmostEqual(crs.ellipsoid.inverse_flattening, mc.MARS_INVERSE_FLATTENING, places=9)


class LongitudeTests(SimpleTestCase):
    def test_normalize_180(self):
        cases = {0.0: 0.0, 180.0: -180.0, 270.0: -90.0, 360.0: 0.0, -190.0: 170.0, 77.45: 77.45}
        for given, expected in cases.items():
            self.assertAlmostEqual(mc.normalize_lon_180(given), expected, places=9, msg=given)

    def test_normalize_360(self):
        self.assertAlmostEqual(mc.normalize_lon_360(-90.0), 270.0)
        self.assertAlmostEqual(mc.normalize_lon_360(77.45), 77.45)

    def test_east_west_roundtrip(self):
        # 77.45 E == 282.55 W
        self.assertAlmostEqual(mc.east_to_west_360(77.45), 282.55, places=9)
        self.assertAlmostEqual(mc.west_360_to_east_180(282.55), 77.45, places=9)

    def test_non_finite_rejected(self):
        with self.assertRaises(ValueError):
            mc.normalize_lon_180(float("nan"))


class LatitudeConversionTests(SimpleTestCase):
    def test_equator_and_poles_unchanged(self):
        for lat in (0.0, 90.0, -90.0):
            self.assertEqual(mc.planetocentric_to_planetographic(lat), lat)
            self.assertEqual(mc.planetographic_to_planetocentric(lat), lat)

    def test_45_degrees_control_point(self):
        # tan(phi_g) = (a/b)^2 tan(phi_c). For phi_c = 45 deg: phi_g = atan((a/b)^2).
        expected = math.degrees(math.atan((3396190.0 / 3376200.0) ** 2))
        self.assertAlmostEqual(mc.planetocentric_to_planetographic(45.0), expected, places=6)
        # The ographic latitude is ~0.34 deg poleward of the ocentric one at 45 deg.
        self.assertAlmostEqual(expected - 45.0, 0.3382, places=3)

    def test_sign_symmetry_and_roundtrip(self):
        for lat in (-80.0, -18.4, 18.4, 60.0, 89.9):
            g = mc.planetocentric_to_planetographic(lat)
            self.assertGreater(abs(g), abs(lat))
            self.assertEqual(math.copysign(1, g), math.copysign(1, lat))
            self.assertAlmostEqual(mc.planetographic_to_planetocentric(g), lat, places=10)

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            mc.planetocentric_to_planetographic(91.0)


class CRSResolutionTests(SimpleTestCase):
    def test_trek_declared_crs_is_reported_as_alias(self):
        crs, alias = mc.resolve_crs(mc.TREK_DECLARED_CRS)
        self.assertIsNotNone(alias)
        self.assertEqual(alias.resolved_as, "ESRI:104905")
        self.assertEqual(crs.ellipsoid.semi_major_metre, 3396190.0)

    def test_epsg_104905_does_not_exist_in_proj(self):
        # Documents why the alias above is needed and must stay explicit.
        with self.assertRaises(mc.UnknownCRSError):
            mc.resolve_crs("EPSG:104905")

    def test_earth_crs_rejected(self):
        with self.assertRaises(mc.UnknownCRSError):
            mc.resolve_crs("EPSG:4326")

    def test_garbage_rejected(self):
        with self.assertRaises(mc.UnknownCRSError):
            mc.resolve_crs("not-a-crs")

    def test_latitude_convention_from_geometry(self):
        from pyproj import CRS

        self.assertEqual(mc.latitude_convention_for_crs(CRS("ESRI:104971")), mc.LatitudeConvention.PLANETOCENTRIC)
        self.assertEqual(mc.latitude_convention_for_crs(CRS("ESRI:104905")), mc.LatitudeConvention.PLANETOGRAPHIC)

    def test_proj_does_not_convert_ocentric_to_ographic(self):
        # Regression guard for a verified PROJ behaviour: between the Mars sphere and the
        # Mars 2000 ellipsoid PROJ applies a null ("ballpark") transformation. Latitude type
        # conversion therefore MUST be done explicitly by adapt_latitude().
        from pyproj import CRS

        _, lat = mc.transform_point(10.0, 45.0, CRS("ESRI:104971"), CRS("ESRI:104905"))
        self.assertAlmostEqual(lat, 45.0, places=9)


class AdaptLatitudeTests(SimpleTestCase):
    def test_same_convention(self):
        self.assertEqual(mc.adapt_latitude(30.0, "PLANETOCENTRIC", "PLANETOCENTRIC"), (30.0, "NONE"))

    def test_explicit_conversion(self):
        lat, status = mc.adapt_latitude(45.0, "PLANETOCENTRIC", "PLANETOGRAPHIC")
        self.assertEqual(status, "CONVERTED_PLANETOCENTRIC_TO_PLANETOGRAPHIC")
        self.assertAlmostEqual(lat, mc.planetocentric_to_planetographic(45.0))

    def test_unknown_source_is_flagged_not_converted(self):
        self.assertEqual(mc.adapt_latitude(18.4, "AS_DECLARED_BY_SOURCE", "PLANETOCENTRIC"), (18.4, "NOT_VERIFIED"))


class GeodesicTests(SimpleTestCase):
    def test_quarter_equator(self):
        # Along the equator the geodesic is an arc of radius a: a * pi / 2.
        d = mc.geodesic_distance_m(0.0, 0.0, 90.0, 0.0)
        self.assertAlmostEqual(d, 3396190.0 * math.pi / 2, delta=0.01)

    def test_one_degree_of_latitude_at_equator(self):
        # M(0) = a (1 - e^2); 1 deg of latitude ~ M(0) * pi/180 near the equator.
        d = mc.geodesic_distance_m(0.0, -0.5, 0.0, 0.5)
        m0 = mc.meridional_radius_m(0.0)
        self.assertAlmostEqual(d, m0 * math.pi / 180.0, delta=5.0)
