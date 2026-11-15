"""Route planning service: chooses the DEM, runs the deterministic planner, assembles the result.

The path is always computed by the deterministic search (``pathfinder``) on the DEM grid.
Nothing in this module — and no AI component — writes route geometry.

Planning levels (by the data actually used, never assumed):
  1 REGIONAL  global/regional DEM (e.g. MOLA): corridors only;
  2 LOCAL     about 5-100 m DTM (e.g. CTX, Kaguya TC): landforms;
  3 DETAILED  metre-scale DTM (e.g. HiRISE): fine relief. No level makes a route "safe".
"""
from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response

from apps.core.exceptions import ApiError
from apps.hazards.models import Hazard
from services import dataset_manager, dem_reader
from services.mars_coordinates import resolve_crs, transform_point

from ..models import Route
from ..profiles import assess_resolution, get_profile
from . import pathfinder, route_comparison

logger = logging.getLogger("mars.routing")

DISCLAIMER = (
    "Computed on the DEM at its own (possibly decimated) resolution with heuristic profile "
    "weights. Not a validated traversability or safety assessment; obstacles smaller than a "
    "DEM cell are invisible to the planner."
)

# Spec vocabulary (v0.4) for the outcome of a calculation.
CALC_STATUS = {
    pathfinder.STATUS_FOUND: "CALCULATED",
    pathfinder.STATUS_INSUFFICIENT: "INSUFFICIENT_TERRAIN_DATA",
    pathfinder.STATUS_NO_PASSABLE: "NO_VALID_ROUTE",
    "PROCESSING_ERROR": "PROCESSING_ERROR",
}
PLANNING_LEVEL = {
    "REGIONAL_PLANNING_ONLY": {"level": 1, "name": "REGIONAL"},
    "SITE_RECONNAISSANCE": {"level": 2, "name": "LOCAL"},
    "DETAILED_TRAVERSE_STUDY": {"level": 3, "name": "DETAILED"},
}


def _failure(status_code: str, reason: str, details=None, http=422, calc: str | None = None) -> Response:
    return Response(
        {
            "status": status_code,
            "calculation_status": calc or CALC_STATUS.get(status_code, status_code),
            "route_class": None,
            "warnings": [reason],
            "route_classification": pathfinder.CLASS_NONE,
            "route": None,
            "reason": reason,
            "details": details or {},
            "error": {"code": status_code, "message": reason, "details": details or {}},
        },
        status=http,
    )


def _hazards_in_query_crs(query_crs, crs_id: str, planet: str = "MARS") -> list[tuple[float, float, float]]:
    """Hazards that act as HARD constraints: reports of this body that are not rejected and are
    not unvalidated model output. AI/model detections block nothing until a person confirms them."""
    out = []
    qs = Hazard.objects.filter(planet=planet).exclude(verification=Hazard.Verification.REJECTED)
    qs = qs.exclude(observation_class__in=Hazard.SOFT_CLASSES, verification=Hazard.Verification.UNVERIFIED)
    for hz in qs:
        lon, lat = hz.lon_east_deg, hz.lat_deg
        if hz.crs != crs_id:
            try:
                hz_crs, _ = resolve_crs(hz.crs)
                lon, lat = transform_point(lon, lat, hz_crs, query_crs)
            except Exception:  # noqa: BLE001 - a hazard we cannot place is reported, not dropped silently
                logger.warning("Hazard %s has unresolvable CRS %s; ignored by planner", hz.pk, hz.crs)
                continue
        out.append((lon, lat, hz.radius_m or 0.0))
    return out


def _data_quality(ds, grid: dict, lat_conv: str, route: dict | None) -> dict:
    """Resolution and quality of the terrain data the planner actually used."""
    cs = grid.get("cell_size_m") or {}
    effective = max(cs.get("dx_max") or 0.0, cs.get("dy_mean") or 0.0)
    known = {"PLANETOCENTRIC", "PLANETOGRAPHIC"}
    if lat_conv in known and ds.latitude_convention in known:
        lat_status = "NONE" if lat_conv == ds.latitude_convention else f"CONVERTED_{lat_conv}_TO_{ds.latitude_convention}"
    else:
        lat_status = "NOT_VERIFIED"
    return {
        "dem": {"id": ds.id, "name": ds.name, "instrument": ds.instrument, "product_id": ds.product_id,
                "resolution_m": ds.resolution_meters, "vertical_datum": ds.vertical_datum, "crs": ds.crs_name},
        "grid_decimation_factor": grid.get("decimation_factor"),
        "grid_cell_size_m": cs,
        "window_nodata_fraction": grid.get("nodata_fraction"),
        "route_unknown_terrain_fraction": route["unknown_terrain_fraction"] if route else None,
        "latitude_handling": lat_status,
        "resolution_assessment": assess_resolution(effective, ds.resolution_meters),
        "planning_scope": planning_scope(ds, effective),
        # v0.4 summary block (every value from the dataset record or this computation)
        "dataset": ds.name,
        "resolution_m": ds.resolution_meters,
        "grid_cell_m": round(effective, 3),
        "access": getattr(ds, "access", "LOCAL"),
        "quality_status": getattr(ds, "quality_status", "NOT_DOCUMENTED"),
        "effective_accuracy": "NOT_DOCUMENTED",
        "coverage_percentage": round(100 * (1 - (grid.get("nodata_fraction") or 0.0)), 3) if grid else None,
        "nodata_percentage": round(100 * (grid.get("nodata_fraction") or 0.0), 3) if grid else None,
        "unknown_terrain_percentage": round(100 * route["unknown_terrain_fraction"], 3) if route else None,
    }


def planning_scope(ds, effective_cell_m: float) -> dict:
    """MOLA-derived DEMs are regional planning only, whatever their gridding: MOLA shots are
    ~300 m apart along track and kilometres apart across track, so gridded values between
    tracks are interpolated, not measured."""
    is_mola = "MOLA" in f"{ds.instrument} {ds.name} {ds.product_id}".upper()
    cls = assess_resolution(effective_cell_m, ds.resolution_meters)["class"]
    if is_mola or cls == "REGIONAL_PLANNING_ONLY":
        return {
            "scope": "REGIONAL_PLANNING_ONLY",
            "reason": ("MOLA altimetry: regional planning only (track spacing, interpolation between tracks)"
                       if is_mola else "DEM cells are larger than 100 m: regional planning only"),
        }
    return {"scope": cls, "reason": "set by the routing grid resolution"}


def _route_metrics_with_dem(route: dict | None, ds, grid: dict, scope: dict) -> None:
    if not route:
        return
    cs = grid.get("cell_size_m") or {}
    route["metrics"].update(
        dem_source=ds.source, dem_name=ds.name, dem_instrument=ds.instrument,
        dem_resolution_m=ds.resolution_meters, grid_cell_size_m=cs,
        window_nodata_pct=round(100 * (grid.get("nodata_fraction") or 0.0), 2),
        suitability_class=scope["scope"],
    )


def _candidate_dems(points, query_crs, lat_conv, planet, only_id=None, terrain_source="local"):
    """DEMs covering ALL points, finest first, and how many points have any coverage.

    ``terrain_source="auto"`` also asks the provider catalogue for DTM products containing both
    the start and the end and registers the finest valid one for remote window reads."""
    per_point = []
    for p in points:
        per_point.append({d.id: d for d in dataset_manager.datasets_covering(p["lon_east_deg"], p["lat_deg"], query_crs, lat_convention=lat_conv, planet=planet)})
    notes: list[str] = []
    if terrain_source == "auto" and not only_id:
        from apps.datasets.services import dataset_discovery, stac_client

        try:
            first = stac_client.search(planet, point=(points[0]["lon_east_deg"], points[0]["lat_deg"]), data_type="DEM")["products"]
            best_local = min((d.resolution_meters or float("inf") for d in per_point[0].values() if all(d.id in s for s in per_point)), default=float("inf"))
            for rec in first:
                if (rec["resolution_m"] or float("inf")) >= best_local:
                    break
                if not all(stac_client.point_in_footprint(rec["footprint"], p["lon_east_deg"], p["lat_deg"]) for p in points):
                    continue
                try:
                    ds = dataset_discovery.register_remote_dem(rec)
                except dataset_discovery.DiscoveryError as exc:
                    notes.append(f"Catalogue product {rec['product_id']} skipped: {exc}")
                    continue
                for s, p in zip(per_point, points):
                    s[ds.id] = ds
                notes.append(f"Using catalogue DTM {rec['product_id']} ({rec['instrument']}) read remotely")
                break
        except stac_client.StacError as exc:
            notes.append(f"Provider catalogue not available ({exc}); registered DEMs only")
    common = [d for d_id, d in per_point[0].items() if all(d_id in s for s in per_point[1:])]
    if only_id:
        common = [d for d in common if d.id == only_id]
    common = [d for d in common if dataset_manager.refresh_file_status(d)]
    common.sort(key=lambda d: (d.resolution_meters is None, d.resolution_meters or 0))
    return common, [bool(s) for s in per_point], notes


def plan_request(v: dict, raw_request) -> Response:
    """Run one validated plan request. ``v`` is RoutePlanRequestSerializer.validated_data."""
    points = [v["start"], *v["waypoints"], v["end"]]
    crs_id, lat_conv, planet = points[0]["crs"], points[0]["latitude_convention"], points[0]["planet"]
    query_crs, _ = resolve_crs(crs_id, planet=planet)
    profile = get_profile(v["profile"])
    if "max_slope_deg" in v:
        profile = pathfinder.MovementProfile(**{**profile.__dict__, "max_slope_deg": min(v["max_slope_deg"], profile.max_slope_deg)})
    overrides = {k: v[k] for k in ("max_roughness_m", "max_local_relief_m", "required_resolution_m", "connectivity") if v.get(k) is not None}
    if v.get("hazard_buffer_m") is not None:
        overrides["hazard_buffer_m"] = max(v["hazard_buffer_m"], profile.hazard_buffer_m)  # only ever more cautious
    if v.get("prefer_lower_roughness"):
        overrides["roughness_weight"] = profile.roughness_weight * 2.0
    if overrides:
        profile = pathfinder.MovementProfile(**{**profile.__dict__, **overrides})
    if v.get("unknown_data_policy") == "REJECT" and profile.allow_unknown_terrain:
        profile = pathfinder.MovementProfile(**{**profile.__dict__, "allow_unknown_terrain": False,
                                                "unknown_multiplier": float("inf"), "max_unknown_fraction": 0.0})
    if not dem_reader.raster_backend_status()["available"]:
        raise ApiError("Raster backend (GDAL) not available", code="DEM_BACKEND_UNAVAILABLE", status_code=503)

    common, covered, notes = _candidate_dems(points, query_crs, lat_conv, planet, v.get("dataset"), v.get("terrain_source", "local"))
    if not common:
        if not covered[0]:
            return _failure(pathfinder.STATUS_INSUFFICIENT, "The start point is outside every validated DEM", {"notes": notes}, calc="START_OUTSIDE_COVERAGE")
        if not covered[-1]:
            return _failure(pathfinder.STATUS_INSUFFICIENT, "The destination is outside every validated DEM", {"notes": notes}, calc="DESTINATION_OUTSIDE_COVERAGE")
        return _failure(pathfinder.STATUS_INSUFFICIENT, "No validated DEM covers all route points", {"notes": notes})
    ds = common[0]

    hazards = _hazards_in_query_crs(query_crs, crs_id, planet)
    try:
        result = pathfinder.plan_route(
            ds, [(p["lon_east_deg"], p["lat_deg"]) for p in points], query_crs, lat_conv, profile,
            hazards_query=hazards, include_return=v["include_return"], include_alternative=v["include_alternative"],
        )
    except pathfinder.RoutePlanningError as exc:
        grid = exc.details.get("grid") or {}
        calc = None
        if "without DEM data" in exc.reason or "no DEM elevation" in exc.reason:
            calc = "UNKNOWN_TERRAIN"
        return _failure(exc.status, exc.reason, {**exc.details, "dataset": ds.name, "profile": profile.to_dict(), "notes": notes,
                                                 "data_quality": _data_quality(ds, grid, lat_conv, None)}, calc=calc)
    except dem_reader.RasterReadError as exc:
        if getattr(ds, "access", "LOCAL") == "REMOTE_COG":
            return _failure("PROCESSING_ERROR", "The remote DEM could not be read from its provider", {"dataset": ds.name}, http=502, calc="INVALID_DATASET")
        raise ApiError(str(exc), code="DEM_READ_ERROR", status_code=500) from exc

    result["data_quality"] = _data_quality(ds, result["grid"], lat_conv, result["route"])
    for key in ("route", "return_route", "alternative_route"):
        _route_metrics_with_dem(result.get(key), ds, result["grid"], result["data_quality"]["planning_scope"])
    scope = result["data_quality"]["planning_scope"]
    warnings = list(notes)
    warnings.append(f"{scope['scope'].replace('_', ' ')}: {scope['reason']}")
    if result["route"]["unknown_terrain_fraction"] > 0:
        warnings.append(f"{result['route']['unknown_terrain_fraction']:.1%} of the route crosses cells without DEM data (marked UNVERIFIED)")
    if result["grid"].get("decimation_factor", 1) > 1.01:
        warnings.append(f"The DEM window was decimated {result['grid']['decimation_factor']:.1f}x for planning: features smaller than a grid cell are not represented")
    if result["grid"].get("nodata_fraction", 0) > 0:
        warnings.append(f"{result['grid']['nodata_fraction']:.1%} of the analysed window has no DEM data")
    if getattr(ds, "quality_status", "") in ("PARTIAL_GAPS", "LARGE_GAPS"):
        warnings.append(f"Provider quality of the DEM: {ds.quality_status}")
    result.update(
        calculation_status="CALCULATED",
        route_class=scope["scope"],
        planning_level=PLANNING_LEVEL.get(scope["scope"], {"level": 1, "name": "REGIONAL"}),
        route_label=route_comparison.route_label(result["route"], profile),
        metrics=result["route"]["metrics"],
        warnings=warnings,
        comparison_table=route_comparison.compare(
            [("Route A", result["route"]), ("Route B", result.get("alternative_route"))], result["data_quality"], profile),
        algorithm={"search": "A*", "connectivity": profile.connectivity, "heuristic": "admissible geodesic lower bound",
                   "geometry_source": "deterministic search on the DEM grid (no AI component writes geometry)"},
        profile=profile.to_dict(),
        dataset={"id": ds.id, "name": ds.name, "resolution_m": ds.resolution_meters, "vertical_datum": ds.vertical_datum, "source": ds.source},
        query={"crs": crs_id, "latitude_convention": lat_conv, "planet": planet},
        hazards_considered=len(hazards),
        disclaimer=DISCLAIMER,
    )
    route = Route.objects.create(
        mission_id=v.get("mission"), dataset=ds, profile=profile.id, status=result["status"],
        request=raw_request, result=result, distance_m=result["route"]["distance_m"],
        unknown_terrain_fraction=result["route"]["unknown_terrain_fraction"],
    )
    return Response({"id": route.id, **result}, status=status.HTTP_201_CREATED)


def derive_hazards_request(v: dict) -> Response:
    """Slope / roughness / NoData hazard candidates on the best DEM around a point."""
    import math

    from pyproj import CRS, Transformer

    from services.mars_coordinates import adapt_latitude
    from services.planet_registry import get_planet

    from . import hazard_analysis, spatial_grid

    c = v["center"]
    crs_id, lat_conv, planet = c["crs"], c["latitude_convention"], c["planet"]
    query_crs, _ = resolve_crs(crs_id, planet=planet)
    if not dem_reader.raster_backend_status()["available"]:
        raise ApiError("Raster backend (GDAL) not available", code="DEM_BACKEND_UNAVAILABLE", status_code=503)
    r = get_planet(planet).radius_equatorial_m
    dlat = math.degrees(v["radius_m"] / r)
    dlon = dlat / max(math.cos(math.radians(c["lat_deg"])), 1e-3)
    corners = [{**c, "lon_east_deg": c["lon_east_deg"] - dlon, "lat_deg": max(-89.9, c["lat_deg"] - dlat)},
               {**c, "lon_east_deg": c["lon_east_deg"] + dlon, "lat_deg": min(89.9, c["lat_deg"] + dlat)}]
    common, _, notes = _candidate_dems([c], query_crs, lat_conv, planet, v.get("dataset"), v.get("terrain_source", "local"))
    if not common:
        return Response({"status": "NO_DATA_COVERAGE", "hazards": [], "notes": notes,
                         "message": "No validated elevation dataset covers this location; no hazard can be derived."}, status=404)
    ds = common[0]
    ds_crs = CRS.from_wkt(ds.crs)
    to_ds = Transformer.from_crs(query_crs, ds_crs, always_xy=True)
    to_query = Transformer.from_crs(ds_crs, query_crs, always_xy=True)

    def q2ds(p):
        lat2, _ = adapt_latitude(p["lat_deg"], lat_conv, ds.latitude_convention)
        return to_ds.transform(p["lon_east_deg"], lat2)

    try:
        # Corners outside the raster are clipped to it by reading around the centre only.
        pts = [q2ds(c)]
        for k in corners:
            try:
                x, y = q2ds(k)
                b = ds.coverage_bbox
                if b["bottom"] < y <= b["top"]:
                    pts.append((x, y))
            except Exception:  # noqa: BLE001
                pass
        try:
            grid = spatial_grid.build_grid(ds, pts, to_query, margin_scale=0.0)
        except pathfinder.RoutePlanningError:
            grid = spatial_grid.build_grid(ds, pts[:1], to_query, margin_scale=1.0)
    except dem_reader.RasterReadError as exc:
        raise ApiError(str(exc), code="DEM_READ_ERROR", status_code=502) from exc
    out = hazard_analysis.derive_hazards(grid, v["slope_limit_deg"], v.get("roughness_limit_m"))
    for h in out["hazards"]:
        lon, lat = to_query.transform(h.pop("x"), h.pop("y"))
        lat, _ = adapt_latitude(float(lat), ds.latitude_convention, lat_conv)
        from .route_metrics import wrap_lon_180

        h.update(lon_east_deg=wrap_lon_180(float(lon)), lat_deg=float(lat), planet=planet, crs=crs_id,
                 source_dataset=ds.name, source_resolution_m=ds.resolution_meters)
    return Response({"status": "DERIVED", **out, "dataset": {"id": ds.id, "name": ds.name, "resolution_m": ds.resolution_meters,
                     "instrument": ds.instrument}, "grid": grid.meta, "notes": notes})
