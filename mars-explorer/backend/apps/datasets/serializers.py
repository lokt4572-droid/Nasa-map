from pathlib import Path

from rest_framework import serializers

from .models import Dataset


class DatasetSerializer(serializers.ModelSerializer):
    file_exists = serializers.SerializerMethodField()

    class Meta:
        model = Dataset
        exclude = ["metadata", "crs"]
        read_only_fields = [f.name for f in Dataset._meta.fields]

    def get_file_exists(self, obj: Dataset) -> bool:
        return Path(obj.file_path).is_file()


class DatasetMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = ["id", "name", "crs", "crs_name", "metadata", "validation_messages", "checksum", "status"]


class DatasetRegisterSerializer(serializers.Serializer):
    """Register a DEM that already sits inside MARS_DATA_DIR (no browser upload of big files)."""

    file_path = serializers.CharField(max_length=1024, help_text="Path relative to MARS_DATA_DIR, e.g. raw/mola/file.xml")
    name = serializers.SlugField(max_length=120)
    planet = serializers.ChoiceField(choices=["MARS", "EARTH", "MOON", "MERCURY", "VENUS"], default="MARS")
    source = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    instrument = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    product_id = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    vertical_datum = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    units = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
