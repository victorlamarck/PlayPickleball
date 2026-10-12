"""Outbox relay: publishes pending events to the Firestore read model.

One drain:
1. Locks a batch of pending events (FOR UPDATE SKIP LOCKED), so concurrent drains never
   publish the same rows.
2. Coalesces them per aggregate and publishes only the newest version of each.
3. Publishes with bounded concurrency. Success marks the whole group as published (older events
   were superseded). Failure bumps `attempts`/`last_error` on the newest event; the group stays
   pending and is retried by the next drain.
4. After commit, sends push notifications for match_started / match_finished events of the
   published groups. Notification failures are logged and never block publishing.
"""

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import OutboxEvent
from app.readmodel.firestore_publisher import Publisher
from app.readmodel.notifier import Notifier, match_notification

logger = structlog.get_logger()

MAX_ERROR_LENGTH = 1000


@dataclass(frozen=True, slots=True)
class PendingEvent:
    id: int
    aggregate_type: str
    aggregate_id: uuid.UUID
    aggregate_version: int
    event_type: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PublishGroup:
    """All pending events of one aggregate in a batch; only `latest` is published."""

    latest: PendingEvent
    event_ids: list[int]
    notify: list[PendingEvent] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DrainResult:
    published: int  # events marked as published (including superseded ones)
    failed: int  # events whose publish attempt failed (one per failed aggregate)
    remaining: int  # events still pending after this drain


NOTIFY_EVENT_TYPES = frozenset({"match_started", "match_finished"})


def coalesce(events: Sequence[PendingEvent]) -> list[PublishGroup]:
    """Group events by aggregate, keep the highest version. Pure; preserves first-seen order."""
    groups: dict[tuple[str, uuid.UUID], list[PendingEvent]] = {}
    for event in events:
        groups.setdefault((event.aggregate_type, event.aggregate_id), []).append(event)
    return [
        PublishGroup(
            latest=max(group, key=lambda e: (e.aggregate_version, e.id)),
            event_ids=[e.id for e in group],
            notify=[e for e in group if e.event_type in NOTIFY_EVENT_TYPES],
        )
        for group in groups.values()
    ]


class OutboxRelay:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        publisher: Publisher,
        notifier: Notifier,
        *,
        concurrency: int = 20,
        publish_timeout: float = 10.0,
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher
        self._notifier = notifier
        self._concurrency = concurrency
        self._publish_timeout = publish_timeout

    async def drain(self, batch_size: int = 200) -> DrainResult:
        published_groups: list[PublishGroup] = []
        failed = 0
        async with self._session_factory() as session, session.begin():
            rows = await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            groups = coalesce([_to_pending(row) for row in rows])

            semaphore = asyncio.Semaphore(self._concurrency)
            errors = await asyncio.gather(*(self._publish(g, semaphore) for g in groups))

            for group, error in zip(groups, errors, strict=True):
                if error is None:
                    published_groups.append(group)
                else:
                    failed += 1
                    await session.execute(
                        update(OutboxEvent)
                        .where(OutboxEvent.id == group.latest.id)
                        .values(
                            attempts=OutboxEvent.attempts + 1,
                            last_error=error[:MAX_ERROR_LENGTH],
                        )
                    )
            published_ids = [i for g in published_groups for i in g.event_ids]
            if published_ids:
                await session.execute(
                    update(OutboxEvent)
                    .where(OutboxEvent.id.in_(published_ids))
                    .values(published_at=func.now())
                )

        await self._send_notifications(published_groups)
        result = DrainResult(len(published_ids), failed, await self.pending_count())
        if result.published or result.failed:
            logger.info("outbox_drained", **asdict(result))
        return result

    async def drain_until_empty(self, batch_size: int = 200, max_batches: int = 10) -> DrainResult:
        """Drain repeatedly while full batches keep succeeding (used by the scheduled endpoint)."""
        published = failed = 0
        result = DrainResult(0, 0, 0)
        for _ in range(max_batches):
            result = await self.drain(batch_size)
            published += result.published
            failed += result.failed
            if result.failed or result.remaining == 0:
                break
        return DrainResult(published, failed, result.remaining)

    async def drain_safely(self) -> None:
        """Fast path after a write (BackgroundTasks): never raises into the request cycle."""
        try:
            await self.drain()
        except Exception:
            logger.exception("outbox_drain_failed")

    async def pending_count(self) -> int:
        async with self._session_factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
            )
        return int(count or 0)

    async def _publish(self, group: PublishGroup, semaphore: asyncio.Semaphore) -> str | None:
        event = group.latest
        async with semaphore:
            try:
                await asyncio.wait_for(
                    self._publisher.publish(
                        event.aggregate_type, str(event.aggregate_id), event.payload
                    ),
                    timeout=self._publish_timeout,
                )
            except Exception as exc:
                logger.warning(
                    "outbox_publish_failed",
                    event_id=event.id,
                    aggregate_id=str(event.aggregate_id),
                    error=repr(exc),
                )
                return repr(exc)
        return None

    async def _send_notifications(self, groups: Sequence[PublishGroup]) -> None:
        for event in (e for g in groups for e in g.notify):
            notification = match_notification(
                event.event_type, str(event.aggregate_id), event.payload
            )
            if notification is None:
                continue
            topic, title, body, data = notification
            try:
                await self._notifier.notify(topic, title, body, data)
            except Exception:
                logger.exception("notification_failed", event_id=event.id, topic=topic)


def _to_pending(row: OutboxEvent) -> PendingEvent:
    return PendingEvent(
        id=row.id,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        aggregate_version=row.aggregate_version,
        event_type=row.event_type,
        payload=row.payload,
    )
