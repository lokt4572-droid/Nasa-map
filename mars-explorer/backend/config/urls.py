from django.contrib import admin
from django.urls import include, path

api_v1 = [
    path("", include("apps.core.urls")),
    path("", include("apps.datasets.urls")),
    path("", include("apps.missions.urls")),
    path("", include("apps.hazards.urls")),
    path("terrain/", include("apps.terrain.urls")),
    path("routes/", include("apps.routing.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
]
