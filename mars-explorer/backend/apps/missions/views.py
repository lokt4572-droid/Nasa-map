from rest_framework import viewsets

from apps.core.sync import SyncViewSetMixin

from .models import Mission, Waypoint
from .serializers import MissionSerializer, WaypointSerializer


class MissionViewSet(SyncViewSetMixin, viewsets.ModelViewSet):
    queryset = Mission.objects.prefetch_related("waypoints").all()
    serializer_class = MissionSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]


class WaypointViewSet(viewsets.ModelViewSet):
    serializer_class = WaypointSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Waypoint.objects.all()
        mission = self.request.query_params.get("mission")
        if mission is not None:
            if not mission.isdigit():
                return qs.none()
            qs = qs.filter(mission_id=int(mission))
        return qs
