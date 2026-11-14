from rest_framework import serializers, status
from rest_framework.decorators import api_view

from apps.core.coordinates import PointQuerySerializer
from apps.core.exceptions import ApiError


class RoutePlanRequestSerializer(serializers.Serializer):
    start = PointQuerySerializer()
    end = PointQuerySerializer()
    max_slope_deg = serializers.FloatField(min_value=0.0, max_value=90.0, required=False)
    mission = serializers.IntegerField(required=False, min_value=1)


@api_view(["POST"])
def plan(request):
    """Interface placeholder. Input is validated, but no route is computed.

    A route must not be presented as safe until a validated traversability model over
    real DEM data exists. Returns 501 NOT_IMPLEMENTED.
    """
    ser = RoutePlanRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    raise ApiError(
        "Route planning is not implemented yet. No route was computed.",
        code="NOT_IMPLEMENTED",
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        details={"accepted_request": ser.validated_data},
    )
