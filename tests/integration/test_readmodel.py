"""Read model tests against the Firestore emulator."""

import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from google.cloud.firestore import AsyncClient as FirestoreClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent
from app.outbox.relay import OutboxRelay
from app.readmodel.firestore_publisher import FirestorePublisher
from app.readmodel.notifier import LoggingNotifier
from app.services import matches
from app.services.idempotency import execute_write
from tests.integration.conftest import FIRESTORE_EMULATOR_HOST, INTERNAL_TOKEN
from tests.integration.helpers import (
    create_tournament,
    get_bracket,
    match_at,
    outbox_events,
    point,
    start,
)

ROOT = Path(__file__).resolve().parents[2]


async def read_doc(firestore_client: FirestoreClient, path: str) -> dict[str, Any] | None:
    snapshot = await firestore_client.document(path).get()
    return snapshot.to_dict() if snapshot.exists else None


async def match_doc(
    firestore_client: FirestoreClient, match: dict[str, Any]
) -> dict[str, Any] | None:
    return await read_doc(
        firestore_client, f"tournaments/{match['tournament_id']}/matches/{match['id']}"
    )


class FailingPublisher:
    async def publish(
        self, aggregate_type: str, aggregate_id: str, payload: dict[str, Any]
    ) -> bool:
        raise RuntimeError("firestore unavailable")


class RecordingNotifier:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.fail = fail

    async def notify(self, topic: str, title: str, body: str, data: dict[str, str]) -> None:
        if self.fail:
            raise RuntimeError("fcm down")
        self.sent.append((topic, title, body))


def tournament_event(aggregate_id: uuid.UUID, version: int, name: str = "Open") -> OutboxEvent:
    return OutboxEvent(
        aggregate_type="tournament",
        aggregate_id=aggregate_id,
        aggregate_version=version,
        event_type="tournament_updated",
        payload={"name": name, "status": "scheduled", "rounds": 2, "version": version},
    )


async def test_scoring_flow_updates_firestore_with_increasing_versions(
    client: AsyncClient, firestore_client: FirestoreClient, session: AsyncSession
) -> None:
    tournament = await create_tournament(client, 4)

    # The post-commit fast path already published the whole empty bracket.
    tournament_doc = await read_doc(firestore_client, f"tournaments/{tournament['id']}")
    assert tournament_doc is not None
    assert tournament_doc["status"] == "scheduled"
    assert tournament_doc["version"] == 1
    assert "updatedAt" in tournament_doc
    matches = firestore_client.collection(f"tournaments/{tournament['id']}/matches")
    assert len([doc async for doc in matches.stream()]) == 3

    bracket = await get_bracket(client, tournament["id"])
    final = match_at(bracket, 2, 0)
    match = await start(client, match_at(bracket, 1, 0)["id"])
    seen_versions = []
    while match["status"] != "finished":
        match = await point(client, match, "A")
        doc = await match_doc(firestore_client, match)
        assert doc is not None
        seen_versions.append(doc["version"])
        assert doc["version"] == match["version"]

    assert seen_versions == sorted(seen_versions)
    assert len(set(seen_versions)) == len(seen_versions)

    finished_doc = await match_doc(firestore_client, match)
    assert finished_doc is not None
    assert finished_doc["status"] == "finished"
    assert finished_doc["winnerTeamId"] == match["team_a"]["id"]

    final_doc = await match_doc(firestore_client, final)
    assert final_doc is not None
    assert final_doc["version"] == 2
    assert final_doc["teamA"]["id"] == match["team_a"]["id"]
    assert final_doc["teamB"] is None

    assert all(e.published_at is not None for e in await outbox_events(session))


async def test_out_of_order_publish_keeps_newest_version(
    firestore_client: FirestoreClient,
) -> None:
    publisher = FirestorePublisher(firestore_client)
    aggregate_id = str(uuid.uuid4())
    payload = {"name": "Open", "status": "in_progress", "rounds": 2}

    assert await publisher.publish("tournament", aggregate_id, {**payload, "version": 5})
    assert not await publisher.publish("tournament", aggregate_id, {**payload, "version": 4})
    assert not await publisher.publish("tournament", aggregate_id, {**payload, "version": 5})

    doc = await read_doc(firestore_client, f"tournaments/{aggregate_id}")
    assert doc is not None
    assert doc["version"] == 5


async def test_failed_publish_stays_pending_and_next_drain_publishes(
    app: FastAPI, session: AsyncSession, firestore_client: FirestoreClient
) -> None:
    aggregate_id = uuid.uuid4()
    session.add(tournament_event(aggregate_id, 1))
    await session.commit()

    failing = OutboxRelay(app.state.session_factory, FailingPublisher(), LoggingNotifier())
    result = await failing.drain()
    assert (result.published, result.failed, result.remaining) == (0, 1, 1)

    [event] = await outbox_events(session)
    assert event.published_at is None
    assert event.attempts == 1
    assert event.last_error is not None and "firestore unavailable" in event.last_error

    working = OutboxRelay(
        app.state.session_factory, FirestorePublisher(firestore_client), LoggingNotifier()
    )
    result = await working.drain()
    assert (result.published, result.failed, result.remaining) == (1, 0, 0)
    [event] = await outbox_events(session)
    assert event.published_at is not None
    assert await read_doc(firestore_client, f"tournaments/{aggregate_id}") is not None


async def test_drain_coalesces_versions_of_same_aggregate(
    app: FastAPI, session: AsyncSession, firestore_client: FirestoreClient
) -> None:
    aggregate_id = uuid.uuid4()
    session.add_all([tournament_event(aggregate_id, v, name=f"v{v}") for v in (1, 2, 3)])
    await session.commit()

    relay = OutboxRelay(
        app.state.session_factory, FirestorePublisher(firestore_client), LoggingNotifier()
    )
    result = await relay.drain()

    assert (result.published, result.failed, result.remaining) == (3, 0, 0)
    doc = await read_doc(firestore_client, f"tournaments/{aggregate_id}")
    assert doc is not None
    assert (doc["name"], doc["version"]) == ("v3", 3)


async def test_notifications_for_started_and_finished_matches(
    app: FastAPI, client: AsyncClient, firestore_client: FirestoreClient
) -> None:
    tournament = await create_tournament(client, 4)
    match_id = match_at(await get_bracket(client, tournament["id"]), 1, 0)["id"]

    # Write directly through the services so the fast path does not drain first.
    async with app.state.session_factory() as db:
        await execute_write(db, None, lambda: matches.start_match(db, uuid.UUID(match_id)))
    for version in range(2, 24):
        async with app.state.session_factory() as db:
            await execute_write(
                db, None, lambda v=version: matches.add_point(db, uuid.UUID(match_id), "A", v)
            )

    notifier = RecordingNotifier()
    relay = OutboxRelay(app.state.session_factory, FirestorePublisher(firestore_client), notifier)
    await relay.drain()

    topic = f"tournament_{tournament['id']}"
    assert [(t, title) for t, title, _ in notifier.sent] == [
        (topic, "Match started"),
        (topic, "Final result"),
    ]
    assert notifier.sent[1][2].startswith("Team 1 wins")


async def test_notification_failure_does_not_block_publishing(
    app: FastAPI, session: AsyncSession, firestore_client: FirestoreClient
) -> None:
    match_id = uuid.uuid4()
    tournament_id = uuid.uuid4()
    session.add(
        OutboxEvent(
            aggregate_type="match",
            aggregate_id=match_id,
            aggregate_version=2,
            event_type="match_started",
            payload={
                "tournamentId": str(tournament_id),
                "teamA": None,
                "teamB": None,
                "status": "live",
                "games": [],
                "version": 2,
            },
        )
    )
    await session.commit()

    relay = OutboxRelay(
        app.state.session_factory,
        FirestorePublisher(firestore_client),
        RecordingNotifier(fail=True),
    )
    result = await relay.drain()

    assert result.published == 1
    assert await read_doc(firestore_client, f"tournaments/{tournament_id}/matches/{match_id}")


async def test_drain_endpoint_requires_internal_token(anon_client: AsyncClient) -> None:
    response = await anon_client.post("/internal/outbox/drain")
    assert response.status_code == 401

    response = await anon_client.post(
        "/internal/outbox/drain", headers={"X-Internal-Token": INTERNAL_TOKEN}
    )
    assert response.status_code == 200
    assert response.json() == {"published": 0, "failed": 0, "remaining": 0}


async def test_drain_endpoint_publishes_pending_events(
    anon_client: AsyncClient, session: AsyncSession, firestore_client: FirestoreClient
) -> None:
    ids = [uuid.uuid4() for _ in range(3)]
    session.add_all([tournament_event(i, 1) for i in ids])
    await session.commit()

    response = await anon_client.post(
        "/internal/outbox/drain", headers={"X-Internal-Token": INTERNAL_TOKEN}
    )
    assert response.json() == {"published": 3, "failed": 0, "remaining": 0}
    for i in ids:
        assert await read_doc(firestore_client, f"tournaments/{i}") is not None


async def test_security_rules_allow_public_reads_and_deny_client_writes() -> None:
    """Loads firestore.rules into the emulator and calls it as an unauthenticated client."""
    base = f"http://{FIRESTORE_EMULATOR_HOST}"
    project = "demo-rules-test"
    rules = (ROOT / "firestore.rules").read_text(encoding="utf-8")
    documents = f"{base}/v1/projects/{project}/databases/(default)/documents"
    doc = {"fields": {"version": {"integerValue": "1"}}}

    async with httpx.AsyncClient() as http:
        loaded = await http.put(
            f"{base}/emulator/v1/projects/{project}:securityRules",
            json={"rules": {"files": [{"name": "firestore.rules", "content": rules}]}},
        )
        assert loaded.status_code == 200, loaded.text

        # Seed a document as an admin (the "owner" token bypasses rules in the emulator).
        admin = {"Authorization": "Bearer owner"}
        seeded = await http.patch(f"{documents}/tournaments/t1", json=doc, headers=admin)
        assert seeded.status_code == 200, seeded.text

        assert (await http.get(f"{documents}/tournaments/t1")).status_code == 200
        assert (await http.get(f"{documents}/tournaments/t1/matches/m1")).status_code == 404
        assert (await http.patch(f"{documents}/tournaments/t1", json=doc)).status_code == 403
        assert (
            await http.patch(f"{documents}/tournaments/t1/matches/m1", json=doc)
        ).status_code == 403
        assert (await http.get(f"{documents}/users/u1")).status_code == 403
        assert (await http.delete(f"{documents}/tournaments/t1")).status_code == 403
