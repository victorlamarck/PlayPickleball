"""SQLAlchemy models. Postgres is the source of truth."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def uuid_pk() -> Mapped[uuid.UUID]:
    # Generated client-side so related rows (e.g. next_match_id) can be linked before insert;
    # the server default keeps raw SQL inserts working too.
    return mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


def updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now()
    )


class TournamentStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


class MatchStatus(StrEnum):
    PENDING = "pending"
    LIVE = "live"
    FINISHED = "finished"


class Tournament(Base):
    __tablename__ = "tournaments"
    __table_args__ = (
        CheckConstraint("status IN ('scheduled', 'in_progress', 'finished')", name="status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default=TournamentStatus.SCHEDULED)
    rounds: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("tournament_id", "seed"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    tournament_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    seed: Mapped[int] = mapped_column(Integer)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("tournament_id", "round", "position"),
        CheckConstraint("status IN ('pending', 'live', 'finished')", name="status"),
        CheckConstraint("next_slot IN ('A', 'B')", name="next_slot"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tournament_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE")
    )
    round: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    team_a_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    team_b_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    status: Mapped[str] = mapped_column(Text, default=MatchStatus.PENDING)
    games: Mapped[list[dict[str, int]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    winner_team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    next_match_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("matches.id"))
    next_slot: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = updated_at()


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint("aggregate_type IN ('match', 'tournament')", name="aggregate_type"),
        Index(
            "ix_outbox_events_pending",
            "id",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(Text)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    aggregate_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)


class IdempotencyKey(Base):
    """Stored responses for `Idempotency-Key` replays. Rows older than 24h may be deleted."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    request_hash: Mapped[str] = mapped_column(Text)
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()
