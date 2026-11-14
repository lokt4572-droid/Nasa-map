"""Hazard models for MARS EXPLORER."""
from django.contrib.gis.db import models
from django.conf import settings


class HazardType(models.TextChoices):
    SLOPE = "slope", "Steep Slope"
    ROCKFALL = "rockfall", "Rockfall Zone"
    DUST_STORM = "dust_storm", "Dust Storm Prone"
    CRATER = "crater", "Crater / Pit"
    SAND_TRAP = "sand_trap", "Sand Trap / Dune Field"
    RADIATION = "radiation", "High Radiation"
    TEMPERATURE = "temperature", "Extreme Temperature"
    COMMUNICATION = "communication", "Communication Blackout"
    CUSTOM = "custom", "Custom Hazard"


class Hazard(models.Model):
    """Hazard area on Mars."""
    name = models.CharField(max_length=100)
    hazard_type = models.CharField(max_length=20, choices=HazardType.choices)
    severity = models.PositiveIntegerField(help_text="1-5 scale", default=1)
    location = models.PolygonField(srid=4326, help_text="Hazard zone boundary")
    center_point = models.PointField(srid=4326, null=True, blank=True)
    description = models.TextField(blank=True)
    elevation_min = models.FloatField(null=True, blank=True)
    elevation_max = models.FloatField(null=True, blank=True)
    slope_max = models.FloatField(null=True, blank=True, help_text="Maximum slope in degrees")
    is_active = models.BooleanField(default=True)
    detected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="detected_hazards")
    detected_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="verified_hazards")
    verified_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-detected_at"]
        verbose_name = "Hazard"
        verbose_name_plural = "Hazards"

    def __str__(self):
        return f"{self.get_hazard_type_display()} - {self.name}"

    def save(self, *args, **kwargs):
        if self.location and not self.center_point:
            self.center_point = self.location.centroid
        super().save(*args, **kwargs)


class HazardReport(models.Model):
    """User-submitted hazard reports."""
    STATUS_CHOICES = [
        ("pending", "Pending Review"),
        ("confirmed", "Confirmed"),
        ("rejected", "Rejected"),
        ("investigating", "Under Investigation"),
    ]

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hazard_reports")
    hazard = models.ForeignKey(Hazard, on_delete=models.CASCADE, related_name="reports", null=True, blank=True)
    location = models.PointField(srid=4326)
    description = models.TextField()
    severity_estimate = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    image = models.ImageField(upload_to="hazard_reports/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_reports")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Hazard Report"
        verbose_name_plural = "Hazard Reports"

    def __str__(self):
        return f"Report by {self.reporter} - {self.status}"
