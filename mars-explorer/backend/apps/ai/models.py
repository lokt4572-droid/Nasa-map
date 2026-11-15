from django.db import models


class AiInteraction(models.Model):
    """Audit record of every AI call: what went in (by reference), what came out, and whether it
    passed validation. Kept even when the output was rejected."""

    class Kind(models.TextChoices):
        INTERPRET = "INTERPRET", "Mission instruction -> route constraints"
        EXPLAIN = "EXPLAIN", "Route result -> explanation"
        PERCEPTION = "PERCEPTION", "Image -> hazard detections"

    kind = models.CharField(max_length=12, choices=Kind.choices)
    provider = models.CharField(max_length=40)
    model = models.CharField(max_length=120, blank=True)
    model_version = models.CharField(max_length=120, blank=True)
    input_ref = models.CharField(max_length=120, help_text="sha256 of the input text/JSON (inputs are not stored verbatim)")
    route = models.ForeignKey("routing.Route", null=True, blank=True, on_delete=models.SET_NULL, related_name="ai_interactions")
    structured_result = models.JSONField(default=dict, blank=True)
    validation = models.JSONField(default=dict, blank=True)
    accepted = models.BooleanField(default=False)
    confidence = models.FloatField(null=True, blank=True, help_text="Only where meaningful; an LLM's self-rating is not recorded as confidence")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
