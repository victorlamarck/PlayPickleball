import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


async def test_health_returns_ok() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_prod_rejects_default_secrets() -> None:
    with pytest.raises(ValueError, match="API_KEY"):
        Settings(env="prod", internal_token="real-token")
    with pytest.raises(ValueError, match="INTERNAL_TOKEN"):
        Settings(env="prod", api_key="real-key")


def test_prod_accepts_real_secrets() -> None:
    settings = Settings(env="prod", api_key="real-key", internal_token="real-token")
    assert settings.env == "prod"
