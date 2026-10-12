import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/v1/tournaments"),
        ("POST", "/v1/matches/{id}/start"),
        ("POST", "/v1/matches/{id}/points"),
        ("PUT", "/v1/matches/{id}/games/0"),
    ],
)
async def test_writes_without_api_key_return_401(
    anon_client: AsyncClient, method: str, path: str
) -> None:
    response = await anon_client.request(method, path.format(id=uuid.uuid4()), json={})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_wrong_api_key_returns_401(anon_client: AsyncClient) -> None:
    response = await anon_client.post("/v1/tournaments", json={}, headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


async def test_reads_do_not_require_api_key(anon_client: AsyncClient, client: AsyncClient) -> None:
    created = await client.post(
        "/v1/tournaments", json={"name": "Open", "teams": [{"name": f"T{i}"} for i in range(4)]}
    )
    response = await anon_client.get(f"/v1/tournaments/{created.json()['id']}/bracket")
    assert response.status_code == 200


async def test_readiness_checks_database(anon_client: AsyncClient) -> None:
    response = await anon_client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
