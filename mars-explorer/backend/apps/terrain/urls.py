from django.urls import path

from . import views

urlpatterns = [
    path("sample/", views.sample, name="terrain-sample"),
    path("slope/", views.slope, name="terrain-slope"),
    path("coverage/", views.coverage, name="terrain-coverage"),
]
