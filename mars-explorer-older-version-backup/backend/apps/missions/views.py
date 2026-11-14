"""Views for Missions app."""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework_gis.filters import DistanceToPointFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from .models import BaseCamp, Waypoint, Mission, ExpeditionLog
from .serializers import (
    BaseCampSerializer, WaypointSerializer,
    MissionSerializer, MissionListSerializer, ExpeditionLogSerializer
)


class BaseCampViewSet(viewsets.ModelViewSet):
    queryset = BaseCamp.objects.select_related("created_by").all()
    serializer_class = BaseCampSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, DistanceToPointFilter, OrderingFilter, SearchFilter]
    filterset_fields = ["is_active"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "established_date", "elevation"]
    distance_filter_field = "location"
    distance_filter_convert_meters = True

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class WaypointViewSet(viewsets.ModelViewSet):
    queryset = Waypoint.objects.select_related("mission").all()
    serializer_class = WaypointSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, DistanceToPointFilter, OrderingFilter, SearchFilter]
    filterset_fields = ["waypoint_type", "is_critical", "mission"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "elevation"]
    distance_filter_field = "location"
    distance_filter_convert_meters = True


class MissionViewSet(viewsets.ModelViewSet):
    queryset = Mission.objects.select_related("primary_base", "created_by").prefetch_related("waypoints", "crew").all()
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = ["status"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "start_date", "created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return MissionListSerializer
        return MissionSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["get"])
    def route(self, request, pk=None):
        """Get optimized route for mission waypoints."""
        mission = self.get_object()
        waypoints = mission.waypoints.all().order_by("id")
        if not waypoints.exists():
            return Response({"error": "No waypoints defined"}, status=status.HTTP_400_BAD_REQUEST)
        
        coords = [(wp.location.x, wp.location.y) for wp in waypoints]
        return Response({
            "mission": mission.name,
            "waypoint_count": len(coords),
            "coordinates": coords,
            "total_distance_km": None,  # To be calculated by routing service
        })


class ExpeditionLogViewSet(viewsets.ModelViewSet):
    queryset = ExpeditionLog.objects.select_related("mission", "author").all()
    serializer_class = ExpeditionLogSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = ["mission"]
    search_fields = ["title", "summary", "achievements"]
    ordering_fields = ["date", "sol", "created_at"]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
