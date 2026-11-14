"""Shared serializer pieces for explicitly-labelled Mars coordinates."""
from __future__ import annotations

from rest_framework import serializers

from services.mars_coordinates import (
    TREK_DECLARED_CRS,
    LatitudeConvention,
    UnknownCRSError,
    normalize_lon_180,
    resolve_crs,
)


class CoordinateFieldsMixin(serializers.Serializer):
    """lon_east_deg / lat_deg plus CRS and latitude convention, validated together."""

    lon_east_deg = serializers.FloatField(min_value=-180.0, max_value=360.0)
    lat_deg = serializers.FloatField(min_value=-90.0, max_value=90.0)
    crs = serializers.CharField(max_length=200, default=TREK_DECLARED_CRS)
    latitude_convention = serializers.ChoiceField(
        choices=[c.value for c in LatitudeConvention], default=LatitudeConvention.AS_DECLARED_BY_SOURCE.value
    )

    def validate_crs(self, value: str) -> str:
        try:
            resolve_crs(value)
        except UnknownCRSError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value

    def validate_lon_east_deg(self, value: float) -> float:
        return normalize_lon_180(value)


class PointQuerySerializer(CoordinateFieldsMixin):
    pass
