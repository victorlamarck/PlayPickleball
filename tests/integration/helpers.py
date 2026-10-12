from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent

TEAM_NAMES = [f"Team {i}" for i in range(1, 17)]


async def create_tournament(client: AsyncClient, team_count: int = 8) -> dict[str, Any]:
    response = await client.post(
        "/v1/tournaments",
        json={"name": "Test Open", "teams": [{"name": n} for n in TEAM_NAMES[:team_count]]},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def get_bracket(client: AsyncClient, tournament_id: str) -> dict[str, Any]:
    response = await client.get(f"/v1/tournaments/{tournament_id}/bracket")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def match_at(bracket: dict[str, Any], round_: int, position: int) -> dict[str, Any]:
    match: dict[str, Any] = bracket["rounds"][round_ - 1]["matches"][position]
    return match


async def start(client: AsyncClient, match_id: str) -> dict[str, Any]:
    response = await client.post(f"/v1/matches/{match_id}/start")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def point(client: AsyncClient, match: dict[str, Any], team: str) -> dict[str, Any]:
    response = await client.post(
        f"/v1/matches/{match['id']}/points",
        json={"team": team, "expected_version": match["version"]},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def play_match(client: AsyncClient, match_id: str, winner: str = "A") -> dict[str, Any]:
    """Start a match and let `winner` take every rally (11-0, 11-0)."""
    match = await start(client, match_id)
    while match["status"] != "finished":
        match = await point(client, match, winner)
    return match


async def outbox_events(session: AsyncSession) -> list[OutboxEvent]:
    session.expire_all()  # always read fresh rows written by the API's own sessions
    rows = await session.scalars(select(OutboxEvent).order_by(OutboxEvent.id))
    return list(rows)
