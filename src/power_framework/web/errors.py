"""Typed, redacted HTTP error responses for the Web UI boundary."""

from __future__ import annotations

import re
import uuid

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from power_framework.core.errors import ConflictError

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class PowerCallTimeoutError(TimeoutError):
    """A bounded synchronous POWER call exceeded its request deadline."""


class PublicError(BaseModel):
    """Stable public error payload with no exception details."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    request_id: str


class PublicErrorResponse(BaseModel):
    """Envelope returned by every handled API error."""

    model_config = ConfigDict(extra="forbid")

    error: PublicError


def request_id_for(request: Request) -> str:
    """Return the sanitized correlation ID assigned by middleware."""
    request_id = getattr(request.state, "request_id", "")
    return request_id if _REQUEST_ID_PATTERN.fullmatch(request_id) else uuid.uuid4().hex


def make_public_error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    payload = PublicErrorResponse(
        error=PublicError(code=code, message=message, request_id=request_id_for(request))
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers={"X-Request-ID": payload.error.request_id},
    )


def _exception_mapping(exc: BaseException) -> tuple[int, str, str]:
    """Map known domain failures to a safe status, code, and message."""
    domain_status = getattr(exc, "status_code", None)
    domain_code = getattr(exc, "code", None)
    if isinstance(exc, ConflictError):
        return 409, "conflict", "The request conflicts with the current resource state."
    domain_messages = {
        403: ("permission_denied", "You do not have permission to perform this operation."),
        404: ("not_found", "The requested resource was not found."),
        409: ("conflict", "The request conflicts with the current resource state."),
        503: ("unavailable", "The POWER service is temporarily unavailable."),
    }
    if domain_status in domain_messages:
        default_code, message = domain_messages[domain_status]
        code = domain_code if isinstance(domain_code, str) else default_code
        return domain_status, code, message
    if isinstance(exc, (PowerCallTimeoutError, TimeoutError)):
        return 504, "timeout", "The POWER service did not complete the request in time."
    if isinstance(exc, FileNotFoundError):
        return 404, "not_found", "The requested resource was not found."
    if isinstance(exc, PermissionError):
        return 403, "permission_denied", "You do not have permission to perform this operation."
    if isinstance(exc, FileExistsError):
        return 409, "conflict", "The request conflicts with the current resource state."
    if isinstance(exc, (ValueError, TypeError)):
        return 400, "invalid_request", "The request is invalid."
    return 500, "internal_error", "The service could not complete the request."


def public_error_details(exc: BaseException) -> tuple[str, str]:
    """Return only safe code/message fields for errors after streaming starts."""
    if isinstance(exc, StarletteHTTPException):
        _, code, message = _http_mapping(exc)
    else:
        _, code, message = _exception_mapping(exc)
    return code, message


def public_http_exception(exc: BaseException) -> HTTPException:
    """Convert a domain exception to an HTTPException with redacted detail."""
    status_code, code, _message = _exception_mapping(exc)
    return HTTPException(status_code=status_code, detail=code)


def _http_mapping(exc: StarletteHTTPException) -> tuple[int, str, str]:
    """Map framework HTTP failures without reflecting their detail field."""
    status_code = exc.status_code
    known = {
        400: ("invalid_request", "The request is invalid."),
        401: ("authentication_required", "Authentication is required."),
        403: ("permission_denied", "You do not have permission to perform this operation."),
        404: ("not_found", "The requested resource was not found."),
        405: (
            "operation_not_allowed",
            "The operation is not allowed while the Web UI is read-only.",
        ),
        408: ("timeout", "The request timed out."),
        409: ("conflict", "The request conflicts with the current resource state."),
        413: ("request_too_large", "The request is too large."),
        422: ("validation_error", "The request failed validation."),
        429: ("rate_limited", "Too many requests. Try again later."),
        500: ("internal_error", "The service could not complete the request."),
        503: ("unavailable", "The service is temporarily unavailable."),
        504: ("timeout", "The POWER service did not complete the request in time."),
    }
    code, message = known.get(
        status_code,
        ("request_error", "The request could not be completed."),
    )
    public_status = status_code if status_code in known else 400
    return public_status, code, message


async def request_validation_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a stable 422 without exposing locations, values, or model internals."""
    return make_public_error_response(
        request, 422, "validation_error", "The request failed validation."
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Redact route-provided HTTPException details at the public boundary."""
    if not isinstance(exc, StarletteHTTPException):
        return make_public_error_response(
            request, 500, "internal_error", "The service could not complete the request."
        )
    status_code, code, message = _http_mapping(exc)
    return make_public_error_response(request, status_code, code, message)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a correlation ID while keeping exception data server-side only."""
    status_code, code, message = _exception_mapping(exc)
    if status_code == 500:
        request.app.state.error_logger.error(
            "Unhandled request failure request_id=%s exception_type=%s",
            request_id_for(request),
            type(exc).__name__,
        )
    return make_public_error_response(request, status_code, code, message)


__all__ = [
    "PowerCallTimeoutError",
    "PublicError",
    "PublicErrorResponse",
    "http_exception_handler",
    "make_public_error_response",
    "public_error_details",
    "public_http_exception",
    "request_id_for",
    "request_validation_handler",
    "unhandled_exception_handler",
]
