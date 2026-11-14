import datetime as dt

from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.exceptions import ApiError
from services import http_client

from . import services


class LatLonSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90.0, max_value=90.0)
    lon = serializers.FloatField(min_value=-180.0, max_value=180.0)


def _latlon(request):
    ser = LatLonSerializer(data=request.query_params)
    ser.is_valid(raise_exception=True)
    return ser.validated_data["lat"], ser.validated_data["lon"]


def _provider_call(fn, *args):
    try:
        return fn(*args)
    except http_client.ProviderTimeout as exc:
        raise ApiError(str(exc), code=exc.code, status_code=504, details={"provider": exc.provider}) from exc
    except http_client.ProviderHTTPError as exc:
        raise ApiError(str(exc), code=exc.code, status_code=502, details={"provider": exc.provider, "upstream_status": exc.status}) from exc
    except http_client.ProviderError as exc:
        raise ApiError(str(exc), code=exc.code, status_code=502, details={"provider": exc.provider}) from exc


@api_view(["GET"])
def current(request):
    return Response(_provider_call(services.current, *_latlon(request)))


@api_view(["GET"])
def forecast(request):
    return Response(_provider_call(services.forecast, *_latlon(request)))


@api_view(["GET"])
def historical(request):
    lat, lon = _latlon(request)
    today = dt.date.today()
    try:
        end = services.parse_date(request.query_params.get("end") or (today - dt.timedelta(days=7)).isoformat(), "end")
        start = services.parse_date(request.query_params.get("start") or (end - dt.timedelta(days=29)).isoformat(), "start")
    except ValueError as exc:
        raise ApiError(str(exc), code="VALIDATION_ERROR") from exc
    try:
        return Response(_provider_call(services.historical, lat, lon, start, end))
    except ValueError as exc:
        raise ApiError(str(exc), code="VALIDATION_ERROR") from exc


@api_view(["GET"])
def weather_status(request):
    return Response(services.status())
