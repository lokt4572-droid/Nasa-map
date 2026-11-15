from django.db import models


class WeatherSnapshot(models.Model):
    """Persistent cache of provider responses. A cached answer is always labelled with
    its retrieval time; it is never presented as 'current' after it expires."""

    key = models.CharField(max_length=200, unique=True)
    provider = models.CharField(max_length=40)
    data_type = models.CharField(max_length=40)
    payload = models.JSONField()
    retrieved_at = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)

    def __str__(self) -> str:
        return f"{self.provider} {self.key}"
