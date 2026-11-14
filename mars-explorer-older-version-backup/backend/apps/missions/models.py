"""Mission models for MARS EXPLORER."""
from django.contrib.gis.db import models
from django.conf import settings


class BaseCamp(models.Model):
    """Astronaut base camp on Mars."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    location = models.PointField(srid=4326)  # WGS84 / Mars equivalent
    elevation = models.FloatField(null=True, blank=True, help_text="Elevation in meters")
    established_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    crew_capacity = models.PositiveIntegerField(default=4)
    power_kw = models.FloatField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="base_camps")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Base Camp"
        verbose_name_plural = "Base Camps"

    def __str__(self):
        return self.name


class Waypoint(models.Model):
    """Navigation waypoint on Mars."""
    WAYPOINT_TYPES = [
        ("landing", "Landing Site"),
        ("science", "Science Target"),
        ("depot", "Supply Depot"),
        ("hazard", "Hazard Area"),
        ("camp", "Camp Location"),
        ("custom", "Custom"),
    ]

    name = models.CharField(max_length=100)
    waypoint_type = models.CharField(max_length=20, choices=WAYPOINT_TYPES, default="custom")
    location = models.PointField(srid=4326)
    elevation = models.FloatField(null=True, blank=True)
    description = models.TextField(blank=True)
    is_critical = models.BooleanField(default=False)
    mission = models.ForeignKey("Mission", on_delete=models.CASCADE, related_name="waypoints", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Waypoint"
        verbose_name_plural = "Waypoints"

    def __str__(self):
        return f"{self.name} ({self.get_waypoint_type_display()})"


class Mission(models.Model):
    """Mars exploration mission."""
    STATUS_CHOICES = [
        ("planning", "Planning"),
        ("active", "Active"),
        ("completed", "Completed"),
        ("aborted", "Aborted"),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="planning")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    primary_base = models.ForeignKey(BaseCamp, on_delete=models.SET_NULL, null=True, blank=True, related_name="missions")
    crew = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="missions", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_missions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Mission"
        verbose_name_plural = "Missions"

    def __str__(self):
        return self.name


class ExpeditionLog(models.Model):
    """Daily expedition log entries."""
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name="logs")
    date = models.DateField()
    sol = models.PositiveIntegerField(help_text="Martian sol number")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=200)
    summary = models.TextField()
    location = models.PointField(srid=4326, null=True, blank=True)
    weather = models.JSONField(default=dict, blank=True, help_text="Temperature, pressure, wind, dust")
    achievements = models.TextField(blank=True)
    issues = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-sol"]
        unique_together = [["mission", "sol"]]
        verbose_name = "Expedition Log"
        verbose_name_plural = "Expedition Logs"

    def __str__(self):
        return f"{self.mission.name} - Sol {self.sol}: {self.title}"
