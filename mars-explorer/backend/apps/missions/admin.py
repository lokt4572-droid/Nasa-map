from django.contrib import admin

from .models import Mission, Waypoint


class WaypointInline(admin.TabularInline):
    model = Waypoint
    extra = 0


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "demo_mode", "created_at")
    inlines = [WaypointInline]
