"""Shared-secret header authentication for scorekeepers and internal callers."""

import hmac

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from app.config import Settings
from app.errors import UnauthorizedError

# auto_error=False so missing headers go through our error format instead of FastAPI's default.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, scheme_name="ApiKey")
internal_token_header = APIKeyHeader(
    name="X-Internal-Token", auto_error=False, scheme_name="InternalToken"
)


def get_settings_from_app(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _matches(provided: str | None, expected: str) -> bool:
    # Constant-time comparison so response timing does not leak the secret.
    return provided is not None and hmac.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    )


async def require_api_key(request: Request, api_key: str | None = Depends(api_key_header)) -> None:
    if not _matches(api_key, get_settings_from_app(request).api_key):
        raise UnauthorizedError("Missing or invalid X-API-Key header")


async def require_internal_token(
    request: Request, token: str | None = Depends(internal_token_header)
) -> None:
    if not _matches(token, get_settings_from_app(request).internal_token):
        raise UnauthorizedError("Missing or invalid X-Internal-Token header")
