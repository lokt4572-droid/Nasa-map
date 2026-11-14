from django.db import models


class Route(models.Model):
    """A computed route. Only routes that the planner actually found are stored."""

    mission = models.ForeignKey("missions.Mission", null=True, blank=True, on_delete=models.SET_NULL, related_name="routes")
    dataset = models.ForeignKey("datasets.Dataset", null=True, blank=True, on_delete=models.SET_NULL, related_name="routes")
    profile = models.CharField(max_length=20)
    status = models.CharField(max_length=40)
    request = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    distance_m = models.FloatField(null=True, blank=True)
    unknown_terrain_fraction = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Route {self.pk} ({self.profile}, {self.status})"
