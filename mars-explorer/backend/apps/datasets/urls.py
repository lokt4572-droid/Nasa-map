from rest_framework.routers import DefaultRouter

from .views import DatasetViewSet

router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
router.register("datasets", DatasetViewSet, basename="dataset")
urlpatterns = router.urls
