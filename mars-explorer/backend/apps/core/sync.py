"""Offline-sync support shared by Mission and Hazard.

* client_id (UUID from the device) makes offline creates idempotent: replaying a create
  returns the existing record instead of a duplicate.
* version is incremented on every update. A PATCH that sends a stale `version` gets
  HTTP 409 CONFLICT with the server copy — the client keeps its local change and asks
  the user; nothing is overwritten silently.
"""
from __future__ import annotations

from django.db import models, transaction
from rest_framework import serializers, status
from rest_framework.response import Response


class SyncFields(models.Model):
    client_id = models.UUIDField(null=True, blank=True, unique=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True


class SyncSerializerMixin(serializers.Serializer):
    client_id = serializers.UUIDField(required=False, allow_null=True)
    version = serializers.IntegerField(read_only=True)


class SyncViewSetMixin:
    def create(self, request, *args, **kwargs):
        cid = request.data.get("client_id") if isinstance(request.data, dict) else None
        if cid:
            existing = self.get_serializer().Meta.model.objects.filter(client_id=cid).first()
            if existing:
                return Response({**self.get_serializer(existing).data, "replayed": True}, status=status.HTTP_200_OK)
        return super().create(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        with transaction.atomic():
            instance = self.get_object()
            sent = request.data.get("version") if isinstance(request.data, dict) else None
            if sent is not None and int(sent) != instance.version:
                return Response(
                    {
                        "error": {
                            "code": "CONFLICT",
                            "message": f"Record changed on the server (server version {instance.version}, yours {sent}).",
                            "details": {"server": self.get_serializer(instance).data},
                        }
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            response = super().partial_update(request, *args, **kwargs)
            type(instance).objects.filter(pk=instance.pk).update(version=models.F("version") + 1)
            instance.refresh_from_db()
            response.data = self.get_serializer(instance).data
            return response
