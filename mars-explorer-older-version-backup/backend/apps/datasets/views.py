from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework_gis.filters import DistanceToPointFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from .models import Dataset, DatasetLayer
from .serializers import DatasetSerializer, DatasetLayerSerializer


class DatasetViewSet(viewsets.ModelViewSet):
    queryset = Dataset.objects.select_related("uploaded_by").all()
    serializer_class = DatasetSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, DistanceToPointFilter, OrderingFilter, SearchFilter]
    filterset_fields = ["source", "dataset_type", "is_public", "is_processed"]
    search_fields = ["name", "identifier", "description"]
    ordering_fields = ["name", "source", "dataset_type", "resolution_meters", "created_at"]
    distance_filter_field = "coverage"
    distance_filter_convert_meters = True

    @action(detail=True, methods=["get"])
    def layers(self, request, pk=None):
        dataset = self.get_object()
        layers = dataset.layers.all()
        from .serializers import DatasetLayerSerializer
        return Response(DatasetLayerSerializer(layers, many=True).data)


class DatasetLayerViewSet(viewsets.ModelViewSet):
    queryset = DatasetLayer.objects.select_related("dataset").all()
    serializer_class = DatasetLayerSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = ["layer_type", "is_base_layer", "is_visible", "dataset"]
    search_fields = ["name", "wmts_layer_id"]
    ordering_fields = ["z_index", "name", "dataset"]
