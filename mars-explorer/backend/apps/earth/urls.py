from django.urls import path

from . import views

urlpatterns = [path("gibs/layers/", views.gibs_layers, name="gibs-layers")]
