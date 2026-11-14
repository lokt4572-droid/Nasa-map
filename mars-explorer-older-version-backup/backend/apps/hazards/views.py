from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework_gis.filters import DistanceToPointFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from .models import Hazard, HazardReport
from .serializers import HazardSerializer, HazardReportSerializer


class HazardViewSet(viewsets.ModelViewSet):
    queryset = Hazard.objects.select_related("detected_by", "verified_by").all()
    serializer_class = HazardSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, DistanceToPointFilter, OrderingFilter, SearchFilter]
    filterset_fields = ["hazard_type", "severity", "is_active", "verified"]
    search_fields = ["name", "description"]
    ordering_fields = ["detected_at", "severity", "hazard_type"]
    distance_filter_field = "location"
    distance_filter_convert_meters = True

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticatedOrReadOnly])
    def verify(self, request, pk=None):
        hazard = self.get_object()
        hazard.verified = True
        hazard.verified_by = request.user
        from django.utils import timezone
        hazard.verified_at = timezone.now()
        hazard.save(update_fields=["verified", "verified_by", "verified_at"])
        return Response({"status": "verified"})


class HazardReportViewSet(viewsets.ModelViewSet):
    queryset = HazardReport.objects.select_related("reporter", "hazard", "reviewed_by").all()
    serializer_class = HazardReportSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, DistanceToPointFilter, OrderingFilter, SearchFilter]
    filterset_fields = ["status", "hazard"]
    search_fields = ["description"]
    ordering_fields = ["created_at", "severity_estimate"]
    distance_filter_field = "location"
    distance_filter_convert_meters = True

    def perform_create(self, serializer):
        serializer.save(reporter=self.request.user)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticatedOrReadOnly])
    def confirm(self, request, pk=None):
        report = self.get_object()
        report.status = "confirmed"
        report.reviewed_by = request.user
        from django.utils import timezone
        report.reviewed_at = timezone.now()
        report.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        # Create hazard if not exists
        if not report.hazard:
            from .models import Hazard
            hazard = Hazard.objects.create(
                name=f"Reported: {report.description[:50]}",
                hazard_type="custom",
                severity=report.severity_estimate,
                location=report.location.buffer(0.001),  # ~100m buffer
                center_point=report.location,
                description=report.description,
                detected_by=report.reporter,
                verified=True,
                verified_by=request.user,
            )
            report.hazard = hazard
            report.save(update_fields=["hazard"])
        return Response({"status": "confirmed", "hazard_id": report.hazard.id})
