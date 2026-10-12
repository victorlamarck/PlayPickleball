"""Writing outbox rows. Callers must be inside the transaction that changes the aggregate."""

import uuid
from collections.abc import Mapping
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, OutboxEvent, Team, Tournament
from app.readmodel.projector import project_match, project_tournament


class EventType(StrEnum):
    MATCH_UPDATED = "match_updated"
    MATCH_STARTED = "match_started"
    MATCH_FINISHED = "match_finished"
    TOURNAMENT_UPDATED = "tournament_updated"


def record_match_event(
    session: AsyncSession, match: Match, teams: Mapping[uuid.UUID, Team], event_type: EventType
) -> None:
    session.add(
        OutboxEvent(
            aggregate_type="match",
            aggregate_id=match.id,
            aggregate_version=match.version,
            event_type=event_type,
            payload=project_match(match, teams),
        )
    )


def record_tournament_event(session: AsyncSession, tournament: Tournament) -> None:
    session.add(
        OutboxEvent(
            aggregate_type="tournament",
            aggregate_id=tournament.id,
            aggregate_version=tournament.version,
            event_type=EventType.TOURNAMENT_UPDATED,
            payload=project_tournament(tournament),
        )
    )
