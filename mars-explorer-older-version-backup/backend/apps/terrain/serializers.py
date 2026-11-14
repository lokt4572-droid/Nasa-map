from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import TerrainAnalysis, ElevationProfile


class TerrainAnalysisSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = TerrainAnalysis
        geo_field = "aoi"
        fields = ["id", "name", "analysis_type", "dataset", "parameters",
                  "statistics", "status", "error_message", "created_at", "completed_at"]


class ElevationProfileSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = ElevationProfile
        geo_field = "path"
        fields = ["id", "name", "dataset", "sample_count", "elevations", "distances",
                  "min_elevation", "max_elevation", "total_gain", "total_loss", "created_at"]
