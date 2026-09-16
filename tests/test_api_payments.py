from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.main import app

VALID_BODY = {
    "amount": "10.00",
    "currency": "RUB",
    "description": "test",
    "webhook_url": "http://example.com/webhook",
}


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_create_payment_requires_api_key(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/payments", json=VALID_BODY, headers={"Idempotency-Key": "k1"}
    )
    assert response.status_code == 401


async def test_create_payment_requires_idempotency_key(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/payments", json=VALID_BODY, headers={"X-API-Key": "dev-api-key"}
    )
    assert response.status_code == 422


async def test_create_and_fetch_payment(client: AsyncClient) -> None:
    create_response = await client.post(
        "/api/v1/payments",
        json=VALID_BODY,
        headers={"X-API-Key": "dev-api-key", "Idempotency-Key": "k2"},
    )
    assert create_response.status_code == 202
    body = create_response.json()
    assert body["status"] == "pending"
    payment_id = body["payment_id"]

    get_response = await client.get(
        f"/api/v1/payments/{payment_id}", headers={"X-API-Key": "dev-api-key"}
    )
    assert get_response.status_code == 200
    detail = get_response.json()
    assert detail["payment_id"] == payment_id
    assert detail["amount"] == "10.00"


async def test_get_unknown_payment_returns_404(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/payments/00000000-0000-0000-0000-000000000000",
        headers={"X-API-Key": "dev-api-key"},
    )
    assert response.status_code == 404


async def test_rejects_non_positive_amount(client: AsyncClient) -> None:
    body = {**VALID_BODY, "amount": "0"}
    response = await client.post(
        "/api/v1/payments", json=body, headers={"X-API-Key": "dev-api-key", "Idempotency-Key": "k3"}
    )
    assert response.status_code == 422
