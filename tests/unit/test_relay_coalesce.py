import uuid
from typing import Any

from app.outbox.relay import PendingEvent, coalesce

MATCH_1 = uuid.uuid4()
MATCH_2 = uuid.uuid4()
TOURNAMENT = uuid.uuid4()


def event(
    id_: int,
    aggregate_id: uuid.UUID,
    version: int,
    event_type: str = "match_updated",
    aggregate_type: str = "match",
) -> PendingEvent:
    payload: dict[str, Any] = {"version": version}
    return PendingEvent(id_, aggregate_type, aggregate_id, version, event_type, payload)


def test_empty_batch() -> None:
    assert coalesce([]) == []


def test_keeps_only_latest_version_per_aggregate() -> None:
    groups = coalesce([event(1, MATCH_1, 2), event(2, MATCH_1, 3), event(3, MATCH_1, 4)])
    assert len(groups) == 1
    assert groups[0].latest.aggregate_version == 4
    assert groups[0].event_ids == [1, 2, 3]


def test_latest_is_by_version_not_by_id() -> None:
    groups = coalesce([event(1, MATCH_1, 5), event(2, MATCH_1, 4)])
    assert groups[0].latest.id == 1


def test_groups_per_aggregate_in_first_seen_order() -> None:
    groups = coalesce(
        [
            event(1, MATCH_2, 7),
            event(2, MATCH_1, 3),
            event(3, MATCH_2, 8),
            event(4, TOURNAMENT, 2, "tournament_updated", "tournament"),
        ]
    )
    assert [(g.latest.aggregate_id, g.latest.aggregate_version) for g in groups] == [
        (MATCH_2, 8),
        (MATCH_1, 3),
        (TOURNAMENT, 2),
    ]


def test_same_id_different_aggregate_type_are_separate_groups() -> None:
    shared = uuid.uuid4()
    groups = coalesce(
        [event(1, shared, 1), event(2, shared, 1, "tournament_updated", "tournament")]
    )
    assert len(groups) == 2


def test_notifications_survive_coalescing() -> None:
    # match_started is superseded by later points, but its notification must still be sent.
    groups = coalesce(
        [
            event(1, MATCH_1, 2, "match_started"),
            event(2, MATCH_1, 3),
            event(3, MATCH_1, 4),
        ]
    )
    assert groups[0].latest.event_type == "match_updated"
    assert [e.event_type for e in groups[0].notify] == ["match_started"]


def test_updates_do_not_notify() -> None:
    groups = coalesce([event(1, MATCH_1, 2), event(2, TOURNAMENT, 2, "tournament_updated")])
    assert all(g.notify == [] for g in groups)
