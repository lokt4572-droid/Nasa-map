"""URL configuration for MARS EXPLORER."""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/missions/", include("apps.missions.urls")),
    path("api/hazards/", include("apps.hazards.urls")),
    path("api/datasets/", include("apps.datasets.urls")),
    path("api/terrain/", include("apps.terrain.urls")),
    path("api/routing/", include("apps.routing.urls")),
]

if __name__ == "__main__":
    from django.conf import settings
    if settings.DEBUG:
        import debug_toolbar
        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
