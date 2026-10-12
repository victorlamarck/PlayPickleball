import uuid

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.db import get_session
from app.routers.responses import ERROR_RESPONSES, write_response
from app.schemas import GameCorrectionRequest, MatchOut, PointRequest
from app.services import matches
from app.services.idempotency import IdempotencyRequest, execute_write, idempotency_request

router = APIRouter(
    prefix="/v1/matches",
    tags=["matches"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "/{match_id}/start",
    response_model=MatchOut,
    summary="Start a match (pending -> live)",
    description="Requires both teams. The first game opens at 0-0.",
)
async def start_match(
    request: Request,
    match_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    idempotency: IdempotencyRequest | None = Depends(idempotency_request),
) -> JSONResponse:
    result = await execute_write(
        session, idempotency, lambda: matches.start_match(session, match_id)
    )
    return write_response(request, result)


@router.post(
    "/{match_id}/points",
    response_model=MatchOut,
    summary="Score a rally point",
    description=(
        "Optimistic concurrency: send the last seen `version` as `expected_version`. "
        "On `409 version_conflict`, `details.current_version` holds the current version."
    ),
)
async def add_point(
    request: Request,
    match_id: uuid.UUID,
    body: PointRequest,
    session: AsyncSession = Depends(get_session),
    idempotency: IdempotencyRequest | None = Depends(idempotency_request),
) -> JSONResponse:
    result = await execute_write(
        session,
        idempotency,
        lambda: matches.add_point(session, match_id, body.team, body.expected_version),
    )
    return write_response(request, result)


@router.put(
    "/{match_id}/games/{index}",
    response_model=MatchOut,
    summary="Correct the score of a game",
    description="Scorekeeper correction. The score must be reachable in a real game.",
)
async def correct_game(
    request: Request,
    match_id: uuid.UUID,
    body: GameCorrectionRequest,
    index: int = Path(ge=0, le=2, description="0-based game index."),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    result = await execute_write(
        session,
        None,
        lambda: matches.correct_game(
            session, match_id, index, body.a, body.b, body.expected_version
        ),
    )
    return write_response(request, result)
