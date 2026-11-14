"""Terrain analysis models for MARS EXPLORER."""
from django.contrib.gis.db import models
from django.conf import settings


class TerrainAnalysis(models.Model):
    """Stored terrain analysis results."""
    ANALYSIS_TYPES = [
        ("slope", "Slope Analysis"),
        ("aspect", "Aspect Analysis"),
        ("hillshade", "Hillshade"),
        ("roughness", "Surface Roughness"),
        ("curvature", "Curvature"),
        ("viewshed", "Viewshed Analysis"),
        ("profile", "Elevation Profile"),
        ("contour", "Contour Generation"),
    ]

    name = models.CharField(max_length=200)
    analysis_type = models.CharField(max_length=20, choices=ANALYSIS_TYPES)
    dataset = models.ForeignKey("datasets.Dataset", on_delete=models.CASCADE, related_name="analyses")
    aoi = models.PolygonField(srid=4326, help_text="Area of interest")
    parameters = models.JSONField(default=dict, blank=True)
    result_file = models.CharField(max_length=500, blank=True, help_text="Path to result file")
    statistics = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, default="pending", choices=[
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ])
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="terrain_analyses")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Terrain Analysis"
        verbose_name_plural = "Terrain Analyses"

    def __str__(self):
        return f"{self.name} ({self.get_analysis_type_display()})"


class ElevationProfile(models.Model):
    """Elevation profile along a path."""
    name = models.CharField(max_length=200)
    path = models.LineStringField(srid=4326)
    dataset = models.ForeignKey("datasets.Dataset", on_delete=models.CASCADE, related_name="profiles")
    sample_count = models.PositiveIntegerField(default=100)
    elevations = models.JSONField(default=list, help_text="List of elevation values in meters")
    distances = models.JSONField(default=list, help_text="Cumulative distances in meters")
    min_elevation = models.FloatField(null=True, blank=True)
    max_elevation = models.FloatField(null=True, blank=True)
    total_gain = models.FloatField(null=True, blank=True)
    total_loss = models.FloatField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Elevation Profile"
        verbose_name_plural = "Elevation Profiles"

    def __str__(self):
        return self.name
