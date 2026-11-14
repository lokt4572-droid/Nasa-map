from rest_framework.routers import DefaultRouter

from .views import HazardViewSet

router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
router.register("hazards", HazardViewSet, basename="hazard")
urlpatterns = router.urls
