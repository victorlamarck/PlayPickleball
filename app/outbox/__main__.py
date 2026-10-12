"""Dev relay loop: `python -m app.outbox` drains the outbox every 500 ms until Ctrl+C."""

import asyncio
import contextlib

import structlog

from app.config import get_settings
from app.db import create_engine, create_session_factory
from app.logging import configure_logging
from app.outbox.relay import OutboxRelay
from app.readmodel.firestore_publisher import FirestorePublisher, create_firestore_client
from app.readmodel.notifier import create_notifier

POLL_INTERVAL_SECONDS = 0.5


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.env == "prod")
    logger = structlog.get_logger()

    engine = create_engine(settings.database_url)
    publisher = FirestorePublisher(create_firestore_client(settings))
    relay = OutboxRelay(create_session_factory(engine), publisher, create_notifier(settings))
    logger.info("relay_started", interval_seconds=POLL_INTERVAL_SECONDS)
    try:
        while True:
            try:
                await relay.drain()
            except Exception:
                logger.exception("outbox_drain_failed")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        publisher.close()
        await engine.dispose()
        logger.info("relay_stopped")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())
