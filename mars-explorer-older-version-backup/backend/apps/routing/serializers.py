from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import Route, RouteSegment


class RouteSegmentSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = RouteSegment
        geo_field = None  # Segments use start/end points, not a single geometry
        fields = ["id", "order", "start_point", "end_point", "distance_km",
                  "slope", "elevation_start", "elevation_end", "estimated_time_hours",
                  "terrain_type", "hazard_crossings"]


class RouteSerializer(GeoFeatureModelSerializer):
    segments = RouteSegmentSerializer(many=True, read_only=True)

    class Meta:
        model = Route
        geo_field = "path"
        fields = ["id", "name", "route_type", "status", "mission", "waypoints",
                  "total_distance_km", "estimated_duration_hours", "max_slope",
                  "elevation_gain", "elevation_loss", "min_elevation", "max_elevation",
                  "avoids_hazards", "hazard_buffer_meters", "energy_estimate_kwh",
                  "notes", "segments", "created_at", "updated_at", "approved_at"]
        read_only_fields = ["created_by", "approved_by", "approved_at"]


class RouteCreateSerializer(GeoFeatureModelSerializer):
    """Serializer for creating routes with waypoints."""
    class Meta:
        model = Route
        geo_field = "path"
        fields = ["id", "name", "route_type", "mission", "waypoints",
                  "hazard_buffer_meters", "notes"]
