from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.exceptions import ApiError
from apps.weather.views import _provider_call

from . import services


@api_view(["GET"])
def search(request):
    q = (request.query_params.get("q") or "").strip()
    if not 2 <= len(q) <= 200:
        raise ApiError("q must be 2..200 characters", code="VALIDATION_ERROR")
    try:
        return Response(_provider_call(services.search, q))
    except services.RateLimited as exc:
        raise ApiError("Search rate limit (1 request/second) — retry shortly", code="RATE_LIMITED", status_code=429) from exc
