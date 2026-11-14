from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import Hazard, HazardReport


class HazardSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Hazard
        geo_field = "location"
        fields = ["id", "name", "hazard_type", "severity", "description",
                  "elevation_min", "elevation_max", "slope_max",
                  "is_active", "verified", "detected_at", "verified_at", "metadata"]


class HazardReportSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = HazardReport
        geo_field = "location"
        fields = ["id", "hazard", "location", "description", "severity_estimate",
                  "status", "image", "created_at", "reviewed_at"]
        read_only_fields = ["reporter", "status", "reviewed_at", "reviewed_by"]
