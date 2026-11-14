import logging
from pathlib import Path

from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.exceptions import ApiError
from services import dataset_manager
from services.dem_reader import RasterBackendUnavailable, RasterReadError

from .models import Dataset
from .serializers import DatasetMetadataSerializer, DatasetRegisterSerializer, DatasetSerializer

logger = logging.getLogger("mars.datasets")


class DatasetViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Dataset.objects.all()
    serializer_class = DatasetSerializer

    def list(self, request, *args, **kwargs):
        for ds in self.get_queryset():
            dataset_manager.refresh_file_status(ds)
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def metadata(self, request, pk=None):
        return Response(DatasetMetadataSerializer(self.get_object()).data)

    @action(detail=False, methods=["post"])
    def register(self, request):
        ser = DatasetRegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        root = Path(settings.MARS_DATA_DIR).resolve()
        target = (root / data["file_path"]).resolve()
        if not target.is_relative_to(root):
            raise ApiError("file_path must be inside MARS_DATA_DIR", code="PATH_OUTSIDE_DATA_DIR")
        try:
            dataset, _, warnings = dataset_manager.register_dataset(
                path=target,
                name=data["name"],
                source=data["source"],
                instrument=data["instrument"],
                product_id=data["product_id"],
                vertical_datum=data["vertical_datum"] or None,
                units=data["units"] or None,
            )
        except dataset_manager.DatasetValidationError as exc:
            raise ApiError(
                "Dataset failed validation",
                code="DATASET_INVALID",
                status_code=422,
                details={"errors": exc.errors, "warnings": exc.warnings},
            ) from exc
        except RasterBackendUnavailable as exc:
            raise ApiError(str(exc), code="DEM_BACKEND_UNAVAILABLE", status_code=503) from exc
        except RasterReadError as exc:
            raise ApiError(str(exc), code="RASTER_UNREADABLE", status_code=422) from exc
        return Response({"dataset": DatasetSerializer(dataset).data, "warnings": warnings}, status=status.HTTP_201_CREATED)
