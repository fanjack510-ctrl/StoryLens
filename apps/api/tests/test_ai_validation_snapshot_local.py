"""Local tests for AI validation snapshot + connection UI state machine."""

from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ApplicationSetting, Base, ProviderConfiguration
from app.services.ai_validation_snapshot import (
    VALIDATION_SNAPSHOT_KEY,
    build_current_fingerprints,
    configuration_fingerprint,
    derive_connection_ui_state,
    load_validation_snapshot,
    record_validation_outcome,
)
from app.services.credentials.fake_store import FakeCredentialStore


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_provider(session: Session, *, model: str = "qwen3.7-plus", enabled: bool = True) -> None:
    session.add(
        ProviderConfiguration(
            provider_name="aliyun_qwen_plus",
            display_name="阿里云百炼",
            region="cn-beijing",
            workspace_id="ws-1",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            plus_model=model,
            max_model="qwen3.7-max",
            flash_model="qwen3.6-flash",
            timeout_seconds=300,
            max_retries=3,
            enabled=enabled,
            disconnected=not enabled,
            allow_auto_route=False,
            credential_reference="keyring:aliyun_qwen_plus",
        )
    )
    session.add(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True)))
    session.commit()


def test_not_configured_without_credential():
    session = _session()
    store = FakeCredentialStore()
    _seed_provider(session)
    current = build_current_fingerprints(session, store, provider_id="aliyun_qwen_plus")
    state, label, _ = derive_connection_ui_state(
        credential_configured=False,
        provider_enabled=True,
        cloud_enabled=True,
        cloud_body_consent=False,
        provider_eligible=False,
        snapshot=None,
        current=current,
    )
    assert state == "NOT_CONFIGURED"
    assert label == "尚未配置"


def test_configured_without_snapshot():
    session = _session()
    store = FakeCredentialStore()
    store.set("aliyun_qwen_plus", "sk-test-key-12345678")
    _seed_provider(session)
    current = build_current_fingerprints(session, store, provider_id="aliyun_qwen_plus")
    state, label, _ = derive_connection_ui_state(
        credential_configured=True,
        provider_enabled=True,
        cloud_enabled=True,
        cloud_body_consent=True,
        provider_eligible=True,
        snapshot=None,
        current=current,
    )
    assert state == "CONFIGURED_NOT_VERIFIED"
    assert "尚未验证" in label


def test_success_snapshot_persists_and_reloads_verified():
    session = _session()
    store = FakeCredentialStore()
    store.set("aliyun_qwen_plus", "sk-test-key-12345678")
    _seed_provider(session)
    snap = record_validation_outcome(
        session,
        store,
        provider_id="aliyun_qwen_plus",
        ok=True,
        model_name="qwen3.7-plus",
        application_version="1.0.3",
    )
    loaded = load_validation_snapshot(session)
    assert loaded is not None
    assert loaded["validation_status"] == "success"
    assert loaded["validated_at"]
    assert "api_key" not in loaded
    assert snap["configuration_fingerprint"]
    current = build_current_fingerprints(session, store, provider_id="aliyun_qwen_plus")
    state, _, reason = derive_connection_ui_state(
        credential_configured=True,
        provider_enabled=True,
        cloud_enabled=True,
        cloud_body_consent=True,
        provider_eligible=True,
        snapshot=loaded,
        current=current,
    )
    assert state == "READY"
    assert "最近验证" in reason


def test_model_change_marks_config_changed():
    session = _session()
    store = FakeCredentialStore()
    store.set("aliyun_qwen_plus", "sk-test-key-12345678")
    _seed_provider(session, model="qwen3.7-plus")
    record_validation_outcome(session, store, provider_id="aliyun_qwen_plus", ok=True)
    row = session.query(ProviderConfiguration).one()
    row.plus_model = "qwen3.7-max"
    session.commit()
    current = build_current_fingerprints(session, store, provider_id="aliyun_qwen_plus")
    state, label, _ = derive_connection_ui_state(
        credential_configured=True,
        provider_enabled=True,
        cloud_enabled=True,
        cloud_body_consent=True,
        provider_eligible=True,
        snapshot=load_validation_snapshot(session),
        current=current,
    )
    assert state == "CONFIG_CHANGED"
    assert "重新验证" in label


def test_endpoint_change_marks_config_changed():
    session = _session()
    store = FakeCredentialStore()
    store.set("aliyun_qwen_plus", "sk-test-key-12345678")
    _seed_provider(session)
    record_validation_outcome(session, store, provider_id="aliyun_qwen_plus", ok=True)
    row = session.query(ProviderConfiguration).one()
    row.base_url = "https://example.invalid/v1"
    session.commit()
    current = build_current_fingerprints(session, store, provider_id="aliyun_qwen_plus")
    state, _, _ = derive_connection_ui_state(
        credential_configured=True,
        provider_enabled=True,
        cloud_enabled=True,
        cloud_body_consent=True,
        provider_eligible=True,
        snapshot=load_validation_snapshot(session),
        current=current,
    )
    assert state == "CONFIG_CHANGED"


def test_credential_change_marks_config_changed():
    session = _session()
    store = FakeCredentialStore()
    store.set("aliyun_qwen_plus", "sk-old-key-aaaaaaaa")
    _seed_provider(session)
    record_validation_outcome(session, store, provider_id="aliyun_qwen_plus", ok=True)
    store.set("aliyun_qwen_plus", "sk-new-key-bbbbbbbb")
    current = build_current_fingerprints(session, store, provider_id="aliyun_qwen_plus")
    state, _, _ = derive_connection_ui_state(
        credential_configured=True,
        provider_enabled=True,
        cloud_enabled=True,
        cloud_body_consent=True,
        provider_eligible=True,
        snapshot=load_validation_snapshot(session),
        current=current,
    )
    assert state == "CONFIG_CHANGED"


def test_failed_snapshot():
    session = _session()
    store = FakeCredentialStore()
    store.set("aliyun_qwen_plus", "sk-test-key-12345678")
    _seed_provider(session)
    record_validation_outcome(
        session,
        store,
        provider_id="aliyun_qwen_plus",
        ok=False,
        failure_category="CREDENTIAL_INVALID",
        failure_message="bad key",
    )
    current = build_current_fingerprints(session, store, provider_id="aliyun_qwen_plus")
    state, label, reason = derive_connection_ui_state(
        credential_configured=True,
        provider_enabled=True,
        cloud_enabled=True,
        cloud_body_consent=True,
        provider_eligible=False,
        snapshot=load_validation_snapshot(session),
        current=current,
    )
    assert state == "VERIFICATION_FAILED"
    assert "API Key" in label
    assert "失败" in reason


def test_cloud_off_not_verified():
    session = _session()
    store = FakeCredentialStore()
    store.set("aliyun_qwen_plus", "sk-test-key-12345678")
    _seed_provider(session)
    record_validation_outcome(session, store, provider_id="aliyun_qwen_plus", ok=True)
    session.merge(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(False)))
    session.commit()
    current = build_current_fingerprints(session, store, provider_id="aliyun_qwen_plus")
    state, _, _ = derive_connection_ui_state(
        credential_configured=True,
        provider_enabled=True,
        cloud_enabled=False,
        cloud_body_consent=True,
        provider_eligible=False,
        snapshot=load_validation_snapshot(session),
        current=current,
    )
    assert state == "CONFIG_CHANGED"


def test_provider_off_not_verified():
    session = _session()
    store = FakeCredentialStore()
    store.set("aliyun_qwen_plus", "sk-test-key-12345678")
    _seed_provider(session, enabled=True)
    record_validation_outcome(session, store, provider_id="aliyun_qwen_plus", ok=True)
    row = session.query(ProviderConfiguration).one()
    row.enabled = False
    session.commit()
    current = build_current_fingerprints(session, store, provider_id="aliyun_qwen_plus")
    state, _, _ = derive_connection_ui_state(
        credential_configured=True,
        provider_enabled=False,
        cloud_enabled=True,
        cloud_body_consent=True,
        provider_eligible=False,
        snapshot=load_validation_snapshot(session),
        current=current,
    )
    assert state == "CONFIG_CHANGED"


def test_consent_required_then_ready():
    session = _session()
    store = FakeCredentialStore()
    store.set("aliyun_qwen_plus", "sk-test-key-12345678")
    _seed_provider(session)
    record_validation_outcome(session, store, provider_id="aliyun_qwen_plus", ok=True)
    current = build_current_fingerprints(session, store, provider_id="aliyun_qwen_plus")
    snap = load_validation_snapshot(session)
    state1, label1, _ = derive_connection_ui_state(
        credential_configured=True,
        provider_enabled=True,
        cloud_enabled=True,
        cloud_body_consent=False,
        provider_eligible=True,
        snapshot=snap,
        current=current,
    )
    assert state1 == "CONSENT_REQUIRED"
    assert "正文发送" in label1
    state2, label2, _ = derive_connection_ui_state(
        credential_configured=True,
        provider_enabled=True,
        cloud_enabled=True,
        cloud_body_consent=True,
        provider_eligible=True,
        snapshot=snap,
        current=current,
    )
    assert state2 == "READY"
    assert "开始分析" in label2


def test_snapshot_excludes_secrets():
    session = _session()
    store = FakeCredentialStore()
    store.set("aliyun_qwen_plus", "sk-secret-should-not-persist")
    _seed_provider(session)
    record_validation_outcome(session, store, provider_id="aliyun_qwen_plus", ok=True)
    raw = session.get(ApplicationSetting, VALIDATION_SNAPSHOT_KEY)
    assert raw is not None
    assert "sk-secret" not in raw.value_json
    assert "Authorization" not in raw.value_json


def test_fingerprint_stable_for_same_config():
    a = configuration_fingerprint(
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        endpoint_host_value="dashscope.aliyuncs.com",
        workspace_id="ws",
        allow_auto_route=False,
        provider_enabled=True,
        cloud_enabled=True,
    )
    b = configuration_fingerprint(
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        endpoint_host_value="dashscope.aliyuncs.com",
        workspace_id="ws",
        allow_auto_route=False,
        provider_enabled=True,
        cloud_enabled=True,
    )
    assert a == b
