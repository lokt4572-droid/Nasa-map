"""Optional AI endpoints (all under /api/v1/ai/).

GET  status/                 provider, availability, perception status
POST interpret/              {"instruction"} -> validated RouteConstraints (no route)
POST plan/                   {"instruction", "start", "end", "waypoints"?, "mission"?} -> deterministic route
                             planned with the validated constraints, plus an explanation
POST explain/                {"route_id"} -> explanation of a stored route result
POST perception/detections/  ingest detections of an external validated model (operator-enabled)
"""
from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.coordinates import PointQuerySerializer
from apps.core.exceptions import ApiError
from apps.hazards.models import Hazard
from apps.routing.models import Route
from apps.routing.services import route_service
from apps.routing.views import RoutePlanRequestSerializer

from .models import AiInteraction
from .providers import get_provider
from .providers.base import ProviderError
from .services import mission_interpreter, perception, route_assistant


@api_view(["GET"])
def ai_status(request):
    try:
        p = get_provider()
    except ProviderError as exc:
        return Response({"assistant": {"status": "MISCONFIGURED", "reason": str(exc)}, "perception": perception.status()})
    if p is None:
        assistant = {"status": "DISABLED", "reason": "AI_PROVIDER=none"}
    else:
        ok, why = p.available()
        assistant = {"status": "AVAILABLE" if ok else "UNAVAILABLE", "reason": why or None, **p.describe()}
    return Response({
        "assistant": assistant,
        "perception": perception.status(),
        "route_engine": "deterministic A* on the DEM; works with or without AI",
        "note": "AI interprets preferences and explains results. It never writes route geometry or DEM values.",
    })


class InterpretSerializer(serializers.Serializer):
    instruction = serializers.CharField(max_length=mission_interpreter.MAX_INSTRUCTION_CHARS, allow_blank=False, trim_whitespace=True)


@api_view(["POST"])
def interpret(request):
    ser = InterpretSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    out = mission_interpreter.interpret(ser.validated_data["instruction"])
    return Response(out, status=200 if out["accepted"] else 422)


class AiPlanSerializer(serializers.Serializer):
    instruction = serializers.CharField(max_length=mission_interpreter.MAX_INSTRUCTION_CHARS)
    start = PointQuerySerializer()
    end = PointQuerySerializer()
    waypoints = PointQuerySerializer(many=True, required=False, default=list)
    mission = serializers.IntegerField(required=False, min_value=1)
    terrain_source = serializers.ChoiceField(choices=["local", "auto"], default="local")


@api_view(["POST"])
def ai_plan(request):
    ser = AiPlanSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    interp = mission_interpreter.interpret(ser.validated_data["instruction"])
    if not interp["accepted"]:
        return Response({"interpretation": interp, "route": None, "calculation_status": "NOT_STARTED"}, status=422)
    # Points come from the request only; the assistant's output contains no coordinates (validated).
    body = {k: request.data[k] for k in ("start", "end", "waypoints", "mission") if k in request.data}
    body.update(interp["plan_fields"], terrain_source=ser.validated_data["terrain_source"])
    plan_ser = RoutePlanRequestSerializer(data=body)
    plan_ser.is_valid(raise_exception=True)
    resp = route_service.plan_request(plan_ser.validated_data, body)
    data = dict(resp.data)
    route_id = data.get("id")
    if route_id:
        AiInteraction.objects.filter(pk=interp["interaction_id"]).update(route_id=route_id)
    data["ai"] = {"interpretation": interp, "explanation": route_assistant.explain(data, route_id)}
    return Response(data, status=resp.status_code)


class ExplainSerializer(serializers.Serializer):
    route_id = serializers.IntegerField(min_value=1)


@api_view(["POST"])
def explain(request):
    ser = ExplainSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    route = Route.objects.filter(pk=ser.validated_data["route_id"]).first()
    if not route:
        raise ApiError("Route not found", code="NOT_FOUND", status_code=404)
    return Response(route_assistant.explain(route.result, route.id))


class DetectionSerializer(serializers.Serializer):
    detection_class = serializers.ChoiceField(choices=sorted(perception.DETECTION_CLASSES))
    lon_east_deg = serializers.FloatField(min_value=-180.0, max_value=360.0)
    lat_deg = serializers.FloatField(min_value=-90.0, max_value=90.0)
    radius_m = serializers.FloatField(min_value=0.0, max_value=100_000.0)
    confidence = serializers.FloatField(min_value=0.0, max_value=1.0)
    planet = serializers.ChoiceField(choices=["MARS", "MOON", "MERCURY", "EARTH"])
    crs = serializers.CharField(max_length=200)
    source_image_id = serializers.CharField(max_length=200)
    source_image_resolution_m = serializers.FloatField(min_value=0.0, max_value=100_000.0)
    observation_date = serializers.DateField()
    model_name = serializers.CharField(max_length=120)
    model_version = serializers.CharField(max_length=60)
    validation_status = serializers.ChoiceField(choices=sorted(perception.VALIDATION_STATES))
    image_geometry = serializers.JSONField(required=False)


@api_view(["POST"])
def ingest_detections(request):
    st = perception.status()
    if not st["ingest_enabled"]:
        return Response({"status": "UNAVAILABLE", "perception": st}, status=503)
    ser = DetectionSerializer(data=request.data, many=True)
    ser.is_valid(raise_exception=True)
    created = []
    for d in ser.validated_data:
        lon = ((d["lon_east_deg"] + 180.0) % 360.0) - 180.0
        hz = Hazard.objects.create(
            title=f"{d['detection_class'].replace('_', ' ').title()} (model detection)",
            hazard_type=d["detection_class"], severity=Hazard.Severity.UNKNOWN,
            source=Hazard.Source.IMAGERY_INTERPRETATION, verification=Hazard.Verification.UNVERIFIED,
            observation_class=Hazard.ObservationClass.MODEL_ESTIMATED,
            observation_method=f"{d['model_name']} {d['model_version']} on {d['source_image_id']}",
            confidence=d["confidence"], planet=d["planet"], lon_east_deg=lon, lat_deg=d["lat_deg"], crs=d["crs"],
            radius_m=d["radius_m"], observed_at=None,
            detection={k: (str(v) if k == "observation_date" else v) for k, v in d.items()},
        )
        created.append(hz.id)
        AiInteraction.objects.create(kind=AiInteraction.Kind.PERCEPTION, provider="external-model", model=d["model_name"],
                                     model_version=d["model_version"], input_ref=f"image:{d['source_image_id']}",
                                     structured_result={"hazard_id": hz.id, "class": d["detection_class"]},
                                     validation={"stored_as": "MODEL_ESTIMATED/UNVERIFIED", "model_validation": d["validation_status"]},
                                     accepted=True, confidence=d["confidence"])
    return Response({"created": created, "stored_as": "MODEL_ESTIMATED / UNVERIFIED",
                     "note": "Detections are uncertain observations. They do not block routes until a person confirms them."},
                    status=status.HTTP_201_CREATED)
