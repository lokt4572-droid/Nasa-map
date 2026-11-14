from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("health/sources/", views.health_sources, name="health-sources"),
]
