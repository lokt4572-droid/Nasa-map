from django.urls import path
from rest_framework.routers import DefaultRouter

from . import discovery_views
from .views import DatasetViewSet

router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
router.register("datasets", DatasetViewSet, basename="dataset")
urlpatterns = [
    # Before the router so "search" is not taken for a dataset id.
    path("datasets/search/", discovery_views.search, name="dataset-search"),
    path("datasets/coverage/", discovery_views.point_coverage, name="dataset-coverage"),
    path("datasets/register-remote/", discovery_views.register_remote, name="dataset-register-remote"),
    path("coverage/<str:planet_id>/", discovery_views.planet_coverage, name="coverage-planet"),
    path("coverage/<str:planet_id>/search/", discovery_views.planet_search, name="coverage-planet-search"),
    *router.urls,
]
