"""Match writes: start, score points, correct games, finish and advance the bracket.

Every write locks the affected rows with SELECT ... FOR UPDATE, checks `expected_version` in the
same transaction, bumps `version` on each changed row and records one outbox event per change.
Lock order is always: matches (ordered by id), then the tournament, so concurrent writes on
neighbouring matches cannot deadlock. Call these functions inside a transaction.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import bracket, scoring
from app.domain.scoring import GameScore
from app.errors import InvalidStateError, NotFoundError, VersionConflictError
from app.models import Match, MatchStatus, Team, Tournament, TournamentStatus
from app.outbox.events import EventType, record_match_event, record_tournament_event
from app.schemas import MatchOut
from app.services.views import load_teams, match_out


async def start_match(session: AsyncSession, match_id: uuid.UUID) -> MatchOut:
    """pending -> live. Both teams must be known. Moves a scheduled tournament to in_progress."""
    match, _ = await _lock_match_and_next(session, match_id)
    if match.status != MatchStatus.PENDING:
        raise InvalidStateError("Only pending matches can be started", {"status": match.status})
    if match.team_a_id is None or match.team_b_id is None:
        raise InvalidStateError("Both teams must be known before the match starts")

    match.status = MatchStatus.LIVE
    match.games = [asdict(GameScore(0, 0))]
    match.version += 1

    teams = await load_teams(session, match.tournament_id)
    record_match_event(session, match, teams, EventType.MATCH_STARTED)

    tournament = await _lock_tournament(session, match.tournament_id)
    if tournament.status == TournamentStatus.SCHEDULED:
        tournament.status = TournamentStatus.IN_PROGRESS
        tournament.version += 1
        record_tournament_event(session, tournament)

    return match_out(match, teams)


async def add_point(
    session: AsyncSession, match_id: uuid.UUID, team: scoring.Team, expected_version: int
) -> MatchOut:
    match, next_match = await _lock_match_and_next(session, match_id)
    _check_version(match, expected_version)
    _require_live(match)
    games = scoring.add_point(_games(match), team)
    return await _apply_games(session, match, next_match, games)


async def correct_game(
    session: AsyncSession,
    match_id: uuid.UUID,
    game_index: int,
    a: int,
    b: int,
    expected_version: int,
) -> MatchOut:
    match, next_match = await _lock_match_and_next(session, match_id)
    _check_version(match, expected_version)
    _require_live(match)
    games = scoring.set_game_score(_games(match), game_index, a, b)
    return await _apply_games(session, match, next_match, games)


async def _apply_games(
    session: AsyncSession, match: Match, next_match: Match | None, games: Sequence[GameScore]
) -> MatchOut:
    match.games = [asdict(g) for g in games]
    match.version += 1
    teams = await load_teams(session, match.tournament_id)

    winner = scoring.is_match_decided(games)
    if winner is None:
        record_match_event(session, match, teams, EventType.MATCH_UPDATED)
        return match_out(match, teams)

    winner_id = match.team_a_id if winner == "A" else match.team_b_id
    assert winner_id is not None  # live matches always have both teams
    match.status = MatchStatus.FINISHED
    match.winner_team_id = winner_id
    record_match_event(session, match, teams, EventType.MATCH_FINISHED)

    if next_match is not None:
        _advance_winner(session, match, next_match, winner_id, teams)
    else:
        tournament = await _lock_tournament(session, match.tournament_id)
        tournament.status = TournamentStatus.FINISHED
        tournament.version += 1
        record_tournament_event(session, tournament)

    return match_out(match, teams)


def _advance_winner(
    session: AsyncSession,
    match: Match,
    next_match: Match,
    winner_id: uuid.UUID,
    teams: Mapping[uuid.UUID, Team],
) -> None:
    assert match.next_slot in ("A", "B")
    placed = bracket.place_winner(
        bracket.MatchTeams(next_match.team_a_id, next_match.team_b_id),
        "A" if match.next_slot == "A" else "B",
        winner_id,
    )
    next_match.team_a_id, next_match.team_b_id = placed.team_a, placed.team_b
    next_match.version += 1
    record_match_event(session, next_match, teams, EventType.MATCH_UPDATED)


async def _lock_match_and_next(
    session: AsyncSession, match_id: uuid.UUID
) -> tuple[Match, Match | None]:
    """Lock the match and the match its winner feeds into, in id order (deadlock-free)."""
    # next_match_id never changes after creation, so reading it before locking is safe.
    row = (
        await session.execute(select(Match.next_match_id).where(Match.id == match_id))
    ).one_or_none()
    if row is None:
        raise NotFoundError("Match not found", {"match_id": str(match_id)})
    next_match_id: uuid.UUID | None = row[0]

    ids = [match_id] if next_match_id is None else [match_id, next_match_id]
    rows = await session.scalars(
        select(Match)
        .where(Match.id.in_(ids))
        .order_by(Match.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    by_id = {m.id: m for m in rows}
    return by_id[match_id], by_id.get(next_match_id) if next_match_id else None


async def _lock_tournament(session: AsyncSession, tournament_id: uuid.UUID) -> Tournament:
    tournament = await session.scalar(
        select(Tournament)
        .where(Tournament.id == tournament_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert tournament is not None  # FK guarantees it
    return tournament


def _check_version(match: Match, expected_version: int) -> None:
    if match.version != expected_version:
        raise VersionConflictError(match.version, expected_version)


def _require_live(match: Match) -> None:
    if match.status != MatchStatus.LIVE:
        raise InvalidStateError("Match is not live", {"status": str(match.status)})


def _games(match: Match) -> list[GameScore]:
    return [GameScore(g["a"], g["b"]) for g in match.games]
