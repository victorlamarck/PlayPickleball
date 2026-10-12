"""Integration fixtures.

- Postgres: a dedicated database, migrated with Alembic, truncated before each test.
- Firestore: the compose emulator with a dedicated project id, cleared before each test.

Requires `make up`. Override with TEST_DATABASE_URL / FIRESTORE_EMULATOR_HOST.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from google.cloud.firestore import AsyncClient as FirestoreClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import Settings
from app.main import create_app
from app.readmodel.firestore_publisher import create_firestore_client

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://scores:scores@localhost:5432/scores_test"
)
FIRESTORE_EMULATOR_HOST = os.environ.get("FIRESTORE_EMULATOR_HOST", "localhost:8081")
FIRESTORE_PROJECT = "demo-live-scores-test"
API_KEY = "test-api-key"
INTERNAL_TOKEN = "test-internal-token"
ROOT = Path(__file__).resolve().parents[2]


async def _ensure_database(url: str) -> None:
    target = make_url(url)
    admin = create_async_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    await admin.dispose()


def _migrate(url: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        env="test",
        database_url=TEST_DATABASE_URL,
        gcp_project_id=FIRESTORE_PROJECT,
        firestore_emulator_host=FIRESTORE_EMULATOR_HOST,
        api_key=API_KEY,
        internal_token=INTERNAL_TOKEN,
        log_level="WARNING",
    )


@pytest.fixture(scope="session")
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    await _ensure_database(TEST_DATABASE_URL)
    # Alembic's async env calls asyncio.run(), so it must run outside the test event loop.
    await asyncio.to_thread(_migrate, TEST_DATABASE_URL)
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture(autouse=True)
async def clean_db(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE outbox_events, idempotency_keys, matches, teams, tournaments "
                "RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()


@pytest.fixture(autouse=True)
async def clean_firestore() -> None:
    async with httpx.AsyncClient() as http:
        response = await http.delete(
            f"http://{FIRESTORE_EMULATOR_HOST}/emulator/v1/projects/{FIRESTORE_PROJECT}"
            "/databases/(default)/documents"
        )
        response.raise_for_status()


@pytest.fixture(scope="session")
def firestore_client(settings: Settings) -> FirestoreClient:
    return create_firestore_client(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-API-Key": API_KEY}
    ) as http:
        yield http


@pytest.fixture
async def anon_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
async def session(app: FastAPI) -> AsyncIterator[AsyncSession]:
    async with app.state.session_factory() as db_session:
        yield db_session
