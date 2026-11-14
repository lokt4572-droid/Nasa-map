from rest_framework import viewsets

from .models import Hazard
from .serializers import HazardSerializer


class HazardViewSet(viewsets.ModelViewSet):
    serializer_class = HazardSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Hazard.objects.all()
        params = self.request.query_params
        mission = params.get("mission")
        if mission is not None:
            qs = qs.filter(mission_id=int(mission)) if mission.isdigit() else qs.none()
        for field in ("hazard_type", "severity", "verification"):
            value = params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        return qs
