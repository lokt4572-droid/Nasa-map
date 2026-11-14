from django.urls import path

from . import views

urlpatterns = [
    path("planets/", views.planet_list, name="planet-list"),
    path("planets/<str:planet_id>/", views.planet_detail, name="planet-detail"),
    path("planets/<str:planet_id>/layers/", views.planet_layers, name="planet-layers"),
]
