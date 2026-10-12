"""Build API response models from ORM rows (inside the session, so nothing lazy-loads later)."""

import uuid
from collections.abc import Mapping
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, Team, Tournament
from app.schemas import GameOut, MatchOut, TeamOut, TournamentOut


async def load_teams(session: AsyncSession, tournament_id: uuid.UUID) -> dict[uuid.UUID, Team]:
    rows = await session.scalars(select(Team).where(Team.tournament_id == tournament_id))
    return {team.id: team for team in rows}


def team_out(team: Team) -> TeamOut:
    return TeamOut(id=team.id, name=team.name, seed=team.seed)


def tournament_out(tournament: Tournament, teams: Mapping[uuid.UUID, Team]) -> TournamentOut:
    return TournamentOut(
        id=tournament.id,
        name=tournament.name,
        status=cast(Literal["scheduled", "in_progress", "finished"], str(tournament.status)),
        rounds=tournament.rounds,
        version=tournament.version,
        teams=[team_out(t) for t in sorted(teams.values(), key=lambda t: t.seed)],
        created_at=tournament.created_at,
        updated_at=tournament.updated_at,
    )


def match_out(match: Match, teams: Mapping[uuid.UUID, Team]) -> MatchOut:
    return MatchOut(
        id=match.id,
        tournament_id=match.tournament_id,
        round=match.round,
        position=match.position,
        team_a=team_out(teams[match.team_a_id]) if match.team_a_id else None,
        team_b=team_out(teams[match.team_b_id]) if match.team_b_id else None,
        status=cast(Literal["pending", "live", "finished"], str(match.status)),
        games=[GameOut(a=g["a"], b=g["b"]) for g in match.games],
        winner_team_id=match.winner_team_id,
        next_match_id=match.next_match_id,
        next_slot=cast(Literal["A", "B"] | None, match.next_slot),
        version=match.version,
        updated_at=match.updated_at,
    )
