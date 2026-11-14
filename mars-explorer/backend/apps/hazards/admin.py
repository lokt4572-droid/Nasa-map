from django.contrib import admin

from .models import Hazard


@admin.register(Hazard)
class HazardAdmin(admin.ModelAdmin):
    list_display = ("title", "hazard_type", "severity", "verification", "lat_deg", "lon_east_deg", "created_at")
    list_filter = ("hazard_type", "severity", "verification", "source")
