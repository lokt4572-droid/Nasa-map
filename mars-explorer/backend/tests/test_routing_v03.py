"""v0.3 routing: corner cutting, safe simplification, unknown-data policy, classification,
per-route metrics, MOLA restriction, route comparison. Synthetic grids only."""
import math
from io import StringIO

import numpy as np
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.routing.profiles import PROFILES, MovementProfile
from apps.routing.services import pathfinder as pf

from .raster_fixtures import MARS_SPHERE, TempDirMixin, requires_raster, write_geotiff

CONS = PROFILES["CONSERVATIVE"]
STD = PROFILES["STANDARD"]


class _Q:
    @staticmethod
    def transform(x, y):
        return x, y


def grid(z: np.ndarray, blocked: np.ndarray | None = None, slope: np.ndarray | None = None) -> pf.TerrainGrid:
    h, w = z.shape
    return pf.TerrainGrid(
        z=z.astype(float), dx_m=np.full(h, 100.0), dy_m=np.full(h - 1, 100.0),
        slope_deg=np.zeros((h, w)) if slope is None else slope, tri_m=np.zeros((h, w)),
        blocked=np.zeros((h, w), dtype=bool) if blocked is None else blocked,
        x0=0.0, y0=0.0, px=1.0, py=-1.0, decimation=1.0, to_query=_Q(),
    )


def diagonal_moves(path):
    return [(a, b) for a, b in zip(path[:-1], path[1:]) if a[0] != b[0] and a[1] != b[1]]


class CornerCuttingTests(SimpleTestCase):
    def test_no_diagonal_between_two_blocked_cells(self):
        b = np.zeros((3, 3), dtype=bool)
        b[0, 1] = b[1, 0] = True
        g = grid(np.zeros((3, 3)), blocked=b)
        self.assertIsNone(pf.astar(g, (0, 0), (1, 1), CONS))  # v0.2 squeezed through diagonally

    def test_no_diagonal_past_one_blocked_cell(self):
        b = np.zeros((3, 3), dtype=bool)
        b[0, 1] = True
        g = grid(np.zeros((3, 3)), blocked=b)
        path = pf.astar(g, (0, 0), (1, 1), CONS)
        self.assertEqual(path, [(0, 0), (1, 0), (1, 1)])

    def test_no_corner_cutting_past_nodata_or_steep_cells(self):
        z = np.zeros((3, 3))
        z[0, 1] = np.nan
        self.assertEqual(pf.astar(grid(z), (0, 0), (1, 1), CONS), [(0, 0), (1, 0), (1, 1)])
        slope = np.zeros((3, 3))
        slope[1, 0] = 40.0
        self.assertEqual(pf.astar(grid(np.zeros((3, 3)), slope=slope), (0, 0), (1, 1), CONS), [(0, 0), (0, 1), (1, 1)])

    def test_diagonals_still_used_in_open_terrain(self):
        path = pf.astar(grid(np.zeros((6, 6))), (0, 0), (5, 5), CONS)
        self.assertEqual(len(path), 6)
        self.assertEqual(len(diagonal_moves(path)), 5)

    def test_every_diagonal_of_a_route_has_passable_side_cells(self):
        checked = 0
        for seed in range(40):
            b = np.random.default_rng(seed).random((30, 30)) < 0.3
            b[0, 0] = b[29, 29] = False
            path = pf.astar(grid(np.zeros((30, 30)), blocked=b), (0, 0), (29, 29), CONS)
            if path is None:
                continue
            checked += 1
            for (i, j), (ni, nj) in diagonal_moves(path):
                self.assertFalse(b[ni, j] or b[i, nj], seed)
        self.assertGreater(checked, 3)


class SimplificationTests(SimpleTestCase):
    def test_supercover_includes_both_cells_at_an_exact_corner(self):
        cells = pf.supercover_cells(0, 0, 2, 2)
        self.assertIn((0, 1), cells)
        self.assertIn((1, 0), cells)
        self.assertEqual(cells[-1], (2, 2))

    def test_simplified_line_never_crosses_an_obstacle(self):
        b = np.zeros((10, 10), dtype=bool)
        b[2:8, 5] = True  # wall with gaps at rows 0-1 and 8-9
        g = grid(np.zeros((10, 10)), blocked=b)
        path = pf.astar(g, (5, 0), (5, 9), CONS)
        simp = pf.simplify_path(g, path, CONS)
        self.assertLess(len(simp), len(path))
        for a, c in zip(simp[:-1], simp[1:]):
            for cell in pf.supercover_cells(*a, *c):
                self.assertFalse(b[cell], (a, c, cell))

    def test_simplification_never_straightens_across_nodata(self):
        z = np.zeros((5, 9))
        z[1:4, 4] = np.nan
        g = grid(z)
        path = pf.astar(g, (2, 0), (2, 8), STD)  # STANDARD may cross NoData...
        simp = pf.simplify_path(g, path, STD)
        for a, c in zip(simp[:-1], simp[1:]):
            crossed = [cell for cell in pf.supercover_cells(*a, *c) if np.isnan(z[cell])]
            # ...but a simplified segment through NoData only exists as an original cell step
            if crossed:
                self.assertLessEqual(max(abs(a[0] - c[0]), abs(a[1] - c[1])), 1)


class CostAndClassificationTests(SimpleTestCase):
    def test_hazard_proximity_pushes_route_away(self):
        g = grid(np.zeros((21, 21)))
        prof = MovementProfile(**{**CONS.__dict__, "hazard_proximity_weight": 5.0})
        pf.block_hazards(g, [(10.0, -8.0, 150.0)])  # hazard centred on cell (8, 10), r = 150 m
        self.assertTrue(g.blocked[8, 10])
        self.assertGreater(g.proximity[8, 12], 0)  # 200 m away: inside 2r
        self.assertEqual(g.proximity[8, 18], 0)  # 800 m away: outside 2r
        straight = [(10, j) for j in range(21)]
        path = pf.astar(g, (10, 0), (10, 20), prof)
        self.assertLess(pf.path_cost(g, path, prof), pf.path_cost(g, straight, prof))
        self.assertGreater(max(abs(i - 10) for i, _ in path), 0)

    def test_classification_and_unverified_segments(self):
        z = np.zeros((5, 9))
        z[:, 4] = np.nan  # NoData column across the grid
        g = grid(z)
        self.assertIsNone(pf.astar(g, (2, 0), (2, 8), CONS))  # CONSERVATIVE never enters NoData
        path = pf.astar(g, (2, 0), (2, 8), STD)
        r = pf.describe_route(g, path, STD, "PLANETOCENTRIC", "PLANETOCENTRIC")
        self.assertEqual(r["classification"], pf.CLASS_PARTIAL)
        self.assertEqual(len(r["unverified_segments"]), 1)
        seg = r["unverified_segments"][0]
        self.assertAlmostEqual(seg["to_m"] - seg["from_m"], 200.0)  # into and out of the NoData cell
        self.assertLess(r["metrics"]["known_terrain_pct"], 100)
        clean = pf.describe_route(grid(np.zeros((5, 9))), pf.astar(grid(np.zeros((5, 9))), (2, 0), (2, 8), STD), STD, "X", "X")
        self.assertEqual(clean["classification"], pf.CLASS_KNOWN)
        self.assertEqual(clean["unverified_segments"], [])

    def test_comparison_uses_same_profile_and_no_travel_time(self):
        g = grid(np.zeros((9, 9)))
        a = pf.describe_route(g, pf.astar(g, (0, 0), (8, 8), CONS), CONS, "X", "X")
        b = pf.describe_route(g, [(0, 0)] + [(0, j) for j in range(1, 9)] + [(i, 8) for i in range(1, 9)], CONS, "X", "X")
        c = pf.compare_routes(a, b)
        self.assertGreater(c["difference_b_minus_a"]["distance_m"], 0)
        self.assertGreater(c["difference_b_minus_a"]["cost"], 0)
        self.assertNotIn("time", str(c).lower().replace("no travel time", ""))


WEST, NORTH, PIX, N = 70.0, 20.0, 0.01, 40


def pt(row, col):
    return {"lon_east_deg": WEST + (col + 0.5) * PIX, "lat_deg": NORTH - (row + 0.5) * PIX, "crs": MARS_SPHERE,
            "latitude_convention": "PLANETOCENTRIC"}


@requires_raster
class RoutingApiV03Tests(TempDirMixin, TestCase):
    def load(self, z, name="dem", instrument=""):
        p = write_geotiff(self.tmp / f"{name}.tif", z.astype("float32"), west=WEST, north=NORTH, pixel_deg=PIX)
        call_command("import_dem", "--file", str(p), "--name", name, "--vertical-datum", "test datum",
                     "--instrument", instrument, stdout=StringIO(), stderr=StringIO())

    def plan(self, **kw):
        return APIClient().post("/api/v1/routes/plan/", {"start": pt(10, 5), "end": pt(10, 35), **kw}, format="json")

    def test_found_route_has_classification_metrics_and_comparison(self):
        z = np.zeros((N, N))
        z[5:15, 20] = 3000.0  # obstacle -> two distinct ways around
        self.load(z, instrument="TEST")
        r = self.plan(profile="CONSERVATIVE")
        self.assertEqual(r.status_code, 201, r.content)
        b = r.json()
        self.assertEqual(b["route_classification"], "KNOWN_TERRAIN_ROUTE")
        m = b["route"]["metrics"]
        for k in ("distance_m", "elevation_gain_m", "max_cell_slope_deg", "known_terrain_pct", "nodata_pct_along_route",
                  "dem_source", "dem_resolution_m", "grid_cell_size_m", "window_nodata_pct", "suitability_class"):
            self.assertIn(k, m)
        self.assertEqual(b["comparison"]["route_a"]["label"], "Route A — lowest cost")
        self.assertIn("No travel time", b["comparison"]["note"])
        self.assertIn("geometry_simplified", b["route"])
        self.assertLessEqual(len(b["route"]["geometry_simplified"]["coordinates"]), len(b["route"]["geometry"]["coordinates"]))
        self.assertNotIn("travel_time", str(b))
        self.assertEqual(b["profile"]["unknown_data_policy"], "REJECT")

    def test_failure_is_no_valid_route(self):
        z = np.zeros((N, N))
        z[:, 20] = 3000.0
        self.load(z)
        b = self.plan(profile="STANDARD").json()
        self.assertEqual(b["route_classification"], "NO_VALID_ROUTE")
        self.assertIsNone(b["route"])

    def test_unknown_policy(self):
        z = np.zeros((N, N))
        z[:, 20] = -9999.0
        self.load(z)
        self.assertEqual(self.plan(profile="CONSERVATIVE", unknown_data_policy="ALLOW_MARKED").status_code, 400)
        r = self.plan(profile="STANDARD")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["route_classification"], "PARTIALLY_UNVERIFIED_ROUTE")
        self.assertTrue(r.json()["route"]["unverified_segments"])
        strict = self.plan(profile="STANDARD", unknown_data_policy="REJECT")
        self.assertEqual(strict.status_code, 422)
        self.assertEqual(strict.json()["route_classification"], "NO_VALID_ROUTE")

    def test_mola_dem_is_regional_planning_only(self):
        self.load(np.zeros((N, N)), name="mola-test", instrument="MGS MOLA")
        b = self.plan(profile="CONSERVATIVE", include_alternative=False).json()
        scope = b["data_quality"]["planning_scope"]
        self.assertEqual(scope["scope"], "REGIONAL_PLANNING_ONLY")
        self.assertIn("MOLA", scope["reason"])
        self.assertEqual(b["route"]["metrics"]["suitability_class"], "REGIONAL_PLANNING_ONLY")
        self.assertFalse(b["data_quality"]["resolution_assessment"]["suitable_for_astronaut_scale_route_safety"])
