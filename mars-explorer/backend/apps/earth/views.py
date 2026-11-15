from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.weather.views import _provider_call
from services import gibs


@api_view(["GET"])
def gibs_layers(request):
    """Curated GIBS layers verified against the live GetCapabilities (EPSG:3857)."""
    return Response(_provider_call(gibs.discover, request.query_params.get("refresh") == "1"))
