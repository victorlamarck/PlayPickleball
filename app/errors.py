"""Domain exceptions and the handlers that render every error as
`{"error": {"code", "message", "details"}}`."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class DomainError(Exception):
    """Base class for errors that map to a structured API error response."""

    code: str = "domain_error"
    status_code: int = 400

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}


class InvalidStateError(DomainError):
    """The operation is not allowed in the aggregate's current state."""

    code = "invalid_state"
    status_code = 409


class VersionConflictError(DomainError):
    """`expected_version` does not match the stored version; the client should refetch."""

    code = "version_conflict"
    status_code = 409

    def __init__(self, current_version: int, expected_version: int) -> None:
        super().__init__(
            "The resource was modified by another request",
            {"current_version": current_version, "expected_version": expected_version},
        )


class InvalidScoreError(DomainError):
    """A score correction describes a score that cannot happen in a real game."""

    code = "invalid_score"
    status_code = 422


class InvalidBracketError(DomainError):
    """The requested bracket cannot be built (e.g. unsupported team count)."""

    code = "invalid_bracket"
    status_code = 422


class IdempotencyKeyReusedError(DomainError):
    """The same Idempotency-Key was sent with a different request."""

    code = "idempotency_key_reused"
    status_code = 422

    def __init__(self) -> None:
        super().__init__("Idempotency-Key was already used with a different request")


class NotFoundError(DomainError):
    code = "not_found"
    status_code = 404


class UnauthorizedError(DomainError):
    code = "unauthorized"
    status_code = 401


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


async def _domain_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return JSONResponse(error_body(exc.code, exc.message, exc.details), exc.status_code)


async def _validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = {"errors": jsonable_encoder(exc.errors())}
    return JSONResponse(error_body("validation_error", "Invalid request", details), 422)


async def _http_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
    return JSONResponse(error_body(code, str(exc.detail)), exc.status_code, headers=exc.headers)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
