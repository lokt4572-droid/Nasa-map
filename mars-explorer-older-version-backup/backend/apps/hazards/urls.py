from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HazardViewSet, HazardReportViewSet

router = DefaultRouter()
router.register(r"hazards", HazardViewSet, basename="hazard")
router.register(r"reports", HazardReportViewSet, basename="hazardreport")

urlpatterns = [
    path("", include(router.urls)),
]
