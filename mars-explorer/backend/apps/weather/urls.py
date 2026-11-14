from django.urls import path

from . import views

urlpatterns = [
    path("current/", views.current, name="weather-current"),
    path("forecast/", views.forecast, name="weather-forecast"),
    path("historical/", views.historical, name="weather-historical"),
    path("status/", views.weather_status, name="weather-status"),
]
