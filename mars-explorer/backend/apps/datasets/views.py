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


# Files accepted for registration through the API (CLI import_dem has no such limit).
ALLOWED_SUFFIXES = {".tif", ".tiff", ".img", ".xml", ".lbl", ".cub", ".vrt"}


def _looks_like_raster_or_label(path: Path) -> bool:
    """Content check (not just the extension): TIFF/BigTIFF magic, PDS3 label, PDS4 XML,
    VRT XML, ISIS cube label, or a raw .IMG that has a sibling PDS label."""
    with path.open("rb") as fh:
        head = fh.read(64)
    if head[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
        return True
    text = head.lstrip(b"\xef\xbb\xbf").lstrip()
    if text.startswith((b"<?xml", b"<Product", b"<VRTDataset")):
        return True
    if text.upper().startswith((b"PDS_VERSION_ID", b"OBJECT", b"CCSD", b"ODL_VERSION")):
        return True
    if path.suffix.lower() == ".img":
        return any(path.with_suffix(sfx).is_file() for sfx in (".xml", ".lbl", ".XML", ".LBL"))
    return False


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

    @action(detail=False, methods=["get"])
    def catalog(self, request):
        """Unified product catalog with local status. Filters: ?planet=MARS&type=DEM"""
        from .catalog import TYPES, catalog_with_status

        planet = (request.query_params.get("planet") or "").upper() or None
        dtype = (request.query_params.get("type") or "").upper() or None
        if dtype and dtype not in TYPES:
            raise ApiError(f"type must be one of {', '.join(TYPES)}", code="VALIDATION_ERROR")
        return Response({"types": TYPES, "results": catalog_with_status(planet, dtype)})

    @action(detail=False, methods=["post"])
    def register(self, request):
        ser = DatasetRegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        root = Path(settings.MARS_DATA_DIR).resolve()
        target = (root / data["file_path"]).resolve()
        if not target.is_relative_to(root):
            raise ApiError("file_path must be inside MARS_DATA_DIR", code="PATH_OUTSIDE_DATA_DIR")
        if not target.is_file():
            raise ApiError("File not found inside the data directory", code="NOT_FOUND", status_code=404)
        if target.suffix.lower() not in ALLOWED_SUFFIXES:
            raise ApiError(f"Unsupported file type {target.suffix!r}; allowed: {', '.join(sorted(ALLOWED_SUFFIXES))}", code="UNSUPPORTED_FILE_TYPE")
        max_bytes = settings.MAX_REGISTER_FILE_BYTES
        if target.stat().st_size > max_bytes:
            raise ApiError(
                f"File larger than {max_bytes // 1_000_000} MB: use the CLI (python manage.py import_dem)",
                code="FILE_TOO_LARGE", status_code=413,
            )
        if not _looks_like_raster_or_label(target):
            raise ApiError("File content is not a recognised raster or PDS/ISIS/VRT label", code="UNSUPPORTED_FILE_TYPE")
        try:
            dataset, _, warnings = dataset_manager.register_dataset(
                path=target,
                name=data["name"],
                planet=data["planet"],
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
                details={"errors": exc.errors, "warnings": exc.warnings, "steps": exc.steps},
            ) from exc
        except RasterBackendUnavailable as exc:
            raise ApiError(str(exc), code="DEM_BACKEND_UNAVAILABLE", status_code=503) from exc
        except RasterReadError as exc:
            raise ApiError(str(exc), code="RASTER_UNREADABLE", status_code=422) from exc
        return Response({"dataset": DatasetSerializer(dataset).data, "warnings": warnings, "steps": dataset.metadata.get("import_steps", [])}, status=status.HTTP_201_CREATED)
