from django.contrib import admin
from django.urls import include, path

api_v1 = [
    path("", include("apps.core.urls")),
    path("", include("apps.planets.urls")),
    path("", include("apps.datasets.urls")),
    path("", include("apps.missions.urls")),
    path("", include("apps.hazards.urls")),
    path("terrain/", include("apps.terrain.urls")),
    path("routes/", include("apps.routing.urls")),
    path("weather/", include("apps.weather.urls")),
    path("geocoding/", include("apps.geocoding.urls")),
    path("earth/", include("apps.earth.urls")),
    path("ai/", include("apps.ai.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
]
