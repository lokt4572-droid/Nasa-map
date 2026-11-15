from rest_framework import serializers

from apps.core.coordinates import CoordinateFieldsMixin
from apps.core.sync import SyncSerializerMixin

from .models import Hazard


class HazardSerializer(SyncSerializerMixin, CoordinateFieldsMixin, serializers.ModelSerializer):
    radius_m = serializers.FloatField(min_value=0.0, max_value=1_000_000.0, required=False, allow_null=True)

    class Meta:
        model = Hazard
        fields = [
            "id", "mission", "title", "hazard_type", "severity", "source", "verification",
            "planet", "observation_class", "observation_method", "confidence", "image_url", "detection",
            "radius_m", "description", "reference_layer", "reported_by", "observed_at",
            "lon_east_deg", "lat_deg", "crs", "latitude_convention", "client_id", "version", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "version", "created_at", "updated_at"]

    confidence = serializers.FloatField(min_value=0.0, max_value=1.0, required=False, allow_null=True)

    def validate_planet(self, value: str) -> str:
        from services.planet_registry import UnknownPlanetError, get_planet

        try:
            return get_planet(value.upper()).id
        except UnknownPlanetError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # A model's output cannot arrive already "confirmed": confirmation is a separate human step.
        if not self.instance and attrs.get("observation_class") == "MODEL_ESTIMATED" and attrs.get("verification") == "CONFIRMED":
            raise serializers.ValidationError({"verification": "Model-estimated hazards are created UNVERIFIED; confirm them afterwards"})
        return attrs

    def validate_title(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Title must not be blank")
        return value
