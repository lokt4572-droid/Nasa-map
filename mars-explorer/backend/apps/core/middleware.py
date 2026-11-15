"""Public demo read-only mode (settings.PUBLIC_READ_ONLY).

Shared records (missions, hazards, registered datasets, sync) cannot be created, changed or deleted
by anonymous visitors of a public deployment. Computation endpoints stay open: they read data and
store only their own results (route results, AI audit records, catalogue DTM registrations from
allow-listed hosts). Operators can write with the X-Api-Token header (WRITE_API_TOKEN)."""
from __future__ import annotations

import hmac
import re

from django.conf import settings
from django.http import JsonResponse

SAFE = {"GET", "HEAD", "OPTIONS"}
# POST endpoints that compute rather than edit shared records.
COMPUTE_ALLOWED = [
    re.compile(p)
    for p in (
        r"^/api/v1/routes/plan/$",
        r"^/api/v1/routes/alternatives/$",
        r"^/api/v1/routes/hazards/derive/$",
        r"^/api/v1/ai/(interpret|plan|explain)/$",
        r"^/api/v1/datasets/register-remote/$",
    )
]


class PublicReadOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "PUBLIC_READ_ONLY", False) and request.method not in SAFE and request.path.startswith("/api/"):
            token = getattr(settings, "WRITE_API_TOKEN", "")
            sent = request.headers.get("X-Api-Token", "")
            operator = bool(token) and hmac.compare_digest(sent, token)
            if not operator and not any(p.match(request.path) for p in COMPUTE_ALLOWED):
                return JsonResponse(
                    {"error": {"code": "READ_ONLY_DEMO", "message": "This public demo is read-only: shared records cannot be changed here.",
                               "details": {"method": request.method, "path": request.path}}},
                    status=403,
                )
        return self.get_response(request)
