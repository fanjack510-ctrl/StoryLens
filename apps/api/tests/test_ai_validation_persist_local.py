"""Service-level persistence tests for recommended setup + validation snapshot."""

from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import ApplicationSetting, Base, ProviderConfiguration
from app.model_gateway.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    ProviderHealth,
)
from app.model_gateway.gateway import ModelGateway
from app.services.ai_validation_snapshot import VALIDATION_SNAPSHOT_KEY, load_validation_snapshot
from app.services.credentials.fake_store import FakeCredentialStore
from app.services.recommended_ai_setup import (
    CANONICAL_PROVIDER_ID,
    configure_recommended_qwen,
    get_recommended_qwen_status,
)


class _Probe(ModelProvider):
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


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _ok_model(**_kwargs):
    return {"ok": True, "error_code": None, "model": "qwen3.7-plus"}


def test_refresh_reads_persisted_verified_state():
    session = _session()
    store = FakeCredentialStore()
    gateway = ModelGateway([_Probe()])
    store.set(CANONICAL_PROVIDER_ID, "sk-test-key-12345678")
    session.add(
        ProviderConfiguration(
            provider_name=CANONICAL_PROVIDER_ID,
            display_name="阿里云百炼",
            region="cn-beijing",
            workspace_id="",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            plus_model="qwen3.7-plus",
            max_model="qwen3.7-max",
            flash_model="qwen3.6-flash",
            timeout_seconds=300,
            max_retries=3,
            enabled=True,
            disconnected=False,
            allow_auto_route=False,
            credential_reference=f"keyring:{CANONICAL_PROVIDER_ID}",
        )
    )
    session.add(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True)))
    session.add(ApplicationSetting(key="cloud_body_consent", value_json=json.dumps(True)))
    session.commit()

    before = get_recommended_qwen_status(session, store, gateway)
    assert before.connection_ui_state == "CONFIGURED_NOT_VERIFIED"

    result = configure_recommended_qwen(
        session=session,
        store=store,
        gateway=gateway,
        api_key=None,
        analysis_mode="BALANCED",
        cloud_body_consent=True,
        persist=False,
        model_probe=_ok_model,
    )
    assert result.model_validated is True or result.connection_ui_state in {
        "VERIFIED",
        "READY",
        "CONSENT_REQUIRED",
    }
    snap = load_validation_snapshot(session)
    assert snap is not None
    assert snap["validation_status"] == "success"
    assert session.get(ApplicationSetting, VALIDATION_SNAPSHOT_KEY) is not None

    again = get_recommended_qwen_status(session, store, gateway)
    assert again.validated_at_display
    assert again.connection_ui_state in {"VERIFIED", "READY", "CONSENT_REQUIRED"}
    assert again.connection_ui_state != "CONFIGURED_NOT_VERIFIED"


def test_failed_probe_persists_failure_snapshot():
    session = _session()
    store = FakeCredentialStore()
    gateway = ModelGateway([_Probe()])
    store.set(CANONICAL_PROVIDER_ID, "sk-test-key-12345678")
    session.add(
        ProviderConfiguration(
            provider_name=CANONICAL_PROVIDER_ID,
            display_name="阿里云百炼",
            region="cn-beijing",
            workspace_id="",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            plus_model="qwen3.7-plus",
            max_model="qwen3.7-max",
            flash_model="qwen3.6-flash",
            timeout_seconds=300,
            max_retries=3,
            enabled=True,
            disconnected=False,
            allow_auto_route=False,
            credential_reference=f"keyring:{CANONICAL_PROVIDER_ID}",
        )
    )
    session.add(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True)))
    session.commit()

    def _fail(**_kwargs):
        return {"ok": False, "error_code": "CREDENTIAL_INVALID", "detail": "bad"}

    configure_recommended_qwen(
        session=session,
        store=store,
        gateway=gateway,
        api_key=None,
        analysis_mode="BALANCED",
        cloud_body_consent=True,
        persist=False,
        model_probe=_fail,
    )
    status = get_recommended_qwen_status(session, store, gateway)
    assert status.connection_ui_state == "VERIFICATION_FAILED"
    assert "API Key" in (status.connection_ui_label or "")
