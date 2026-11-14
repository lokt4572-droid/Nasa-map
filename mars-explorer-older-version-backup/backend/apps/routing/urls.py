from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RouteViewSet, RouteSegmentViewSet

router = DefaultRouter()
router.register(r"routes", RouteViewSet, basename="route")
router.register(r"segments", RouteSegmentViewSet, basename="routesegment")

urlpatterns = [
    path("", include(router.urls)),
]
