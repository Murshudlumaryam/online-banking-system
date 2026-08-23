import uuid
from datetime import date

import pytest
from httpx import AsyncClient


def _valid_payload(email: str) -> dict:
    return {
        "email": email,
        "password": "StrongPass1",
        "first_name": "Aysel",
        "last_name": "Mammadova",
        "date_of_birth": str(date(1995, 5, 20)),
        "phone_number": "+994501234567",
        "national_id": f"TEST{uuid.uuid4().hex[:12].upper()}",
        "address": "Baku, Azerbaijan",
    }


@pytest.mark.asyncio
async def test_register_creates_user_and_customer(client: AsyncClient, unique_email: str):
    response = await client.post("/api/v1/auth/register", json=_valid_payload(unique_email))

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == unique_email.lower()
    assert body["customer"]["first_name"] == "Aysel"
    assert body["customer"]["customer_number"].startswith("CUS-")


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(client: AsyncClient, unique_email: str):
    payload = _valid_payload(unique_email)

    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409
    assert second.json()["error_code"] == "EMAIL_ALREADY_REGISTERED"


@pytest.mark.asyncio
async def test_register_rejects_future_date_of_birth(client: AsyncClient, unique_email: str):
    payload = _valid_payload(unique_email)
    payload["date_of_birth"] = "2999-01-01"

    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_rejects_weak_password(client: AsyncClient, unique_email: str):
    payload = _valid_payload(unique_email)
    payload["password"] = "weak"

    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
