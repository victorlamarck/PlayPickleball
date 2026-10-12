"""Shared response helpers for routers."""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask

from app.outbox.relay import OutboxRelay
from app.schemas import ErrorResponse
from app.services.idempotency import WriteResult

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid API key"},
    404: {"model": ErrorResponse, "description": "Not found"},
    409: {"model": ErrorResponse, "description": "`version_conflict` or `invalid_state`"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}


def write_response(request: Request, result: WriteResult) -> JSONResponse:
    """Response for a committed write. Schedules the outbox fast path to run after it is sent."""
    if result.replayed:
        return JSONResponse(
            result.body, status_code=result.status_code, headers={"Idempotent-Replayed": "true"}
        )
    relay: OutboxRelay = request.app.state.relay
    return JSONResponse(
        result.body,
        status_code=result.status_code,
        background=BackgroundTask(relay.drain_safely),
    )
