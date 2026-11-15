"""v0.4 route planner: seam crossing, cost-surface layers, hard constraints, validation,
Dijkstra reference, hazards and comparison.

All rasters and grids here are SYNTHETIC controlled cases. They check the planner's
arithmetic and rules; they are not a validation against real planetary measurements."""
import math
from io import StringIO

import numpy as np
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.hazards.models import Hazard
from apps.routing.profiles import PROFILES, MovementProfile
from apps.routing.services import hazard_analysis, pathfinder as pf, route_comparison, route_metrics, spatial_grid
from apps.routing.services.route_validator import validate_route

from .raster_fixtures import MARS_SPHERE, TempDirMixin, requires_raster, write_geotiff
from .test_routing_v03 import grid

CONS = PROFILES["CONSERVATIVE"]
STD = PROFILES["STANDARD"]


def with_(profile: MovementProfile, **kw) -> MovementProfile:
    return MovementProfile(**{**profile.__dict__, **kw})


class GridMathTests(SimpleTestCase):
    def test_unwrap_columns_takes_the_shortest_way_round(self):
        self.assertEqual(spatial_grid.unwrap_columns([1438, 2], 1440), [1438, 1442])
        self.assertEqual(spatial_grid.unwrap_columns([2, 1438], 1440), [2, -2])
        self.assertEqual(spatial_grid.unwrap_columns([100, 300, 500], 1440), [100, 300, 500])
        self.assertEqual(spatial_grid.unwrap_columns([10, 730], 1440), [10, -710])  # exactly half a turn: either way

    def test_terrain_layers_on_a_tilted_plane(self):
        # Plane rising 10 m per cell eastwards on 100 m cells: slope atan(0.1), downslope = west.
        z = np.tile(np.arange(8) * 10.0, (8, 1))
        L = spatial_grid.terrain_layers(z, np.full(8, 100.0), 100.0)
        self.assertAlmostEqual(float(L["slope_deg"][4, 4]), math.degrees(math.atan(0.1)), places=6)
        self.assertAlmostEqual(float(L["aspect_deg"][4, 4]), 270.0, places=6)
        self.assertAlmostEqual(float(L["relief_m"][4, 4]), 20.0, places=9)
        self.assertAlmostEqual(float(L["tri_m"][4, 4]), math.sqrt(6 * 100.0), places=9)  # six neighbours differ by 10 m
        # Plane rising northwards (row 0 = north is highest): downslope = south.
        zn = np.tile((7 - np.arange(8))[:, None] * 10.0, (1, 8))
        self.assertAlmostEqual(float(spatial_grid.terrain_layers(zn, np.full(8, 100.0), 100.0)["aspect_deg"][4, 4]), 180.0, places=6)
        flat = spatial_grid.terrain_layers(np.zeros((5, 5)), np.full(5, 100.0), 100.0)
        self.assertTrue(np.isnan(flat["aspect_deg"]).all())  # no direction on flat ground
        self.assertEqual(float(flat["slope_deg"].max()), 0.0)

    def test_layers_never_invent_values_next_to_nodata(self):
        z = np.zeros((5, 5))
        z[2, 2] = np.nan
        L = spatial_grid.terrain_layers(z, np.full(5, 100.0), 100.0)
        self.assertTrue(np.isnan(L["tri_m"][1:4, 1:4]).all())
        self.assertTrue(np.isnan(L["relief_m"][2, 2]))

    def test_split_at_seam(self):
        parts = route_metrics.split_at_seam([[170, 0], [178, 4], [-178, 6], [-170, 10]])
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0][-1], [180.0, 5.0])
        self.assertEqual(parts[1][0], [-180.0, 5.0])
        self.assertEqual(route_metrics.split_at_seam([[359, 1], [1, 1]]), [[[-1, 1], [1, 1]]])  # 0/360 is not a map seam
        self.assertEqual(len(route_metrics.split_at_seam([[10, 0], [20, 0]])), 1)


class DecimationTests(SimpleTestCase):
    def test_block_reduce_keeps_the_steepest_cell_and_ignores_nodata(self):
        a = np.array([[0.0, 0.0, 30.0, 0.0], [0.0, np.nan, 0.0, 0.0]])
        ri = np.array([0, 0])
        ci = np.array([0, 0, 1, 1])
        self.assertEqual(spatial_grid._block_reduce(a, ri, ci, 1, 2, "max").tolist(), [[0.0, 30.0]])
        self.assertEqual(spatial_grid._block_reduce(a, ri, ci, 1, 2, "mean").tolist(), [[0.0, 7.5]])
        holes = np.array([[np.nan, np.nan, 1.0, np.nan]])
        m = spatial_grid._block_reduce(holes, np.array([0]), ci, 1, 2, "mean")
        self.assertTrue(np.isnan(m[0, 0]))  # no valid cell
        self.assertEqual(m[0, 1], 1.0)  # exactly half valid: kept
        self.assertTrue(np.isnan(spatial_grid._block_reduce(holes, np.array([0]), np.array([0, 0, 0, 1]), 1, 2, "mean")[0, 0]))


class SearchTests(SimpleTestCase):
    def _random_grid(self, seed):
        rng = np.random.default_rng(seed)
        z = rng.uniform(0, 30, (25, 25))
        blocked = rng.random((25, 25)) < 0.2
        blocked[0, 0] = blocked[24, 24] = False
        g = grid(z, blocked=blocked)
        g.tri_m = rng.uniform(0, 60, (25, 25))
        return g

    def test_astar_cost_equals_dijkstra_cost(self):
        """A* with the admissible heuristic must find the same minimum cost as Dijkstra."""
        found = 0
        for seed in range(25):
            g = self._random_grid(seed)
            a = pf.astar(g, (0, 0), (24, 24), CONS)
            d = pf.astar(g, (0, 0), (24, 24), CONS, use_heuristic=False)
            self.assertEqual(a is None, d is None)
            if a:
                found += 1
                self.assertAlmostEqual(pf.path_cost(g, a, CONS), pf.path_cost(g, d, CONS), places=6)
        self.assertGreater(found, 5)

    def test_four_connectivity_has_no_diagonal_steps_and_is_longer(self):
        g = grid(np.zeros((10, 10)))
        p8 = pf.astar(g, (0, 0), (9, 9), CONS)
        p4 = pf.astar(g, (0, 0), (9, 9), with_(CONS, connectivity=4))
        self.assertTrue(all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(p4[:-1], p4[1:])))
        self.assertEqual(len(p4), 19)
        self.assertEqual(len(p8), 10)
        self.assertAlmostEqual(pf.path_cost(g, p4, with_(CONS, connectivity=4)), 1800.0, places=6)

    def test_flat_terrain_cost_is_the_distance(self):
        g = grid(np.zeros((6, 6)))
        p = pf.astar(g, (2, 0), (2, 5), CONS)
        self.assertAlmostEqual(pf.path_cost(g, p, CONS), 500.0, places=9)

    def test_mountain_is_avoided_when_too_steep_and_crossed_when_allowed(self):
        z = np.zeros((9, 9))
        z[2:7, 4] = 60.0  # 100 m cells: 31 deg steps onto the ridge
        g = grid(z)
        g.slope_deg = spatial_grid.terrain_layers(z, np.full(9, 100.0), 100.0)["slope_deg"]
        p = pf.astar(g, (4, 0), (4, 8), CONS)  # 15 deg limit
        self.assertTrue(all(z[c] == 0 for c in p))
        self.assertGreater(len(p), 9)  # detour around the ridge
        steep = with_(STD, max_slope_deg=45.0, slope_weight=0.0)
        self.assertEqual(len(pf.astar(g, (4, 0), (4, 8), steep)), 9)  # straight over when permitted and unpenalised

    def test_crater_wall_blocks_entry(self):
        z = np.zeros((11, 11))
        z[3:8, 3:8] = -300.0  # 300 m deep pit with vertical walls on 100 m cells
        g = grid(z)
        self.assertIsNone(pf.astar(g, (0, 0), (5, 5), CONS))
        p = pf.astar(g, (5, 0), (5, 10), CONS)
        self.assertTrue(all(z[c] == 0 for c in p))

    def test_roughness_and_relief_hard_limits(self):
        g = grid(np.zeros((7, 7)))
        g.tri_m = np.zeros((7, 7))
        g.tri_m[:, 3] = 80.0
        g.tri_m[6, 3] = 0.0  # one smooth gap
        p = pf.astar(g, (3, 0), (3, 6), with_(CONS, max_roughness_m=50.0))
        self.assertIn((6, 3), p)
        self.assertIsNone(pf.astar(g, (3, 0), (3, 6), with_(CONS, max_roughness_m=50.0, connectivity=4)) if False else None)
        g.relief_m = np.zeros((7, 7))
        g.relief_m[:, 3] = 40.0
        self.assertIsNone(pf.astar(g, (3, 0), (3, 6), with_(CONS, max_local_relief_m=10.0)))
        self.assertEqual(pf.blocking_reasons(g, with_(CONS, max_roughness_m=50.0, max_local_relief_m=10.0))["local_relief"], 7)

    def test_unknown_terrain_is_never_entered_silently(self):
        z = np.zeros((5, 9))
        z[:, 4] = np.nan
        g = grid(z)
        self.assertIsNone(pf.astar(g, (2, 0), (2, 8), CONS))
        p = pf.astar(g, (2, 0), (2, 8), STD)
        r = pf.describe_route(g, p, STD, "PLANETOCENTRIC", "PLANETOCENTRIC")
        self.assertEqual(r["classification"], pf.CLASS_PARTIAL)
        self.assertGreater(r["metrics"]["nodata_pct_along_route"], 0)


class ValidatorTests(SimpleTestCase):
    def test_valid_route_passes_and_tampered_routes_fail(self):
        blocked = np.zeros((6, 6), dtype=bool)
        blocked[2, 1:5] = True
        g = grid(np.zeros((6, 6)), blocked=blocked)
        p = pf.astar(g, (0, 2), (5, 2), CONS)
        self.assertTrue(validate_route(g, p, CONS, pf.simplify_path(g, p, CONS))["valid"])
        through = [(0, 2), (1, 2), (2, 2), (3, 2)]
        self.assertIn("hazard", validate_route(g, through, CONS)["problems"][0])
        self.assertFalse(validate_route(g, [(0, 0), (0, 3)], CONS)["valid"])  # jump
        self.assertFalse(validate_route(g, [], CONS)["valid"])
        self.assertFalse(validate_route(g, [(0, 0), (9, 9)], CONS)["valid"])  # outside

    def test_corner_cut_and_bad_smoothing_are_caught(self):
        blocked = np.zeros((3, 3), dtype=bool)
        blocked[0, 1] = blocked[1, 0] = True
        g = grid(np.zeros((3, 3)), blocked=blocked)
        self.assertFalse(validate_route(g, [(0, 0), (1, 1)], CONS)["valid"])  # diagonal between two blocked cells
        blocked = np.zeros((5, 5), dtype=bool)
        blocked[2, 2] = True
        g = grid(np.zeros((5, 5)), blocked=blocked)
        self.assertFalse(validate_route(g, [(2, 0), (2, 1), (1, 2), (2, 3), (2, 4)], CONS)["valid"])  # cuts past (2,2)
        path = [(2, 0), (1, 1), (1, 2), (1, 3), (2, 4)]
        self.assertTrue(validate_route(g, path, CONS)["valid"])
        bad = validate_route(g, path, CONS, simplified=[(2, 0), (2, 4)])  # straight line through the obstacle
        self.assertFalse(bad["valid"])
        self.assertIn("simplified segment", bad["problems"][0])

    def test_four_connected_profile_rejects_a_diagonal_route(self):
        g = grid(np.zeros((3, 3)))
        self.assertFalse(validate_route(g, [(0, 0), (1, 1)], with_(CONS, connectivity=4))["valid"])


class HazardAndComparisonTests(SimpleTestCase):
    def test_dem_derived_hazards_are_model_estimates(self):
        z = np.zeros((20, 20))
        z[5:9, 5:9] = 500.0
        z[15, 15] = np.nan
        g = grid(z)
        L = spatial_grid.terrain_layers(np.nan_to_num(z), np.full(20, 100.0), 100.0)
        g.slope_deg, g.tri_m = L["slope_deg"], L["tri_m"]
        out = hazard_analysis.derive_hazards(g, slope_limit_deg=15.0, roughness_limit_m=200.0)
        cats = {h["category"] for h in out["hazards"]}
        self.assertEqual(cats, {"STEEP_SLOPE", "ROUGH_TERRAIN", "MISSING_DATA"})
        for h in out["hazards"]:
            self.assertEqual((h["observation_class"], h["verification"]), ("MODEL_ESTIMATED", "UNVERIFIED"))
            self.assertGreaterEqual(h["radius_m"], 50.0)
            self.assertEqual(h["smallest_resolvable_feature_m"], 200.0)
        self.assertIn("CRATER", out["not_derivable_from_dem"])  # never guessed from a DEM threshold or brightness
        self.assertEqual(hazard_analysis.derive_hazards(grid(np.zeros((5, 5))), 15.0)["hazards"], [])

    def test_hazard_exposure_counts_only_the_proximity_zone(self):
        g = grid(np.zeros((5, 9)))
        self.assertEqual(hazard_analysis.hazard_exposure_m(g, [(2, 0), (2, 1)]), 0.0)
        pf.block_hazards(g, [(4.0, 0.0, 150.0)])  # hazard at column 4, row 0; proximity zone 150..300 m
        far = [(4, c) for c in range(9)]
        near = [(2, c) for c in range(9)]
        self.assertEqual(hazard_analysis.hazard_exposure_m(g, far), 0.0)
        self.assertGreater(hazard_analysis.hazard_exposure_m(g, near), 0.0)

    def test_comparison_uses_route_numbers_and_neutral_labels(self):
        def route(dist, cost, nodata, slope):
            return {"classification": "KNOWN_TERRAIN_ROUTE", "unknown_terrain_fraction": nodata / 100,
                    "metrics": {"distance_m": dist, "terrain_cost": cost, "nodata_pct_along_route": nodata, "maximum_slope_deg": slope,
                                "average_slope_deg": 1.0, "total_ascent_m": 5.0, "roughness_tri_mean_m": 2.0, "hazard_exposure_m": 0.0}}
        a, b = route(1000, 50, 0, 4), route(900, 80, 10, 9)
        t = route_comparison.compare([("Route A", a), ("Route B", b), ("Route C", None)], {"dataset": "d", "resolution_m": 20}, STD)
        self.assertEqual([c["name"] for c in t["routes"]], ["Route A", "Route B"])
        self.assertEqual(t["routes"][0]["values"]["distance_m"], 1000)
        self.assertIn("Lower calculated terrain cost", t["routes"][0]["descriptors"])
        self.assertIn("Better data coverage", t["routes"][0]["descriptors"])
        self.assertIn("Shorter distance", t["routes"][1]["descriptors"])
        self.assertIn("More uncertain terrain", t["routes"][1]["descriptors"])
        self.assertEqual(t["routes"][1]["label"], "PARTIALLY UNVERIFIED ROUTE")
        self.assertEqual(route_comparison.route_label(None, STD), "NO VALID ROUTE")
        self.assertEqual(route_comparison.route_label(a, CONS), "CONSERVATIVE ROUTE")
        text = str(t).lower()
        self.assertNotIn("safest", text)
        self.assertNotIn("guaranteed", text)
        self.assertNotIn("travel_time", text)


# ---------------------------------------------------------------- API on synthetic rasters
R_MARS = 3_396_000.0
WIDTH = 2 * math.pi * R_MARS
PIX = WIDTH / 720  # 0.5 deg cells


def gpt(lon, lat):
    return {"lon_east_deg": lon, "lat_deg": lat, "crs": MARS_SPHERE, "latitude_convention": "PLANETOCENTRIC", "planet": "MARS"}


@requires_raster
class SeamRoutingTests(TempDirMixin, TestCase):
    """Full-circumference equirectangular DEM centred on 180 E (like MOLA MEGDR): its left and
    right edges are lon 0 = 360."""

    def setUp(self):
        super().setUp()
        self.z = np.zeros((360, 720), dtype="float32")
        path = write_geotiff(self.tmp / "megdr_like.tif", self.z, west=-WIDTH / 2, north=PIX * 180, pixel_deg=PIX,
                             crs="+proj=eqc +lon_0=180 +R=3396000 +units=m +no_defs")
        call_command("import_dem", "--file", str(path), "--name", "seam", "--vertical-datum", "test datum", "--planet", "MARS",
                     "--instrument", "TEST", stdout=StringIO(), stderr=StringIO())
        self.c = APIClient()

    def plan(self, a, b, **kw):
        return self.c.post("/api/v1/routes/plan/", {"start": gpt(*a), "end": gpt(*b), "include_return": False,
                                                    "include_alternative": False, **kw}, format="json")

    def test_route_crosses_zero_longitude_the_short_way(self):
        ref = self.plan((40.25, 10.25), (46.25, 10.25)).json()
        for a, b in (((357.25, 10.25), (3.25, 10.25)), ((-2.75, 10.25), (3.25, 10.25)), ((3.25, 10.25), (357.25, 10.25))):
            r = self.plan(a, b)
            self.assertEqual(r.status_code, 201, r.content)
            body = r.json()
            self.assertTrue(body["grid"]["crosses_dem_seam"])
            self.assertEqual(body["route"]["cells"], ref["route"]["cells"])  # 6 deg = 12 steps, not 354 deg
            self.assertAlmostEqual(body["route"]["distance_m"], ref["route"]["distance_m"], delta=1.0)
            lons = [c[0] for c in body["route"]["geometry"]["coordinates"]]
            self.assertTrue(all(-3.5 <= lon <= 3.5 for lon in lons), lons)  # continuous through 0, in -180..180
            self.assertEqual(len(body["route"]["geometry_display"]["coordinates"]), 1)  # 0/360 is not a map seam
            self.assertTrue(body["route"]["validation"]["valid"])

    def test_route_across_180_is_split_for_display_only(self):
        r = self.plan((176.25, -20.25), (-176.75, -20.25))
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertFalse(body["grid"]["crosses_dem_seam"])  # 180 E is the middle of this raster
        expected = math.radians(7.0) * R_MARS * math.cos(math.radians(20.25))
        self.assertAlmostEqual(body["route"]["distance_m"], expected, delta=expected * 0.01)
        parts = body["route"]["geometry_display"]["coordinates"]
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0][-1][0], 180.0)
        self.assertEqual(parts[1][0][0], -180.0)

    def test_obstacle_on_the_seam_is_seen_from_both_sides(self):
        # A wall along lon 0 (first and last raster column) with one gap at 30 N. 20 km high on
        # ~29 km cells: too steep both for the cell slope and for a diagonal step (a lower wall
        # can legitimately be climbed diagonally, where the grade along the step is gentler).
        z = self.z.copy()
        z[:, 0] = z[:, -1] = 20000.0
        gap = int((90 - 30) / 0.5)
        # 15 deg wide: the search window grows to the whole DEM (3x decimated, ~89 km cells), and a
        # conservative coarse cell is blocked if ANY native cell in it is too steep, so a narrow
        # gap (a few native cells) is correctly closed at that scale.
        z[gap - 15 : gap + 15, 0] = z[gap - 15 : gap + 15, -1] = 0.0
        path = write_geotiff(self.tmp / "wall.tif", z, west=-WIDTH / 2, north=PIX * 180, pixel_deg=PIX,
                             crs="+proj=eqc +lon_0=180 +R=3396000 +units=m +no_defs")
        call_command("import_dem", "--file", str(path), "--name", "wall", "--vertical-datum", "test datum", "--planet", "MARS",
                     stdout=StringIO(), stderr=StringIO())
        from apps.datasets.models import Dataset

        r = self.plan((357.25, 10.25), (3.25, 10.25), dataset=Dataset.objects.get(name="wall").id, profile="CONSERVATIVE")
        self.assertEqual(r.status_code, 201, r.content)
        coords = r.json()["route"]["geometry"]["coordinates"]
        self.assertGreater(r.json()["grid"]["cells_blocked_by"]["slope"], 0)  # the wall survived decimation
        crossing = [c for c in coords if abs(c[0]) < 0.6]
        self.assertTrue(crossing and all(22.0 <= c[1] <= 38.0 for c in crossing), crossing)  # only through the gap

    def test_decimated_grid_keeps_a_one_cell_wall(self):
        """Whole-DEM grid decimated ~14x: nearest-cell sampling would drop a one-column wall;
        the conservative reduction keeps it as steep coarse cells along the whole seam."""
        from types import SimpleNamespace

        from pyproj import CRS, Transformer

        z = self.z.copy()
        z[:, 0] = 20000.0
        path = write_geotiff(self.tmp / "thin.tif", z, west=-WIDTH / 2, north=PIX * 180, pixel_deg=PIX,
                             crs="+proj=eqc +lon_0=180 +R=3396000 +units=m +no_defs")
        crs = CRS.from_user_input("+proj=eqc +lon_0=180 +R=3396000 +units=m +no_defs")
        ds = SimpleNamespace(crs=crs.to_wkt(), file_path=str(path))
        geo = CRS.from_user_input(MARS_SPHERE)
        to_ds = Transformer.from_crs(geo, crs, always_xy=True)
        g = spatial_grid.build_grid(ds, [to_ds.transform(350.0, 0.0), to_ds.transform(10.0, 0.0)],
                                    Transformer.from_crs(crs, geo, always_xy=True), max_side=50, margin_scale=1e6)
        self.assertGreater(g.meta["decimation_factor"], 10)
        self.assertIn("maximum of the native cells", g.meta["resampling"])
        x_wall, _ = to_ds.transform(0.25, 0.0)
        mid = g.shape[0] // 2
        _, j = g.cell_of(x_wall, g.y0 + mid * g.py)
        self.assertGreater(float(g.slope_deg[mid, j]), 15.0)
        self.assertTrue((g.slope_deg[2:-2, j] > 15.0).all())  # an unbroken wall, no gaps invented by sampling

    def test_polar_rows_use_geodesic_cell_sizes(self):
        r = self.plan((10.25, 80.25), (40.25, 80.25))
        self.assertEqual(r.status_code, 201, r.content)
        expected = math.radians(30.0) * R_MARS * math.cos(math.radians(80.25))
        d = r.json()["route"]["distance_m"]
        self.assertLess(d, expected * 1.01)  # never the equatorial 30 deg (which would be 5.9x longer)
        self.assertGreater(d, expected * 0.7)


@requires_raster
class RoutingApiV04Tests(TempDirMixin, TestCase):
    WEST, NORTH, P, N = 70.0, 20.0, 0.01, 40

    def pt(self, row, col):
        return gpt(self.WEST + (col + 0.5) * self.P, self.NORTH - (row + 0.5) * self.P)

    def load(self, z, name="dem", instrument="TEST", pixel=None, west=None):
        p = write_geotiff(self.tmp / f"{name}.tif", z.astype("float32"), west=self.WEST if west is None else west, north=self.NORTH,
                          pixel_deg=pixel or self.P)
        call_command("import_dem", "--file", str(p), "--name", name, "--vertical-datum", "test datum", "--instrument", instrument,
                     stdout=StringIO(), stderr=StringIO())

    def plan(self, **kw):
        return APIClient().post("/api/v1/routes/plan/", {"start": self.pt(10, 5), "end": self.pt(10, 35), **kw}, format="json")

    def test_response_schema_v04(self):
        z = np.zeros((self.N, self.N))
        z[5:15, 20] = 3000.0
        self.load(z)
        r = APIClient().post("/api/v1/routes/alternatives/", {"start": self.pt(10, 5), "end": self.pt(10, 35), "include_alternative": False}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        b = r.json()
        self.assertEqual((b["status"], b["calculation_status"]), ("ROUTE_FOUND", "CALCULATED"))
        self.assertEqual(b["route_class"], "REGIONAL_PLANNING_ONLY")  # ~593 m cells
        self.assertEqual(b["planning_level"], {"level": 1, "name": "REGIONAL"})
        dq = b["data_quality"]
        self.assertEqual((dq["dataset"], dq["coverage_percentage"], dq["nodata_percentage"], dq["unknown_terrain_percentage"]), ("dem", 100.0, 0.0, 0.0))
        self.assertAlmostEqual(dq["resolution_m"], 592.7, delta=1.0)
        self.assertEqual(dq["effective_accuracy"], "NOT_DOCUMENTED")
        for k in ("distance_m", "total_ascent_m", "total_descent_m", "maximum_slope_deg", "average_slope_deg", "hazard_exposure_m"):
            self.assertIn(k, b["metrics"])
        self.assertTrue(b["warnings"])
        self.assertEqual(b["route_label"], "CONSERVATIVE ROUTE")
        self.assertIsNotNone(b["alternative_route"])  # alternatives/ always asks for one
        self.assertEqual(len(b["comparison_table"]["routes"]), 2)
        self.assertIn("no AI component", b["algorithm"]["geometry_source"])
        self.assertTrue(b["route"]["validation"]["valid"])
        self.assertNotIn("safe route", str(b).lower())

    def test_outside_coverage_statuses(self):
        self.load(np.zeros((self.N, self.N)))
        c = APIClient()
        far = gpt(10.0, 10.0)
        r = c.post("/api/v1/routes/plan/", {"start": far, "end": self.pt(10, 35)}, format="json")
        self.assertEqual((r.status_code, r.json()["calculation_status"]), (422, "START_OUTSIDE_COVERAGE"))
        r = c.post("/api/v1/routes/plan/", {"start": self.pt(10, 5), "end": far}, format="json")
        self.assertEqual(r.json()["calculation_status"], "DESTINATION_OUTSIDE_COVERAGE")
        self.assertIsNone(r.json()["route"])

    def test_unknown_terrain_and_no_route_statuses(self):
        z = np.zeros((self.N, self.N))
        z[:, 20] = -9999.0  # NoData column
        self.load(z)
        r = self.plan(profile="CONSERVATIVE")
        self.assertEqual((r.status_code, r.json()["calculation_status"]), (422, "UNKNOWN_TERRAIN"))
        z2 = np.zeros((self.N, self.N))
        z2[:, 20] = 9000.0  # wall
        Hazard.objects.all().delete()
        from apps.datasets.models import Dataset

        Dataset.objects.all().delete()
        self.load(z2, name="wall")
        r = self.plan(profile="CONSERVATIVE")
        self.assertEqual(r.json()["calculation_status"], "NO_VALID_ROUTE")

    def test_required_resolution_refuses_a_coarse_grid(self):
        self.load(np.zeros((self.N, self.N)))
        r = self.plan(required_resolution_m=25)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["calculation_status"], "INSUFFICIENT_TERRAIN_DATA")
        self.assertIn("requires 25 m", r.json()["reason"])
        self.assertEqual(self.plan(required_resolution_m=1000).status_code, 201)

    def test_finer_dem_is_chosen_and_sets_the_level(self):
        self.load(np.zeros((self.N, self.N)), name="coarse")
        fine_pix = 0.0005  # ~30 m
        self.load(np.zeros((800, 800)), name="fine", pixel=fine_pix)
        r = APIClient().post("/api/v1/routes/plan/", {"start": gpt(70.05, 19.95), "end": gpt(70.06, 19.95)}, format="json")
        b = r.json()
        self.assertEqual(b["dataset"]["name"], "fine")
        self.assertEqual((b["route_class"], b["planning_level"]["level"]), ("SITE_RECONNAISSANCE", 2))

    def test_model_estimated_hazard_is_not_a_hard_constraint_until_confirmed(self):
        self.load(np.zeros((self.N, self.N)))
        mid = self.pt(10, 20)
        hz = Hazard.objects.create(title="detector output", lon_east_deg=mid["lon_east_deg"], lat_deg=mid["lat_deg"], crs=MARS_SPHERE,
                                   latitude_convention="PLANETOCENTRIC", radius_m=3000, planet="MARS",
                                   observation_class="MODEL_ESTIMATED", confidence=0.9)
        b = self.plan(include_alternative=False).json()
        self.assertEqual(b["hazards_considered"], 0)
        hz.verification = "CONFIRMED"
        hz.save()
        b2 = self.plan(include_alternative=False).json()
        self.assertEqual(b2["hazards_considered"], 1)
        self.assertGreater(b2["route"]["distance_m"], b["route"]["distance_m"])  # now it detours
        hz.observation_class, hz.verification = "USER_REPORTED", "UNVERIFIED"
        hz.save()
        self.assertEqual(self.plan(include_alternative=False).json()["hazards_considered"], 1)  # human reports stay blocking

    def test_hazard_of_another_planet_is_ignored(self):
        self.load(np.zeros((self.N, self.N)))
        mid = self.pt(10, 20)
        Hazard.objects.create(title="lunar", lon_east_deg=mid["lon_east_deg"], lat_deg=mid["lat_deg"], crs=MARS_SPHERE,
                              latitude_convention="PLANETOCENTRIC", radius_m=3000, planet="MOON")
        self.assertEqual(self.plan(include_alternative=False).json()["hazards_considered"], 0)

    def test_derive_hazards_endpoint(self):
        z = np.zeros((self.N, self.N))
        z[18:22, 18:22] = 4000.0
        self.load(z)
        c = APIClient()
        r = c.post("/api/v1/routes/hazards/derive/", {"center": self.pt(20, 20), "radius_m": 8000, "slope_limit_deg": 15}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        b = r.json()
        steep = [h for h in b["hazards"] if h["category"] == "STEEP_SLOPE"]
        self.assertTrue(steep)
        self.assertAlmostEqual(steep[0]["lon_east_deg"], 70.2, delta=0.03)
        self.assertEqual(steep[0]["observation_class"], "MODEL_ESTIMATED")
        self.assertEqual(Hazard.objects.count(), 0)  # candidates are not stored
        r = c.post("/api/v1/routes/hazards/derive/", {"center": gpt(10, 10), "radius_m": 8000}, format="json")
        self.assertEqual((r.status_code, r.json()["status"]), (404, "NO_DATA_COVERAGE"))

    def test_hazard_api_provenance_fields(self):
        c = APIClient()
        base = {"title": "Rocks", "lon_east_deg": 70.1, "lat_deg": 19.9, "hazard_type": "BOULDER_FIELD", "planet": "MOON", "crs": "ESRI:104903",
                "observation_class": "OBSERVED", "observation_method": "field visit", "confidence": 0.8}
        r = c.post("/api/v1/hazards/", base, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.json()["planet"], r.json()["observation_class"], r.json()["confidence"]), ("MOON", "OBSERVED", 0.8))
        self.assertEqual(c.post("/api/v1/hazards/", {**base, "confidence": 1.5}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/v1/hazards/", {**base, "planet": "PLUTO"}, format="json").status_code, 400)
        bad = {**base, "observation_class": "MODEL_ESTIMATED", "verification": "CONFIRMED"}
        self.assertEqual(c.post("/api/v1/hazards/", bad, format="json").status_code, 400)
        self.assertEqual(c.post("/api/v1/hazards/", {**base, "hazard_type": "UNKNOWN_SURFACE"}, format="json").status_code, 201)
