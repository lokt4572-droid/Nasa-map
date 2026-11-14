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
            "radius_m", "description", "reference_layer", "reported_by", "observed_at",
            "lon_east_deg", "lat_deg", "crs", "latitude_convention", "client_id", "version", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "version", "created_at", "updated_at"]

    def validate_title(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Title must not be blank")
        return value
