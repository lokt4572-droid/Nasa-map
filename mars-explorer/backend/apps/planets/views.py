"""Planet registry API (read-only; data in services/planet_registry.py)."""
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.exceptions import ApiError
from services.planet_registry import PLANETS, UnknownPlanetError, get_planet, layers_for


def _planet_or_404(planet_id: str):
    try:
        return get_planet(planet_id)
    except UnknownPlanetError as exc:
        raise ApiError(str(exc), code="NOT_FOUND", status_code=404) from exc


@api_view(["GET"])
def planet_list(request):
    return Response([{**p.to_dict(), "layer_count": len(layers_for(p.id))} for p in PLANETS.values()])


@api_view(["GET"])
def planet_detail(request, planet_id: str):
    p = _planet_or_404(planet_id)
    return Response({**p.to_dict(), "layers": layers_for(p.id)})


@api_view(["GET"])
def planet_layers(request, planet_id: str):
    p = _planet_or_404(planet_id)
    return Response(layers_for(p.id))
