from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework_gis.filters import DistanceToPointFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from django.contrib.gis.geos import LineString
from .models import Route, RouteSegment
from .serializers import RouteSerializer, RouteCreateSerializer, RouteSegmentSerializer


class RouteViewSet(viewsets.ModelViewSet):
    queryset = Route.objects.select_related("mission", "created_by", "approved_by").prefetch_related("segments").all()
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, DistanceToPointFilter, OrderingFilter, SearchFilter]
    filterset_fields = ["route_type", "status", "mission", "avoids_hazards"]
    search_fields = ["name", "notes"]
    ordering_fields = ["name", "total_distance_km", "created_at", "status"]
    distance_filter_field = "path"
    distance_filter_convert_meters = True

    def get_serializer_class(self):
        if self.action == "create":
            return RouteCreateSerializer
        return RouteSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def calculate_route_stats(self, route):
        """Calculate route statistics from waypoints."""
        if not route.waypoints or len(route.waypoints) < 2:
            return
        
        coords = [(wp[0], wp[1]) for wp in route.waypoints]
        line = LineString(coords, srid=4326)
        route.path = line
        
        # Calculate distance (approximate, in km)
        # 1 degree ≈ 111 km at equator, but Mars is smaller
        # Mars radius ~ 3390 km, so 1 degree ≈ 59 km
        route.total_distance_km = line.length * 59  # Rough approximation
        
        # For now, set placeholder values
        route.estimated_duration_hours = route.total_distance_km / 5  # 5 km/h rover speed
        route.save(update_fields=["path", "total_distance_km", "estimated_duration_hours"])

    @action(detail=True, methods=["post"])
    def calculate(self, request, pk=None):
        """Calculate route statistics and segments."""
        route = self.get_object()
        self.calculate_route_stats(route)
        
        # Generate segments
        RouteSegment.objects.filter(route=route).delete()
        coords = [(wp[0], wp[1]) for wp in route.waypoints]
        
        segments = []
        for i in range(len(coords) - 1):
            start = coords[i]
            end = coords[i + 1]
            seg = RouteSegment.objects.create(
                route=route,
                order=i,
                start_point=start,
                end_point=end,
                distance_km=0,  # To be calculated
                slope=0,
                elevation_start=0,
                elevation_end=0,
                estimated_time_hours=0,
            )
            segments.append(seg)
        
        return Response({
            "status": "calculated",
            "total_distance_km": route.total_distance_km,
            "estimated_duration_hours": route.estimated_duration_hours,
            "segment_count": len(segments),
        })

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        route = self.get_object()
        route.status = "approved"
        route.approved_by = request.user
        from django.utils import timezone
        route.approved_at = timezone.now()
        route.save(update_fields=["status", "approved_by", "approved_at"])
        return Response({"status": "approved"})


class RouteSegmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RouteSegment.objects.select_related("route").all()
    serializer_class = RouteSegmentSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
