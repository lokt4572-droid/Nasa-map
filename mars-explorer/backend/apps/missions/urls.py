from rest_framework.routers import DefaultRouter

from .views import MissionViewSet, WaypointViewSet

router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
router.register("missions", MissionViewSet, basename="mission")
router.register("waypoints", WaypointViewSet, basename="waypoint")
urlpatterns = router.urls
