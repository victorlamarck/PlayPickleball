import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.helpers import (
    create_tournament,
    get_bracket,
    match_at,
    outbox_events,
    play_match,
)


async def test_create_tournament_then_get_bracket(client: AsyncClient) -> None:
    tournament = await create_tournament(client, 8)
    assert tournament["status"] == "scheduled"
    assert tournament["rounds"] == 3
    assert tournament["version"] == 1
    assert [t["seed"] for t in tournament["teams"]] == list(range(1, 9))

    bracket = await get_bracket(client, tournament["id"])
    assert [len(r["matches"]) for r in bracket["rounds"]] == [4, 2, 1]

    first_round = bracket["rounds"][0]["matches"]
    assert [(m["team_a"]["seed"], m["team_b"]["seed"]) for m in first_round] == [
        (1, 8),
        (4, 5),
        (2, 7),
        (3, 6),
    ]
    semis = bracket["rounds"][1]["matches"]
    final = bracket["rounds"][2]["matches"][0]
    assert first_round[0]["next_match_id"] == semis[0]["id"]
    assert first_round[0]["next_slot"] == "A"
    assert first_round[1]["next_slot"] == "B"
    assert all(m["team_a"] is None and m["team_b"] is None for m in semis)
    assert final["next_match_id"] is None
    assert all(
        m["status"] == "pending" and m["version"] == 1
        for r in bracket["rounds"]
        for m in r["matches"]
    )


async def test_create_tournament_seeds_read_model_through_outbox(
    client: AsyncClient, session: AsyncSession
) -> None:
    tournament = await create_tournament(client, 4)

    events = await outbox_events(session)
    assert [e.event_type for e in events] == ["tournament_updated"] + ["match_updated"] * 3
    assert events[0].aggregate_id == uuid.UUID(tournament["id"])
    assert events[0].payload == {
        "name": "Test Open",
        "status": "scheduled",
        "rounds": 2,
        "version": 1,
    }
    first_match = events[1].payload
    assert first_match["round"] == 1
    assert first_match["teamA"]["seed"] == 1
    assert first_match["teamB"]["seed"] == 4
    assert first_match["games"] == []


async def test_unsupported_team_count_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/tournaments", json={"name": "Odd", "teams": [{"name": f"T{i}"} for i in range(6)]}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_bracket"


async def test_unknown_tournament_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/v1/tournaments/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_final_finishes_tournament(client: AsyncClient, session: AsyncSession) -> None:
    tournament = await create_tournament(client, 4)
    bracket = await get_bracket(client, tournament["id"])

    await play_match(client, match_at(bracket, 1, 0)["id"], winner="A")  # seed 1
    await play_match(client, match_at(bracket, 1, 1)["id"], winner="B")  # seed 3
    bracket = await get_bracket(client, tournament["id"])
    final = match_at(bracket, 2, 0)
    assert (final["team_a"]["seed"], final["team_b"]["seed"]) == (1, 3)

    final = await play_match(client, final["id"], winner="B")
    assert final["winner_team_id"] == bracket["rounds"][1]["matches"][0]["team_b"]["id"]

    response = await client.get(f"/v1/tournaments/{tournament['id']}")
    finished = response.json()
    assert finished["status"] == "finished"
    # scheduled(1) -> in_progress(2) -> finished(3)
    assert finished["version"] == 3

    tournament_events = [
        e for e in await outbox_events(session) if e.aggregate_type == "tournament"
    ]
    assert [e.payload["status"] for e in tournament_events] == [
        "scheduled",
        "in_progress",
        "finished",
    ]
