from django.urls import path

from . import views

urlpatterns = [
    path("", views.route_list, name="route-list"),
    path("plan/", views.plan, name="route-plan"),
    path("alternatives/", views.alternatives, name="route-alternatives"),
    path("hazards/derive/", views.derive_hazards, name="route-derive-hazards"),
    path("profiles/", views.profiles, name="route-profiles"),
    path("<int:pk>/", views.detail, name="route-detail"),
]
