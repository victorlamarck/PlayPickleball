from typing import Any

from app.readmodel.firestore_publisher import document_path
from app.readmodel.notifier import match_notification

PAYLOAD: dict[str, Any] = {
    "tournamentId": "t1",
    "teamA": {"id": "a", "name": "Dink Dynasty", "seed": 1},
    "teamB": {"id": "b", "name": "Spin Doctors", "seed": 8},
    "games": [{"a": 11, "b": 7}, {"a": 9, "b": 11}, {"a": 11, "b": 5}],
    "winnerTeamId": "a",
}


def test_match_started_notification() -> None:
    assert match_notification("match_started", "m1", PAYLOAD) == (
        "tournament_t1",
        "Match started",
        "Dink Dynasty vs Spin Doctors",
        {"matchId": "m1", "event": "match_started"},
    )


def test_match_finished_notification_names_winner_and_score() -> None:
    notification = match_notification("match_finished", "m1", PAYLOAD)
    assert notification is not None
    _, title, body, _ = notification
    assert title == "Final result"
    assert body == "Dink Dynasty wins: Dink Dynasty vs Spin Doctors (11-7, 9-11, 11-5)"


def test_other_events_do_not_notify() -> None:
    assert match_notification("match_updated", "m1", PAYLOAD) is None


def test_document_paths() -> None:
    assert document_path("tournament", "t1", {}) == "tournaments/t1"
    assert document_path("match", "m1", {"tournamentId": "t1"}) == "tournaments/t1/matches/m1"
