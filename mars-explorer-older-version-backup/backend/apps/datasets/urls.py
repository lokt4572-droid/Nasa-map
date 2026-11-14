from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DatasetViewSet, DatasetLayerViewSet

router = DefaultRouter()
router.register(r"datasets", DatasetViewSet, basename="dataset")
router.register(r"layers", DatasetLayerViewSet, basename="datasetlayer")

urlpatterns = [
    path("", include(router.urls)),
]
