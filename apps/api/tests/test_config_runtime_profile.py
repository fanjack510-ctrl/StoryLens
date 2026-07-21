"""Config runtime profile: which SQLite / credential environment is active."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core import paths
from app.db.models import Base
from app.db.session import get_db, get_session_factory
from app.main import app
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.registry import get_model_gateway
from app.services.config_runtime_profile import (
    build_config_runtime_profile,
    resolve_runtime_mode,
)
from app.services.credentials.fake_store import FakeCredentialStore
from app.services.credentials.keyring_store import KeyringCredentialStore
from app.services.credentials.service import get_credential_store


def test_browser_dev_profile_isolates_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("STORYLENS_DATA_DIR", raising=False)
    monkeypatch.delenv("STORYLENS_APP_ENV", raising=False)
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    monkeypatch.setattr(paths, "resource_root", lambda: tmp_path)
    paths.user_data_root.cache_clear()

    profile = build_config_runtime_profile(FakeCredentialStore())
    assert profile["runtime_mode"] == "browser_dev"
    assert profile["app_env"] == "development"
    assert profile["isolates_sqlite_from_packaged"] is True
    assert Path(profile["data_directory"]) == (tmp_path / "data").resolve()
    assert profile["credential_store"]["returns_secret_to_api"] is False
    assert profile["credential_store"]["desktop_parity"] is False
    assert "浏览器开发模式" in profile["user_message"]


def test_packaged_profile_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("STORYLENS_APP_ENV", "production")
    monkeypatch.delenv("STORYLENS_DATA_DIR", raising=False)
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    paths.user_data_root.cache_clear()

    profile = build_config_runtime_profile(KeyringCredentialStore())
    assert resolve_runtime_mode() == "packaged"
    assert profile["runtime_mode"] == "packaged"
    assert profile["isolates_sqlite_from_packaged"] is False
    assert Path(profile["data_directory"]) == tmp_path / "StoryLens"
    assert profile["credential_store"]["machine_scoped"] is True
    assert profile["credential_store"]["returns_secret_to_api"] is False


@pytest.fixture
def profile_client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'profile.db'}", connect_args={"check_same_thread": False}
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    store = FakeCredentialStore()

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway([])
    app.dependency_overrides[get_credential_store] = lambda: store
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()


def test_config_profile_endpoint_omits_secrets(profile_client):
    response = profile_client.get("/api/v1/settings/config-profile")
    assert response.status_code == 200
    body = response.json()
    assert body["runtime_mode"] in {"browser_dev", "desktop_dev", "packaged"}
    assert "data_directory" in body
    assert body["credential_store"]["returns_secret_to_api"] is False
    assert "sk-" not in response.text.lower()
    assert '"api_key"' not in response.text.lower()
