import uuid

from app.models import Match, Team, Tournament
from app.readmodel.projector import project_match, project_tournament

TOURNAMENT_ID = uuid.uuid4()


def make_team(seed: int, name: str) -> Team:
    return Team(id=uuid.uuid4(), tournament_id=TOURNAMENT_ID, name=name, seed=seed)


def test_project_live_match() -> None:
    a, b = make_team(1, "Dink Dynasty"), make_team(8, "Spin Doctors")
    match = Match(
        id=uuid.uuid4(),
        tournament_id=TOURNAMENT_ID,
        round=1,
        position=0,
        team_a_id=a.id,
        team_b_id=b.id,
        status="live",
        games=[{"a": 11, "b": 7}, {"a": 4, "b": 2}],
        winner_team_id=None,
        version=23,
    )

    assert project_match(match, {a.id: a, b.id: b}) == {
        "tournamentId": str(TOURNAMENT_ID),
        "round": 1,
        "position": 0,
        "teamA": {"id": str(a.id), "name": "Dink Dynasty", "seed": 1},
        "teamB": {"id": str(b.id), "name": "Spin Doctors", "seed": 8},
        "status": "live",
        "games": [{"a": 11, "b": 7}, {"a": 4, "b": 2}],
        "winnerTeamId": None,
        "version": 23,
    }


def test_project_future_match_without_teams() -> None:
    match = Match(
        id=uuid.uuid4(),
        tournament_id=TOURNAMENT_ID,
        round=2,
        position=1,
        team_a_id=None,
        team_b_id=None,
        status="pending",
        games=[],
        version=1,
    )
    doc = project_match(match, {})
    assert doc["teamA"] is None
    assert doc["teamB"] is None
    assert doc["games"] == []


def test_project_finished_match_has_winner() -> None:
    a, b = make_team(1, "A"), make_team(2, "B")
    match = Match(
        id=uuid.uuid4(),
        tournament_id=TOURNAMENT_ID,
        round=3,
        position=0,
        team_a_id=a.id,
        team_b_id=b.id,
        status="finished",
        games=[{"a": 11, "b": 0}, {"a": 11, "b": 0}],
        winner_team_id=a.id,
        version=30,
    )
    assert project_match(match, {a.id: a, b.id: b})["winnerTeamId"] == str(a.id)


def test_project_tournament() -> None:
    tournament = Tournament(
        id=TOURNAMENT_ID, name="Demo Open", status="in_progress", rounds=3, version=7
    )
    assert project_tournament(tournament) == {
        "name": "Demo Open",
        "status": "in_progress",
        "rounds": 3,
        "version": 7,
    }
