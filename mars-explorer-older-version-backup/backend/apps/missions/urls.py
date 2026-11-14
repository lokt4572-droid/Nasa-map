from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BaseCampViewSet, WaypointViewSet, MissionViewSet, ExpeditionLogViewSet

router = DefaultRouter()
router.register(r"basecamps", BaseCampViewSet, basename="basecamp")
router.register(r"waypoints", WaypointViewSet, basename="waypoint")
router.register(r"missions", MissionViewSet, basename="mission")
router.register(r"logs", ExpeditionLogViewSet, basename="expeditionlog")

urlpatterns = [
    path("", include(router.urls)),
]
