from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import Dataset, DatasetLayer


class DatasetSerializer(GeoFeatureModelSerializer):
    layers_count = serializers.SerializerMethodField()

    class Meta:
        model = Dataset
        geo_field = "coverage"
        fields = ["id", "name", "source", "dataset_type", "identifier", "description",
                  "resolution_meters", "crs", "file_path", "bands", "bit_depth",
                  "min_value", "max_value", "acquisition_date", "processing_level",
                  "metadata", "is_public", "is_processed", "layers_count", "created_at"]

    def get_layers_count(self, obj):
        return obj.layers.count()


class DatasetLayerSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = DatasetLayer
        geo_field = None
        fields = ["id", "name", "dataset", "layer_type", "url_template",
                  "wmts_layer_id", "wmts_matrix_set", "wmts_style", "wmts_format",
                  "min_zoom", "max_zoom", "attribution", "opacity",
                  "is_base_layer", "is_visible", "z_index", "color_ramp"]
