from django.urls import path

from . import views

urlpatterns = [
    path("status/", views.ai_status, name="ai-status"),
    path("interpret/", views.interpret, name="ai-interpret"),
    path("plan/", views.ai_plan, name="ai-plan"),
    path("explain/", views.explain, name="ai-explain"),
    path("perception/detections/", views.ingest_detections, name="ai-perception-detections"),
]
