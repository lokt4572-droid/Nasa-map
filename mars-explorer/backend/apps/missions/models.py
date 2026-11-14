from django.db import models

from apps.core.models import MarsPoint


class Mission(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        ABORTED = "ABORTED", "Aborted"

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    # No real astronaut positioning hardware is connected. Missions flagged demo_mode are
    # exercises with manually entered positions and must be labelled DEMO in the UI.
    demo_mode = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class Waypoint(MarsPoint):
    """Bases, checkpoints and points of interest belonging to a mission."""

    class Kind(models.TextChoices):
        BASE = "BASE", "Base"
        CHECKPOINT = "CHECKPOINT", "Checkpoint"
        LANDING_SITE = "LANDING_SITE", "Landing site"
        POI = "POI", "Point of interest"

    mission = models.ForeignKey(Mission, related_name="waypoints", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CHECKPOINT)
    order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["mission_id", "order", "id"]

    def __str__(self) -> str:
        return f"{self.kind} {self.name}"
