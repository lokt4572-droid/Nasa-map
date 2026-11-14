"""Serializers for Missions app."""
from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import BaseCamp, Waypoint, Mission, ExpeditionLog


class BaseCampSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = BaseCamp
        geo_field = "location"
        fields = ["id", "name", "description", "elevation", "established_date", 
                  "is_active", "crew_capacity", "power_kw", "created_at", "updated_at"]


class WaypointSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Waypoint
        geo_field = "location"
        fields = ["id", "name", "waypoint_type", "elevation", "description", 
                  "is_critical", "mission", "created_at"]


class MissionSerializer(GeoFeatureModelSerializer):
    waypoints = WaypointSerializer(many=True, read_only=True)
    primary_base = serializers.StringRelatedField(read_only=True)
    crew_count = serializers.SerializerMethodField()

    class Meta:
        model = Mission
        geo_field = "primary_base__location"
        fields = ["id", "name", "description", "status", "start_date", "end_date",
                  "primary_base", "waypoints", "crew_count", "created_at", "updated_at"]

    def get_crew_count(self, obj):
        return obj.crew.count()


class MissionListSerializer(GeoFeatureModelSerializer):
    """Lightweight serializer for mission lists."""
    crew_count = serializers.SerializerMethodField()

    class Meta:
        model = Mission
        geo_field = "primary_base__location"
        fields = ["id", "name", "status", "start_date", "end_date", "primary_base", "crew_count"]

    def get_crew_count(self, obj):
        return obj.crew.count()


class ExpeditionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpeditionLog
        fields = ["id", "mission", "date", "sol", "author", "title", "summary",
                  "location", "weather", "achievements", "issues", "created_at"]
        read_only_fields = ["author", "created_at"]
