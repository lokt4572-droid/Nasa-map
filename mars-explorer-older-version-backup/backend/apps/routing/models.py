"""Route planning models for MARS EXPLORER."""
from django.contrib.gis.db import models
from django.conf import settings


class Route(models.Model):
    """Planned route on Mars."""
    ROUTE_TYPES = [
        ("driving", "Rover Driving"),
        ("walking", "EVA Walking"),
        ("flight", "Aerial/Direct"),
        ("emergency", "Emergency Return"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("planned", "Planned"),
        ("approved", "Approved"),
        ("active", "Active"),
        ("completed", "Completed"),
        ("aborted", "Aborted"),
    ]

    name = models.CharField(max_length=200)
    route_type = models.CharField(max_length=20, choices=ROUTE_TYPES, default="driving")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    path = models.LineStringField(srid=4326)
    waypoints = models.JSONField(default=list, help_text="Ordered list of waypoint coordinates")
    mission = models.ForeignKey("missions.Mission", on_delete=models.SET_NULL, null=True, blank=True, related_name="routes")
    total_distance_km = models.FloatField(null=True, blank=True)
    estimated_duration_hours = models.FloatField(null=True, blank=True)
    max_slope = models.FloatField(null=True, blank=True, help_text="Maximum slope in degrees")
    elevation_gain = models.FloatField(null=True, blank=True)
    elevation_loss = models.FloatField(null=True, blank=True)
    min_elevation = models.FloatField(null=True, blank=True)
    max_elevation = models.FloatField(null=True, blank=True)
    avoids_hazards = models.BooleanField(default=False)
    hazard_buffer_meters = models.FloatField(default=100)
    energy_estimate_kwh = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_routes")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_routes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Route"
        verbose_name_plural = "Routes"

    def __str__(self):
        return f"{self.name} ({self.get_route_type_display()})"


class RouteSegment(models.Model):
    """Individual segment of a route."""
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="segments")
    order = models.PositiveIntegerField()
    start_point = models.PointField(srid=4326)
    end_point = models.PointField(srid=4326)
    distance_km = models.FloatField()
    slope = models.FloatField(help_text="Average slope in degrees")
    elevation_start = models.FloatField()
    elevation_end = models.FloatField()
    estimated_time_hours = models.FloatField()
    terrain_type = models.CharField(max_length=50, blank=True)
    hazard_crossings = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["route", "order"]
        verbose_name = "Route Segment"
        verbose_name_plural = "Route Segments"

    def __str__(self):
        return f"{self.route.name} - Segment {self.order}"
