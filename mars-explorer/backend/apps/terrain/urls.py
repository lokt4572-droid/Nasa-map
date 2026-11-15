from django.urls import path

from . import views

urlpatterns = [
    path("sample/", views.sample, name="terrain-sample"),
    path("slope/", views.slope, name="terrain-slope"),
    path("aspect/", views.aspect, name="terrain-aspect"),
    path("roughness/", views.roughness, name="terrain-roughness"),
    path("relief/", views.relief, name="terrain-relief"),
    path("nodata/", views.nodata, name="terrain-nodata"),
    path("difference/", views.difference, name="terrain-difference"),
    path("area/", views.area, name="terrain-area"),
    path("render/", views.render, name="terrain-render"),
    path("coverage/", views.coverage, name="terrain-coverage"),
    path("patch/", views.patch, name="terrain-patch"),
    path("profile/", views.profile, name="terrain-profile"),
]
