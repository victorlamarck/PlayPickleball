"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.config import Settings, get_settings
from app.db import create_engine, create_session_factory
from app.errors import install_error_handlers
from app.logging import configure_logging
from app.outbox.relay import OutboxRelay
from app.readmodel.firestore_publisher import (
    FirestorePublisher,
    Publisher,
    create_firestore_client,
)
from app.readmodel.notifier import Notifier, create_notifier
from app.routers import health, internal, matches, tournaments


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    app.state.session_factory = session_factory

    firestore_publisher: FirestorePublisher | None = None
    publisher: Publisher | None = app.state.publisher_override
    if publisher is None:
        firestore_publisher = FirestorePublisher(create_firestore_client(settings))
        publisher = firestore_publisher
    notifier: Notifier = app.state.notifier_override or create_notifier(settings)
    app.state.relay = OutboxRelay(session_factory, publisher, notifier)

    structlog.get_logger().info("startup", env=settings.env)
    try:
        yield
    finally:
        if firestore_publisher is not None:
            firestore_publisher.close()
        await engine.dispose()


def create_app(
    settings: Settings | None = None,
    *,
    publisher: Publisher | None = None,
    notifier: Notifier | None = None,
) -> FastAPI:
    """Build the app. `publisher`/`notifier` overrides exist for tests."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.env == "prod")

    app = FastAPI(
        title="Pickleball Live Scores API",
        version="0.1.0",
        description=(
            "Write API for live pickleball scores. Postgres is the source of truth; "
            "match state is mirrored to Firestore for real-time clients.\n\n"
            "Write endpoints require the `X-API-Key` header. POST endpoints accept an optional "
            "`Idempotency-Key` header. Errors use the shape "
            '`{"error": {"code", "message", "details"}}`.'
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.publisher_override = publisher
    app.state.notifier_override = notifier
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(tournaments.router)
    app.include_router(matches.router)
    app.include_router(internal.router)
    return app


app = create_app()
