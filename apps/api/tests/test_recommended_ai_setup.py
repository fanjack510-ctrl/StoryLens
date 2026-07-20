"""Recommended Aliyun Bailian quick-setup (ordinary wizard + settings)."""

from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ApplicationSetting, Base, ProviderConfiguration
from app.db.session import get_db, get_session_factory
from app.main import app
from app.model_gateway.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    ProviderHealth,
)
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.registry import get_model_gateway
from app.services.credentials.fake_store import FakeCredentialStore
from app.services.credentials.service import get_credential_store
from app.services.recommended_ai_setup import (
    CANONICAL_PROVIDER_ID,
    configure_recommended_qwen,
    get_recommended_qwen_status,
    repair_recommended_qwen,
)


class AliyunProbeFake(ModelProvider):
    name = CANONICAL_PROVIDER_ID
    default_model = "qwen3.7-plus"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            enabled=True,
            cloud=True,
            provider_family="aliyun_qwen",
            sends_content_to_cloud=True,
            structured_output_mode="json_object",
            supports_json_object=True,
            supports_boundary_candidates=True,
            requires_boundary_review=True,
            automatic_boundary_routing=False,
            max_context_tokens=32768,
            default_timeout_seconds=30,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_name=self.name, status="healthy", detail="ok")

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            text='{"status":"ok"}',
            model=self.default_model,
            input_tokens=1,
            output_tokens=1,
            raw={"id": "fake"},
        )


def _ok_transport(**_kwargs) -> dict:
    return {"overall_status": "ok", "error_code": None}


def _fail_transport(**_kwargs) -> dict:
    return {"overall_status": "failed", "error_code": "PROVIDER_DNS_ERROR"}


@pytest.fixture
def setup_env(tmp_path, verified_cloud_pricing) -> Generator[tuple[TestClient, Session, FakeCredentialStore], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ai_setup.db'}", connect_args={"check_same_thread": False}
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    store = FakeCredentialStore()
    provider = AliyunProbeFake()

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway([provider])
    app.dependency_overrides[get_credential_store] = lambda: store
    with TestClient(app) as client, factory() as session:
        yield client, session, store
    app.dependency_overrides.clear()
    engine.dispose()


def test_configure_persists_credential_and_enables_cloud(setup_env, monkeypatch) -> None:
    client, session, store = setup_env
    monkeypatch.setattr(
        "app.services.recommended_ai_setup.run_transport_diagnostic",
        _ok_transport,
    )
    response = client.post(
        "/api/v1/desktop/ai-setup/recommended-qwen",
        json={
            "api_key": "sk-test-secret-value",
            "analysis_mode": "BALANCED",
            "cloud_body_consent": True,
            "persist": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["persisted"] is True
    assert body["credential_configured"] is True
    assert body["provider_enabled"] is True
    assert body["cloud_enabled"] is True
    assert body["provider_eligible"] is True
    assert body["selected_provider_id"] == CANONICAL_PROVIDER_ID
    assert "sk-test-secret-value" not in response.text
    assert store.get(CANONICAL_PROVIDER_ID) == "sk-test-secret-value"

    session.expire_all()
    row = session.scalar(
        select(ProviderConfiguration).where(
            ProviderConfiguration.provider_name == CANONICAL_PROVIDER_ID
        )
    )
    assert row is not None
    assert row.enabled is True
    assert row.disconnected is False
    assert row.base_url
    assert row.plus_model == "qwen3.7-plus"
    cloud = session.get(ApplicationSetting, "cloud_enabled")
    assert cloud is not None and json.loads(cloud.value_json) is True


def test_test_only_does_not_claim_saved_or_enable_cloud(setup_env, monkeypatch) -> None:
    client, session, store = setup_env
    monkeypatch.setattr(
        "app.services.recommended_ai_setup.run_transport_diagnostic",
        _ok_transport,
    )
    response = client.post(
        "/api/v1/desktop/ai-setup/recommended-qwen",
        json={
            "api_key": "sk-test-only-keyxx",
            "analysis_mode": "FAST",
            "cloud_body_consent": False,
            "persist": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["persisted"] is False
    assert "尚未保存" in body["user_message"]
    assert store.get(CANONICAL_PROVIDER_ID) is None
    cloud = session.get(ApplicationSetting, "cloud_enabled")
    assert cloud is None or json.loads(cloud.value_json) is False


def test_failed_test_does_not_overwrite_existing_key(setup_env, monkeypatch) -> None:
    _client, session, store = setup_env
    store.set(CANONICAL_PROVIDER_ID, "sk-original-valid-key")
    monkeypatch.setattr(
        "app.services.recommended_ai_setup.run_transport_diagnostic",
        _fail_transport,
    )
    result = configure_recommended_qwen(
        session=session,
        store=store,
        gateway=ModelGateway([AliyunProbeFake()]),
        api_key="sk-bad-replacement",
        analysis_mode="BALANCED",
        cloud_body_consent=True,
        persist=True,
        transport_probe=_fail_transport,
    )
    assert result.ok is False
    assert store.get(CANONICAL_PROVIDER_ID) == "sk-original-valid-key"


def test_without_consent_does_not_enable_cloud(setup_env, monkeypatch) -> None:
    client, _session, store = setup_env
    monkeypatch.setattr(
        "app.services.recommended_ai_setup.run_transport_diagnostic",
        _ok_transport,
    )
    response = client.post(
        "/api/v1/desktop/ai-setup/recommended-qwen",
        json={
            "api_key": "sk-test-secret-value",
            "analysis_mode": "QUALITY",
            "cloud_body_consent": False,
            "persist": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["cloud_enabled"] is False
    assert store.get(CANONICAL_PROVIDER_ID) is None


def test_does_not_create_duplicate_providers(setup_env, monkeypatch) -> None:
    client, session, _store = setup_env
    monkeypatch.setattr(
        "app.services.recommended_ai_setup.run_transport_diagnostic",
        _ok_transport,
    )
    payload = {
        "api_key": "sk-test-secret-value",
        "analysis_mode": "BALANCED",
        "cloud_body_consent": True,
        "persist": True,
    }
    assert client.post("/api/v1/desktop/ai-setup/recommended-qwen", json=payload).json()["ok"]
    assert client.post("/api/v1/desktop/ai-setup/recommended-qwen", json=payload).json()["ok"]
    session.expire_all()
    rows = list(
        session.scalars(
            select(ProviderConfiguration).where(
                ProviderConfiguration.provider_name == CANONICAL_PROVIDER_ID
            )
        )
    )
    assert len(rows) == 1


def test_status_survives_reload(setup_env, monkeypatch) -> None:
    client, session, store = setup_env
    monkeypatch.setattr(
        "app.services.recommended_ai_setup.run_transport_diagnostic",
        _ok_transport,
    )
    assert client.post(
        "/api/v1/desktop/ai-setup/recommended-qwen",
        json={
            "api_key": "sk-test-secret-value",
            "analysis_mode": "FAST",
            "cloud_body_consent": True,
            "persist": True,
        },
    ).json()["ok"]
    status = get_recommended_qwen_status(session, store, ModelGateway([AliyunProbeFake()]))
    assert status.provider_eligible is True
    assert status.analysis_mode == "FAST"
    again = client.get("/api/v1/desktop/ai-setup/recommended-qwen").json()
    assert again["credential_configured"] is True
    assert again["provider_eligible"] is True


def test_repair_requires_consent_before_enabling_cloud(setup_env) -> None:
    _client, session, store = setup_env
    store.set(CANONICAL_PROVIDER_ID, "sk-existing-keyxx")
    from app.services.recommended_ai_setup import _ensure_canonical_provider

    row = _ensure_canonical_provider(session)
    row.enabled = True
    row.disconnected = False
    row.credential_reference = f"keyring:{CANONICAL_PROVIDER_ID}"
    session.commit()

    denied = repair_recommended_qwen(
        session=session,
        store=store,
        gateway=ModelGateway([AliyunProbeFake()]),
        cloud_body_consent=False,
    )
    assert denied.needs_cloud_consent is True
    assert denied.cloud_enabled is False

    fixed = repair_recommended_qwen(
        session=session,
        store=store,
        gateway=ModelGateway([AliyunProbeFake()]),
        cloud_body_consent=True,
    )
    assert fixed.cloud_enabled is True
    assert fixed.provider_enabled is True


def test_empty_base_url_put_no_longer_blocks_ordinary_save(setup_env) -> None:
    client, session, store = setup_env
    app.dependency_overrides[get_credential_store] = lambda: store
    response = client.put(
        f"/api/v1/model-providers/{CANONICAL_PROVIDER_ID}/configuration",
        json={
            "display_name": "阿里云百炼",
            "region": "cn-beijing",
            "workspace_id": "",
            "base_url": "",
            "plus_model": "qwen3.7-plus",
            "max_model": "qwen3.7-max",
            "flash_model": "qwen3.6-flash",
            "timeout_seconds": 300,
            "max_retries": 3,
            "enabled": True,
            "disconnected": False,
            "allow_auto_route": False,
            "raw_logging_enabled": False,
            "api_key": "sk-test-secret-value",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["credential_state"] == "configured"
    session.expire_all()
    row = session.scalar(
        select(ProviderConfiguration).where(
            ProviderConfiguration.provider_name == CANONICAL_PROVIDER_ID
        )
    )
    assert row is not None
    assert row.base_url


def test_production_credential_store_is_keyring() -> None:
    from app.services.credentials.keyring_store import KeyringCredentialStore
    from app.services.credentials.service import get_credential_store

    get_credential_store.cache_clear()
    store = get_credential_store()
    assert isinstance(store, KeyringCredentialStore)
    assert "FakeCredentialStore" not in type(store).__name__
    get_credential_store.cache_clear()


def test_api_key_not_in_sqlite_after_setup(setup_env, monkeypatch) -> None:
    client, session, _store = setup_env
    monkeypatch.setattr(
        "app.services.recommended_ai_setup.run_transport_diagnostic",
        _ok_transport,
    )
    secret = "sk-must-not-appear-in-db"
    assert client.post(
        "/api/v1/desktop/ai-setup/recommended-qwen",
        json={
            "api_key": secret,
            "analysis_mode": "BALANCED",
            "cloud_body_consent": True,
            "persist": True,
        },
    ).json()["ok"]
    for row in session.scalars(select(ApplicationSetting)):
        assert secret not in row.value_json
    for row in session.scalars(select(ProviderConfiguration)):
        blob = " ".join(
            str(getattr(row, field))
            for field in (
                "display_name",
                "workspace_id",
                "base_url",
                "plus_model",
                "credential_reference",
            )
        )
        assert secret not in blob
