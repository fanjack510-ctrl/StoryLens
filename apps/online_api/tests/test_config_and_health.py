from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from storylens_online.config import OnlineSettings
from storylens_online.main import create_app


def make_settings(**overrides) -> OnlineSettings:
    values = {
        "database_url": "postgresql+psycopg://storylens@postgres:5432/storylens_online",
        "frontend_origin": "https://storylens.example.com",
        "afdian_user_id": "publisher-id",
        "afdian_api_token": SecretStr("not-a-real-token"),
    }
    values.update(overrides)
    return OnlineSettings(**values)


def test_online_runtime_rejects_desktop_sqlite() -> None:
    with pytest.raises(ValidationError, match="requires PostgreSQL"):
        make_settings(database_url="sqlite:///./data/storylens.db")


def test_public_snapshot_never_contains_afdian_secret() -> None:
    snapshot = make_settings().public_snapshot().model_dump(mode="json")
    assert snapshot["afdian_configured"] is True
    assert "token" not in snapshot
    assert "not-a-real-token" not in str(snapshot)
    assert snapshot["billing_multiplier"] == "2.0"


def test_health_contract_is_validated_and_desktop_version_is_independent() -> None:
    client = TestClient(create_app(make_settings(billing_multiplier=Decimal("2.0"))))
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["service"] == "storylens-online-api"
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["configuration"]["database_backend"] == "postgresql"
