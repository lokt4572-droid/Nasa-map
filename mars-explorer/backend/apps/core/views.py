from django.conf import settings
from django.db import connection
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from services.dem_reader import raster_backend_status


@api_view(["GET"])
def health(request):
    db_ok = True
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        db_ok = False
    data_dir = settings.MARS_DATA_DIR
    return Response(
        {
            "status": "ok" if db_ok else "degraded",
            "service": "nova-backend",
            "version": settings.APP_VERSION,
            "time_utc": timezone.now().isoformat(),
            "database": "ok" if db_ok else "error",
            "data_dir": {"path": str(data_dir), "exists": data_dir.is_dir()},
            "raster_backend": raster_backend_status(),
        },
        status=200 if db_ok else 503,
    )


@api_view(["GET"])
def health_sources(request):
    """External service availability (cached 10 min; ?refresh=1 forces a new probe)."""
    from services.source_health import check_sources

    return Response(check_sources(force=request.query_params.get("refresh") == "1"))
