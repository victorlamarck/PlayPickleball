"""The single place that turns Postgres state into Firestore document dicts.

The outbox payload is exactly this dict; `updatedAt` is added by the publisher at write time.
"""

import uuid
from collections.abc import Mapping
from typing import Any

from app.models import Match, Team, Tournament


def _team(team_id: uuid.UUID | None, teams: Mapping[uuid.UUID, Team]) -> dict[str, Any] | None:
    if team_id is None:
        return None
    team = teams[team_id]
    return {"id": str(team.id), "name": team.name, "seed": team.seed}


def project_match(match: Match, teams: Mapping[uuid.UUID, Team]) -> dict[str, Any]:
    """Document for `tournaments/{tournamentId}/matches/{matchId}`."""
    return {
        "tournamentId": str(match.tournament_id),
        "round": match.round,
        "position": match.position,
        "teamA": _team(match.team_a_id, teams),
        "teamB": _team(match.team_b_id, teams),
        "status": str(match.status),
        "games": [{"a": g["a"], "b": g["b"]} for g in match.games],
        "winnerTeamId": str(match.winner_team_id) if match.winner_team_id else None,
        "version": match.version,
    }


def project_tournament(tournament: Tournament) -> dict[str, Any]:
    """Document for `tournaments/{tournamentId}`."""
    return {
        "name": tournament.name,
        "status": str(tournament.status),
        "rounds": tournament.rounds,
        "version": tournament.version,
    }
