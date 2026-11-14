"""Route planning API (A* on a validated DEM).

A route is returned only when the planner found one on real DEM data. Otherwise the
response is ``{"status": "INSUFFICIENT_TERRAIN_DATA" | "NO_PASSABLE_ROUTE", "route": null}``
(HTTP 422). A found route is never called "safe".
"""
from __future__ import annotations

import logging

from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.coordinates import PointQuerySerializer
from apps.core.exceptions import ApiError
from apps.hazards.models import Hazard
from services import dataset_manager, dem_reader
from services.mars_coordinates import resolve_crs, transform_point

from .models import Route
from .profiles import PROFILES, get_profile
from .services import pathfinder

logger = logging.getLogger("mars.routing")

DISCLAIMER = (
    "Computed on the DEM at its own (possibly decimated) resolution with heuristic profile "
    "weights. Not a validated traversability or safety assessment; obstacles smaller than a "
    "DEM cell are invisible to the planner."
)


class RoutePlanRequestSerializer(serializers.Serializer):
    start = PointQuerySerializer()
    end = PointQuerySerializer()
    waypoints = PointQuerySerializer(many=True, required=False, default=list)
    profile = serializers.ChoiceField(choices=list(PROFILES), default="CONSERVATIVE")
    include_return = serializers.BooleanField(default=True)
    include_alternative = serializers.BooleanField(default=True)
    max_slope_deg = serializers.FloatField(min_value=1.0, max_value=45.0, required=False)
    mission = serializers.IntegerField(required=False, min_value=1)
    dataset = serializers.IntegerField(required=False, min_value=1)

    def validate_waypoints(self, value):
        if len(value) > 20:
            raise serializers.ValidationError("At most 20 intermediate waypoints")
        return value

    def validate(self, attrs):
        pts = [attrs["start"], *attrs["waypoints"], attrs["end"]]
        if len({(p["crs"], p["latitude_convention"], p["planet"]) for p in pts}) != 1:
            raise serializers.ValidationError("All points must use the same crs, latitude_convention and planet")
        return attrs


def _failure(status_code: str, reason: str, details=None, http=422) -> Response:
    return Response(
        {
            "status": status_code,
            "route": None,
            "reason": reason,
            "details": details or {},
            "error": {"code": status_code, "message": reason, "details": details or {}},
        },
        status=http,
    )


def _hazards_in_query_crs(query_crs, crs_id: str) -> list[tuple[float, float, float]]:
    out = []
    for hz in Hazard.objects.exclude(verification=Hazard.Verification.REJECTED):
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


@api_view(["POST"])
def plan(request):
    ser = RoutePlanRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    v = ser.validated_data
    points = [v["start"], *v["waypoints"], v["end"]]
    crs_id, lat_conv, planet = points[0]["crs"], points[0]["latitude_convention"], points[0]["planet"]
    query_crs, _ = resolve_crs(crs_id, planet=planet)
    profile = get_profile(v["profile"])
    if "max_slope_deg" in v:
        profile = pathfinder.MovementProfile(**{**profile.__dict__, "max_slope_deg": min(v["max_slope_deg"], profile.max_slope_deg)})
    if not dem_reader.raster_backend_status()["available"]:
        raise ApiError("Raster backend (GDAL) not available", code="DEM_BACKEND_UNAVAILABLE", status_code=503)

    # A DEM that covers ALL points (finest first).
    candidate_sets = []
    for p in points:
        ids = {d.id: d for d in dataset_manager.datasets_covering(p["lon_east_deg"], p["lat_deg"], query_crs, lat_convention=lat_conv, planet=planet)}
        candidate_sets.append(ids)
    common = [d for d_id, d in candidate_sets[0].items() if all(d_id in s for s in candidate_sets[1:])]
    if v.get("dataset"):
        common = [d for d in common if d.id == v["dataset"]]
    common = [d for d in common if dataset_manager.refresh_file_status(d)]
    if not common:
        return _failure(pathfinder.STATUS_INSUFFICIENT, "No validated DEM covers all route points")
    ds = sorted(common, key=lambda d: (d.resolution_meters is None, d.resolution_meters or 0))[0]

    hazards = _hazards_in_query_crs(query_crs, crs_id) if planet == "MARS" else []
    try:
        result = pathfinder.plan_route(
            ds, [(p["lon_east_deg"], p["lat_deg"]) for p in points], query_crs, lat_conv, profile,
            hazards_query=hazards, include_return=v["include_return"], include_alternative=v["include_alternative"],
        )
    except pathfinder.RoutePlanningError as exc:
        return _failure(exc.status, exc.reason, {**exc.details, "dataset": ds.name, "profile": profile.to_dict()})
    except dem_reader.RasterReadError as exc:
        raise ApiError(str(exc), code="DEM_READ_ERROR", status_code=500) from exc

    result.update(
        profile=profile.to_dict(),
        dataset={"id": ds.id, "name": ds.name, "resolution_m": ds.resolution_meters, "vertical_datum": ds.vertical_datum, "source": ds.source},
        query={"crs": crs_id, "latitude_convention": lat_conv, "planet": planet},
        hazards_considered=len(hazards),
        disclaimer=DISCLAIMER,
    )
    route = Route.objects.create(
        mission_id=v.get("mission"), dataset=ds, profile=profile.id, status=result["status"],
        request=request.data, result=result, distance_m=result["route"]["distance_m"],
        unknown_terrain_fraction=result["route"]["unknown_terrain_fraction"],
    )
    return Response({"id": route.id, **result}, status=status.HTTP_201_CREATED)


@api_view(["GET", "DELETE"])
def detail(request, pk: int):
    route = Route.objects.filter(pk=pk).first()
    if not route:
        raise ApiError("Route not found", code="NOT_FOUND", status_code=404)
    if request.method == "DELETE":
        route.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    return Response({"id": route.id, "created_at": route.created_at, **route.result})


@api_view(["GET"])
def route_list(request):
    qs = Route.objects.all()
    if request.query_params.get("mission", "").isdigit():
        qs = qs.filter(mission_id=int(request.query_params["mission"]))
    return Response([
        {"id": r.id, "profile": r.profile, "status": r.status, "distance_m": r.distance_m,
         "unknown_terrain_fraction": r.unknown_terrain_fraction, "mission": r.mission_id, "created_at": r.created_at}
        for r in qs[:200]
    ])


@api_view(["GET"])
def profiles(request):
    return Response([p.to_dict() for p in PROFILES.values()])
