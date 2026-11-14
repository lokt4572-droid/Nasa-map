from django.urls import path

from . import views

urlpatterns = [
    path("", views.route_list, name="route-list"),
    path("plan/", views.plan, name="route-plan"),
    path("profiles/", views.profiles, name="route-profiles"),
    path("<int:pk>/", views.detail, name="route-detail"),
]
