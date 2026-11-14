"""Centralised API error format.

Every error response has the shape::

    {"error": {"code": "SOME_CODE", "message": "Human readable", "details": {...}}}
"""
from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("mars.api")


class ApiError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "BAD_REQUEST"
    default_detail = "Bad request"

    def __init__(self, message: str | None = None, *, code: str | None = None, status_code: int | None = None, details=None):
        super().__init__(detail=message or self.default_detail, code=code or self.default_code)
        if status_code is not None:
            self.status_code = status_code
        self.error_code = code or self.default_code
        self.details = details or {}


def error_response(code: str, message: str, http_status: int, details=None) -> Response:
    return Response({"error": {"code": code, "message": message, "details": details or {}}}, status=http_status)


def api_exception_handler(exc, context):
    if isinstance(exc, ApiError):
        return error_response(exc.error_code, str(exc.detail), exc.status_code, exc.details)
    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error", exc_info=exc)
        return error_response("INTERNAL_ERROR", "Internal server error", status.HTTP_500_INTERNAL_SERVER_ERROR)
    if isinstance(exc, ValidationError):
        return error_response("VALIDATION_ERROR", "Invalid input", response.status_code, response.data)
    code = getattr(exc, "default_code", "ERROR")
    code = str(code).upper()
    message = response.data.get("detail", str(exc)) if isinstance(response.data, dict) else str(exc)
    return error_response(code, str(message), response.status_code)
