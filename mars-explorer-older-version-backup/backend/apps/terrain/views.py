from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework_gis.filters import DistanceToPointFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from .models import TerrainAnalysis, ElevationProfile
from .serializers import TerrainAnalysisSerializer, ElevationProfileSerializer


class TerrainAnalysisViewSet(viewsets.ModelViewSet):
    queryset = TerrainAnalysis.objects.select_related("dataset", "created_by").all()
    serializer_class = TerrainAnalysisSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, DistanceToPointFilter, OrderingFilter, SearchFilter]
    filterset_fields = ["analysis_type", "status"]
    search_fields = ["name"]
    ordering_fields = ["created_at", "analysis_type"]
    distance_filter_field = "aoi"
    distance_filter_convert_meters = True

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, status="pending")

    @action(detail=True, methods=["post"])
    def execute(self, request, pk=None):
        """Trigger analysis execution (async via task queue in production)."""
        analysis = self.get_object()
        analysis.status = "processing"
        analysis.save(update_fields=["status"])
        # In production, this would trigger a Celery task
        # For now, return success with info
        return Response({
            "status": "queued",
            "message": "Analysis queued. In production, this would run asynchronously.",
            "analysis_id": analysis.id
        })


class ElevationProfileViewSet(viewsets.ModelViewSet):
    queryset = ElevationProfile.objects.select_related("dataset", "created_by").all()
    serializer_class = ElevationProfileSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, DistanceToPointFilter, OrderingFilter, SearchFilter]
    filterset_fields = ["dataset"]
    search_fields = ["name"]
    ordering_fields = ["created_at"]
    distance_filter_field = "path"
    distance_filter_convert_meters = True

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
