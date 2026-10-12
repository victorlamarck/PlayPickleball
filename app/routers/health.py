"""Liveness and readiness endpoints."""

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(tags=["health"])
logger = structlog.get_logger()


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])


@router.get("/health", summary="Liveness probe")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/health/ready",
    summary="Readiness probe (checks the database)",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
)
async def ready(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("readiness_check_failed", error=str(exc))
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})
