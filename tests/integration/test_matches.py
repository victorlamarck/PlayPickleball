import asyncio
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.helpers import (
    create_tournament,
    get_bracket,
    match_at,
    outbox_events,
    play_match,
    point,
    start,
)


async def test_start_match_opens_first_game_and_moves_tournament_in_progress(
    client: AsyncClient, session: AsyncSession
) -> None:
    tournament = await create_tournament(client, 4)
    match_id = match_at(await get_bracket(client, tournament["id"]), 1, 0)["id"]

    match = await start(client, match_id)
    assert match["status"] == "live"
    assert match["games"] == [{"a": 0, "b": 0}]
    assert match["version"] == 2

    response = await client.get(f"/v1/tournaments/{tournament['id']}")
    assert response.json()["status"] == "in_progress"

    new_events = (await outbox_events(session))[4:]
    assert [(e.event_type, e.aggregate_version) for e in new_events] == [
        ("match_started", 2),
        ("tournament_updated", 2),
    ]


async def test_cannot_start_match_without_both_teams(client: AsyncClient) -> None:
    tournament = await create_tournament(client, 4)
    final = match_at(await get_bracket(client, tournament["id"]), 2, 0)

    response = await client.post(f"/v1/matches/{final['id']}/start")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


async def test_cannot_start_twice(client: AsyncClient) -> None:
    tournament = await create_tournament(client, 4)
    match_id = match_at(await get_bracket(client, tournament["id"]), 1, 0)["id"]
    await start(client, match_id)

    response = await client.post(f"/v1/matches/{match_id}/start")
    assert response.status_code == 409


async def test_point_on_pending_match_is_rejected(client: AsyncClient) -> None:
    tournament = await create_tournament(client, 4)
    match = match_at(await get_bracket(client, tournament["id"]), 1, 0)

    response = await client.post(
        f"/v1/matches/{match['id']}/points", json={"team": "A", "expected_version": 1}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


async def test_points_increment_version_and_write_outbox(
    client: AsyncClient, session: AsyncSession
) -> None:
    tournament = await create_tournament(client, 4)
    match = await start(client, match_at(await get_bracket(client, tournament["id"]), 1, 0)["id"])

    match = await point(client, match, "A")
    match = await point(client, match, "B")
    match = await point(client, match, "A")
    assert match["games"] == [{"a": 2, "b": 1}]
    assert match["version"] == 5

    match_events = [
        e for e in await outbox_events(session) if e.aggregate_id == uuid.UUID(match["id"])
    ]
    assert [e.aggregate_version for e in match_events] == [1, 2, 3, 4, 5]
    assert match_events[-1].payload["games"] == [{"a": 2, "b": 1}]


async def test_version_conflict_returns_current_version_and_writes_nothing(
    client: AsyncClient, session: AsyncSession
) -> None:
    tournament = await create_tournament(client, 4)
    match = await start(client, match_at(await get_bracket(client, tournament["id"]), 1, 0)["id"])
    await point(client, match, "A")  # version 2 -> 3
    events_before = len(await outbox_events(session))

    response = await client.post(
        f"/v1/matches/{match['id']}/points", json={"team": "B", "expected_version": 2}
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "version_conflict"
    assert error["details"] == {"current_version": 3, "expected_version": 2}
    assert len(await outbox_events(session)) == events_before


async def test_finishing_match_advances_winner_and_bumps_both_versions(
    client: AsyncClient, session: AsyncSession
) -> None:
    tournament = await create_tournament(client, 8)
    bracket = await get_bracket(client, tournament["id"])
    first = match_at(bracket, 1, 1)  # seed 4 vs seed 5, feeds semi 0 slot B

    finished = await play_match(client, first["id"], winner="B")
    assert finished["status"] == "finished"
    assert finished["games"] == [{"a": 0, "b": 11}, {"a": 0, "b": 11}]
    assert finished["winner_team_id"] == first["team_b"]["id"]

    semi = match_at(await get_bracket(client, tournament["id"]), 2, 0)
    assert semi["team_a"] is None
    assert semi["team_b"]["seed"] == 5
    assert semi["version"] == 2

    events = await outbox_events(session)
    last_two = events[-2:]
    assert [(e.aggregate_id, e.event_type) for e in last_two] == [
        (uuid.UUID(first["id"]), "match_finished"),
        (uuid.UUID(semi["id"]), "match_updated"),
    ]
    assert last_two[1].payload["teamB"]["seed"] == 5
    assert last_two[1].aggregate_version == 2

    response = await client.post(
        f"/v1/matches/{first['id']}/points",
        json={"team": "A", "expected_version": finished["version"]},
    )
    assert response.status_code == 409


async def test_concurrent_points_with_same_version_one_wins(client: AsyncClient) -> None:
    tournament = await create_tournament(client, 4)
    match = await start(client, match_at(await get_bracket(client, tournament["id"]), 1, 0)["id"])

    body = {"team": "A", "expected_version": match["version"]}
    responses = await asyncio.gather(
        client.post(f"/v1/matches/{match['id']}/points", json=body),
        client.post(f"/v1/matches/{match['id']}/points", json=body),
    )

    assert sorted(r.status_code for r in responses) == [200, 409]
    loser = next(r for r in responses if r.status_code == 409)
    assert loser.json()["error"]["details"]["current_version"] == match["version"] + 1


async def test_idempotency_key_replays_response_without_reapplying(client: AsyncClient) -> None:
    tournament = await create_tournament(client, 4)
    match = await start(client, match_at(await get_bracket(client, tournament["id"]), 1, 0)["id"])

    url = f"/v1/matches/{match['id']}/points"
    body = {"team": "A", "expected_version": match["version"]}
    headers = {"Idempotency-Key": "point-123"}
    first = await client.post(url, json=body, headers=headers)
    second = await client.post(url, json=body, headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["games"] == [{"a": 1, "b": 0}]
    assert "Idempotent-Replayed" not in first.headers
    assert second.headers["Idempotent-Replayed"] == "true"

    reused = await client.post(url, json={**body, "team": "B"}, headers=headers)
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "idempotency_key_reused"


async def test_concurrent_requests_with_same_idempotency_key_apply_once(
    client: AsyncClient,
) -> None:
    tournament = await create_tournament(client, 4)
    match = await start(client, match_at(await get_bracket(client, tournament["id"]), 1, 0)["id"])

    url = f"/v1/matches/{match['id']}/points"
    body = {"team": "A", "expected_version": match["version"]}
    headers = {"Idempotency-Key": "concurrent-1"}
    responses = await asyncio.gather(
        *(client.post(url, json=body, headers=headers) for _ in range(3))
    )

    assert [r.status_code for r in responses] == [200, 200, 200]
    assert all(r.json()["games"] == [{"a": 1, "b": 0}] for r in responses)


async def test_idempotent_tournament_creation(client: AsyncClient) -> None:
    body = {"name": "Once", "teams": [{"name": f"T{i}"} for i in range(4)]}
    headers = {"Idempotency-Key": "create-once"}
    first = await client.post("/v1/tournaments", json=body, headers=headers)
    second = await client.post("/v1/tournaments", json=body, headers=headers)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_game_correction(client: AsyncClient) -> None:
    tournament = await create_tournament(client, 4)
    match = await start(client, match_at(await get_bracket(client, tournament["id"]), 1, 0)["id"])
    match = await point(client, match, "A")

    response = await client.put(
        f"/v1/matches/{match['id']}/games/0",
        json={"a": 10, "b": 9, "expected_version": match["version"]},
    )
    assert response.status_code == 200, response.text
    corrected = response.json()
    assert corrected["games"] == [{"a": 10, "b": 9}]
    assert corrected["version"] == match["version"] + 1

    impossible = await client.put(
        f"/v1/matches/{match['id']}/games/0",
        json={"a": 15, "b": 3, "expected_version": corrected["version"]},
    )
    assert impossible.status_code == 422
    assert impossible.json()["error"]["code"] == "invalid_score"


async def test_unknown_match_returns_404(client: AsyncClient) -> None:
    response = await client.post(
        f"/v1/matches/{uuid.uuid4()}/points", json={"team": "A", "expected_version": 1}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_invalid_body_uses_error_format(client: AsyncClient) -> None:
    response = await client.post(
        f"/v1/matches/{uuid.uuid4()}/points", json={"team": "C", "expected_version": 0}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
