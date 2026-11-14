from rest_framework import serializers

from apps.core.coordinates import CoordinateFieldsMixin

from .models import Mission, Waypoint


class WaypointSerializer(CoordinateFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = Waypoint
        fields = [
            "id", "mission", "name", "kind", "order", "notes",
            "lon_east_deg", "lat_deg", "crs", "latitude_convention", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class MissionSerializer(serializers.ModelSerializer):
    waypoints = WaypointSerializer(many=True, read_only=True)
    hazard_count = serializers.IntegerField(source="hazards.count", read_only=True)

    class Meta:
        model = Mission
        fields = ["id", "name", "description", "status", "demo_mode", "waypoints", "hazard_count", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name must not be blank")
        return value
