"""Unit of work for write endpoints, with optional `Idempotency-Key` support.

Every write runs in one transaction. When a key is given:
- a transaction-scoped advisory lock on the key serializes concurrent retries of the same request;
- a stored response for the same key and request hash is replayed without re-running the write;
- the same key with a different request hash is rejected (422);
- the response is stored in the same transaction as the write, so both commit or neither does.

Only successful responses are stored: a failed write rolls back, and a retry runs it again.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Header, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import IdempotencyKeyReusedError
from app.models import IdempotencyKey


@dataclass(frozen=True, slots=True)
class IdempotencyRequest:
    key: str
    request_hash: str


@dataclass(frozen=True, slots=True)
class WriteResult:
    status_code: int
    body: dict[str, Any]
    replayed: bool = False


def hash_request(method: str, path: str, body: bytes) -> str:
    try:
        canonical = json.dumps(json.loads(body), sort_keys=True, separators=(",", ":")).encode()
    except ValueError:
        canonical = body
    digest = hashlib.sha256()
    for part in (method.upper().encode(), path.encode(), canonical):
        digest.update(part)
        digest.update(b"\0")
    return digest.hexdigest()


async def idempotency_request(
    request: Request,
    idempotency_key: str | None = Header(
        default=None,
        max_length=255,
        description="Optional. Retrying with the same key returns the original response.",
    ),
) -> IdempotencyRequest | None:
    """FastAPI dependency reading the optional `Idempotency-Key` header."""
    if not idempotency_key:
        return None
    body = await request.body()
    return IdempotencyRequest(idempotency_key, hash_request(request.method, request.url.path, body))


async def execute_write(
    session: AsyncSession,
    idempotency: IdempotencyRequest | None,
    operation: Callable[[], Awaitable[BaseModel]],
    status_code: int = 200,
) -> WriteResult:
    async with session.begin():
        if idempotency is not None:
            await session.execute(
                select(func.pg_advisory_xact_lock(func.hashtext(idempotency.key)))
            )
            stored = await session.get(IdempotencyKey, idempotency.key)
            if stored is not None:
                if stored.request_hash != idempotency.request_hash:
                    raise IdempotencyKeyReusedError()
                return WriteResult(stored.response_status, stored.response_body, replayed=True)

        body = (await operation()).model_dump(mode="json")

        if idempotency is not None:
            session.add(
                IdempotencyKey(
                    key=idempotency.key,
                    request_hash=idempotency.request_hash,
                    response_status=status_code,
                    response_body=body,
                )
            )
    return WriteResult(status_code, body)
