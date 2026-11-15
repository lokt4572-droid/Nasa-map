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
from .models import Route
from .profiles import PROFILES
from .services import pathfinder, route_service
from .services.route_service import DISCLAIMER, planning_scope  # noqa: F401 - re-exported for callers

logger = logging.getLogger("mars.routing")


class RoutePlanRequestSerializer(serializers.Serializer):
    start = PointQuerySerializer()
    end = PointQuerySerializer()
    waypoints = PointQuerySerializer(many=True, required=False, default=list)
    profile = serializers.ChoiceField(choices=list(PROFILES), default="CONSERVATIVE")
    include_return = serializers.BooleanField(default=True)
    include_alternative = serializers.BooleanField(default=True)
    max_slope_deg = serializers.FloatField(min_value=1.0, max_value=45.0, required=False)
    unknown_data_policy = serializers.ChoiceField(choices=["REJECT", "ALLOW_MARKED"], required=False)
    mission = serializers.IntegerField(required=False, min_value=1)
    dataset = serializers.IntegerField(required=False, min_value=1)
    # v0.4 mission configuration (all optional; they can only make the plan more restrictive)
    terrain_source = serializers.ChoiceField(choices=["local", "auto"], default="local")
    max_roughness_m = serializers.FloatField(min_value=0.0, max_value=1e5, required=False)
    max_local_relief_m = serializers.FloatField(min_value=0.0, max_value=1e5, required=False)
    required_resolution_m = serializers.FloatField(min_value=0.01, max_value=1e6, required=False)
    hazard_buffer_m = serializers.FloatField(min_value=0.0, max_value=1e6, required=False)
    connectivity = serializers.ChoiceField(choices=[4, 8], required=False)
    prefer_lower_roughness = serializers.BooleanField(required=False, default=False)

    def validate_waypoints(self, value):
        if len(value) > 20:
            raise serializers.ValidationError("At most 20 intermediate waypoints")
        return value

    def validate(self, attrs):
        pts = [attrs["start"], *attrs["waypoints"], attrs["end"]]
        if len({(p["crs"], p["latitude_convention"], p["planet"]) for p in pts}) != 1:
            raise serializers.ValidationError("All points must use the same crs, latitude_convention and planet")
        if attrs.get("unknown_data_policy") == "ALLOW_MARKED" and attrs.get("profile", "CONSERVATIVE") != "STANDARD":
            raise serializers.ValidationError(
                {"unknown_data_policy": "Crossing terrain without DEM data is only possible with the STANDARD profile, where it is marked UNVERIFIED"}
            )
        return attrs


@api_view(["POST"])
def plan(request):
    ser = RoutePlanRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    return route_service.plan_request(ser.validated_data, request.data)


@api_view(["POST"])
def alternatives(request):
    """Same as plan/, always with the alternative candidate and the comparison table."""
    ser = RoutePlanRequestSerializer(data={**request.data, "include_alternative": True})
    ser.is_valid(raise_exception=True)
    return route_service.plan_request(ser.validated_data, request.data)


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


class DeriveHazardsSerializer(serializers.Serializer):
    center = PointQuerySerializer()
    radius_m = serializers.FloatField(min_value=50.0, max_value=500_000.0)
    slope_limit_deg = serializers.FloatField(min_value=1.0, max_value=60.0, default=15.0)
    roughness_limit_m = serializers.FloatField(min_value=0.0, max_value=1e5, required=False)
    terrain_source = serializers.ChoiceField(choices=["local", "auto"], default="local")
    dataset = serializers.IntegerField(required=False, min_value=1)


@api_view(["POST"])
def derive_hazards(request):
    """DEM-derived hazard candidates around a point (MODEL_ESTIMATED, not stored)."""
    ser = DeriveHazardsSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    return route_service.derive_hazards_request(ser.validated_data)
