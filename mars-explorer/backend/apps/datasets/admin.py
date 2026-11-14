from django.contrib import admin

from .models import Dataset


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("name", "data_type", "instrument", "status", "resolution_meters", "units", "created_at")
    list_filter = ("status", "data_type", "instrument")
    search_fields = ("name", "product_id", "file_path")
