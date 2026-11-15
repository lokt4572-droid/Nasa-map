from django.db import models

from apps.core.models import MarsPoint
from apps.core.sync import SyncFields


class Hazard(MarsPoint, SyncFields):
    """A reported obstacle or potentially hazardous area.

    A report is an observation, not a validated safety assessment. ``verification``
    records whether anyone has confirmed it.
    """

    class HazardType(models.TextChoices):
        CRATER = "CRATER", "Crater / depression"
        STEEP_SLOPE = "STEEP_SLOPE", "Steep slope"
        CLIFF = "CLIFF", "Cliff / scarp"
        BOULDER_FIELD = "BOULDER_FIELD", "Boulder field"
        SOFT_REGOLITH = "SOFT_REGOLITH", "Soft regolith / sand"
        DUNE = "DUNE", "Dune / ripple field"
        DUST = "DUST", "Dust activity"
        ROUGH_TERRAIN = "ROUGH_TERRAIN", "Rough terrain"
        SAND_DUNE = "SAND_DUNE", "Sand dune"
        UNKNOWN_SURFACE = "UNKNOWN_SURFACE", "Unknown surface"
        MISSING_DATA = "MISSING_DATA", "Missing elevation data"
        OTHER = "OTHER", "Other"

    class Severity(models.TextChoices):
        UNKNOWN = "UNKNOWN", "Unknown"
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    class Source(models.TextChoices):
        FIELD_OBSERVATION = "FIELD_OBSERVATION", "Field observation"
        IMAGERY_INTERPRETATION = "IMAGERY_INTERPRETATION", "Imagery interpretation"
        DEM_DERIVED = "DEM_DERIVED", "Derived from DEM"
        OTHER = "OTHER", "Other"

    class ObservationClass(models.TextChoices):
        """How the hazard is known. It is shown with every hazard and decides what the planner does."""
        OBSERVED = "OBSERVED", "Observed (direct observation or measurement)"
        INFERRED = "INFERRED", "Inferred (interpretation of data)"
        USER_REPORTED = "USER_REPORTED", "Reported by a user"
        MODEL_ESTIMATED = "MODEL_ESTIMATED", "Estimated by a model or algorithm"
        UNKNOWN = "UNKNOWN", "Unknown"

    # Unverified reports of these classes never become hard constraints in route planning:
    # an algorithm's output is an uncertain observation until a person confirms it.
    SOFT_CLASSES = ("MODEL_ESTIMATED",)

    class Verification(models.TextChoices):
        UNVERIFIED = "UNVERIFIED", "Unverified"
        CONFIRMED = "CONFIRMED", "Confirmed"
        REJECTED = "REJECTED", "Rejected"

    mission = models.ForeignKey(
        "missions.Mission", related_name="hazards", on_delete=models.SET_NULL, null=True, blank=True
    )
    title = models.CharField(max_length=200)
    hazard_type = models.CharField(max_length=30, choices=HazardType.choices, default=HazardType.OTHER)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.UNKNOWN)
    source = models.CharField(max_length=30, choices=Source.choices, default=Source.IMAGERY_INTERPRETATION)
    verification = models.CharField(max_length=12, choices=Verification.choices, default=Verification.UNVERIFIED)
    planet = models.CharField(max_length=10, default="MARS", db_index=True)
    observation_class = models.CharField(max_length=20, choices=ObservationClass.choices, default=ObservationClass.USER_REPORTED)
    observation_method = models.CharField(max_length=200, blank=True, help_text="e.g. field visit, HiRISE image interpretation, DEM slope threshold")
    confidence = models.FloatField(null=True, blank=True, help_text="0..1 as stated by the reporter or model; not a scientific probability")
    image_url = models.URLField(max_length=500, blank=True, help_text="Optional link to an image of the observation")
    detection = models.JSONField(default=dict, blank=True, help_text="For model output: model, version, source image, resolution, validation status")
    radius_m = models.FloatField(null=True, blank=True, help_text="Approximate radius of the area, metres")
    description = models.TextField(blank=True)
    reference_layer = models.CharField(max_length=200, blank=True, help_text="Map layer used when the hazard was picked")
    reported_by = models.CharField(max_length=120, blank=True)
    observed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.hazard_type})"
