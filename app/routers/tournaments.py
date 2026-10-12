import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.db import get_session
from app.routers.responses import ERROR_RESPONSES, write_response
from app.schemas import BracketOut, CreateTournamentRequest, TournamentOut
from app.services import tournaments
from app.services.idempotency import IdempotencyRequest, execute_write, idempotency_request

router = APIRouter(prefix="/v1/tournaments", tags=["tournaments"], responses=ERROR_RESPONSES)


@router.post(
    "",
    status_code=201,
    response_model=TournamentOut,
    summary="Create a tournament and generate its bracket",
    dependencies=[Depends(require_api_key)],
)
async def create_tournament(
    request: Request,
    body: CreateTournamentRequest,
    session: AsyncSession = Depends(get_session),
    idempotency: IdempotencyRequest | None = Depends(idempotency_request),
) -> JSONResponse:
    result = await execute_write(
        session,
        idempotency,
        lambda: tournaments.create_tournament(session, body.name, [t.name for t in body.teams]),
        status_code=201,
    )
    return write_response(request, result)


@router.get("/{tournament_id}", summary="Get a tournament")
async def get_tournament(
    tournament_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> TournamentOut:
    return await tournaments.get_tournament(session, tournament_id)


@router.get(
    "/{tournament_id}/bracket",
    summary="Get all matches grouped by round",
    description="Initial state / fallback for clients that do not use the Firestore read model.",
)
async def get_bracket(
    tournament_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> BracketOut:
    return await tournaments.get_bracket(session, tournament_id)
