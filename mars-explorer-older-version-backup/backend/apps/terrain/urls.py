from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TerrainAnalysisViewSet, ElevationProfileViewSet

router = DefaultRouter()
router.register(r"analyses", TerrainAnalysisViewSet, basename="terrainanalysis")
router.register(r"profiles", ElevationProfileViewSet, basename="elevationprofile")

urlpatterns = [
    path("", include(router.urls)),
]
