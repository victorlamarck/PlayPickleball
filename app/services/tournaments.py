"""Tournament creation and reads."""

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import bracket
from app.errors import NotFoundError
from app.models import Match, MatchStatus, Team, Tournament, TournamentStatus
from app.outbox.events import EventType, record_match_event, record_tournament_event
from app.schemas import BracketOut, RoundOut, TournamentOut
from app.services.views import load_teams, match_out, tournament_out


async def create_tournament(
    session: AsyncSession, name: str, team_names: list[str]
) -> TournamentOut:
    """Create the tournament, its seeded teams and the full bracket. Call inside a transaction."""
    plans = bracket.generate_bracket(len(team_names))

    tournament = Tournament(
        id=uuid.uuid4(),
        name=name,
        status=TournamentStatus.SCHEDULED,
        rounds=bracket.round_count(len(team_names)),
        version=1,
    )
    teams = [
        Team(id=uuid.uuid4(), tournament_id=tournament.id, name=team_name, seed=seed)
        for seed, team_name in enumerate(team_names, start=1)
    ]
    team_by_seed = {team.seed: team for team in teams}
    teams_by_id = {team.id: team for team in teams}

    matches = {
        (plan.round, plan.position): Match(
            id=uuid.uuid4(),
            tournament_id=tournament.id,
            round=plan.round,
            position=plan.position,
            status=MatchStatus.PENDING,
            games=[],
            version=1,
        )
        for plan in plans
    }
    for plan in plans:
        match = matches[(plan.round, plan.position)]
        if plan.seed_a is not None and plan.seed_b is not None:
            match.team_a_id = team_by_seed[plan.seed_a].id
            match.team_b_id = team_by_seed[plan.seed_b].id
        if plan.next is not None:
            match.next_match_id = matches[(plan.next.round, plan.next.position)].id
            match.next_slot = plan.next.slot

    # Explicit flush order: no ORM relationships, so FK targets must be inserted first.
    # Later rounds go first because earlier matches reference them via next_match_id.
    session.add(tournament)
    await session.flush()
    session.add_all(teams)
    await session.flush()
    final_first: list[Match] = sorted(matches.values(), key=lambda m: (-m.round, m.position))
    session.add_all(final_first)
    await session.flush()

    # Seed the read model with every document so clients can render the empty bracket.
    record_tournament_event(session, tournament)
    for match in sorted(matches.values(), key=lambda m: (m.round, m.position)):
        record_match_event(session, match, teams_by_id, EventType.MATCH_UPDATED)

    return tournament_out(tournament, teams_by_id)


async def _get_tournament(session: AsyncSession, tournament_id: uuid.UUID) -> Tournament:
    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise NotFoundError("Tournament not found", {"tournament_id": str(tournament_id)})
    return tournament


async def get_tournament(session: AsyncSession, tournament_id: uuid.UUID) -> TournamentOut:
    tournament = await _get_tournament(session, tournament_id)
    return tournament_out(tournament, await load_teams(session, tournament_id))


async def get_bracket(session: AsyncSession, tournament_id: uuid.UUID) -> BracketOut:
    tournament = await _get_tournament(session, tournament_id)
    teams = await load_teams(session, tournament_id)
    matches = await session.scalars(
        select(Match)
        .where(Match.tournament_id == tournament_id)
        .order_by(Match.round, Match.position)
    )
    by_round: dict[int, list[Match]] = defaultdict(list)
    for match in matches:
        by_round[match.round].append(match)
    return BracketOut(
        tournament=tournament_out(tournament, teams),
        rounds=[
            RoundOut(round=round_, matches=[match_out(m, teams) for m in by_round[round_]])
            for round_ in sorted(by_round)
        ],
    )
