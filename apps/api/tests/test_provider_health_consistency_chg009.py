"""CHG-20260729-009: settings validation must keep analysis preflight fresh."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AnalysisRun,
    ApplicationSetting,
    Base,
    ModelInvocation,
    ProviderConfiguration,
)
from app.model_gateway.base import ProviderCapabilities
from app.services.ai_validation_snapshot import record_validation_outcome
from app.services.provider_eligibility import (
    HEALTH_TTL_SECONDS,
    apply_validation_snapshot_health,
    evaluate_manual_boundary_candidate,
    parse_health_timestamp,
)
from tests.optional_gates import CLOUD_PRICING_PATH, install_verified_cloud_pricing, restore_cloud_pricing


class Store:
    def __init__(self, secret: str | None = "sk-test"):
        self.secret = secret

    def available(self):
        return True

    def get(self, _name):
        return self.secret

    def set(self, *_a, **_k):
        pass

    def delete(self, *_a, **_k):
        pass


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chg009.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        yield s
    engine.dispose()


@pytest.fixture
def pricing(tmp_path):
    path, previous = install_verified_cloud_pricing(CLOUD_PRICING_PATH)
    try:
        yield path
    finally:
        restore_cloud_pricing(path, previous)


def _caps(**extra) -> ProviderCapabilities:
    base = dict(
        max_context_tokens=32000,
        default_timeout_seconds=10,
        enabled=True,
        cloud=True,
        supports_json_object=True,
        supports_structured_output=True,
        supports_scene_analysis=True,
        supports_boundary_candidates=True,
        automatic_boundary_routing=False,
        requires_boundary_review=True,
        manual_only=False,
    )
    base.update(extra)
    return ProviderCapabilities(**base)


def _configure_plus(session) -> None:
    session.add(
        ProviderConfiguration(
            provider_name="aliyun_qwen_plus",
            display_name="阿里云百炼",
            region="cn-beijing",
            workspace_id="",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            plus_model="qwen3.7-plus",
            max_model="qwen3.7-max",
            flash_model="qwen3.6-flash",
            timeout_seconds=60,
            max_retries=1,
            enabled=True,
            disconnected=False,
            allow_auto_route=False,
            credential_reference="keyring:aliyun_qwen_plus",
        )
    )
    session.add(ApplicationSetting(key="cloud_enabled", value_json="true"))
    session.add(
        ApplicationSetting(
            key="cloud_budget_settings",
            value_json=json.dumps(
                {
                    "cloud_request_budget_enabled": True,
                    "cloud_daily_request_limit": 500,
                    "cloud_daily_token_limit": 500000,
                    "cloud_daily_estimated_cost_limit": 50,
                }
            ),
        )
    )
    session.commit()


def _add_old_success(session, *, hours_ago: float = 30) -> None:
    created = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id="1",
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="v1",
        schema_version="v1",
        input_hash="a" * 64,
        status="succeeded",
        execution_mode="cloud",
        cloud_consent=True,
        sends_content_to_cloud=True,
    )
    session.add(run)
    session.flush()
    inv = ModelInvocation(
        run_id=run.id,
        task_type="scene_boundary",
        provider_name="aliyun_qwen_plus",
        model_name="qwen3.7-plus",
        prompt_version="v1",
        schema_version="v1",
        attempt_no=1,
        invocation_kind="boundary_candidate_detection",
        request_hash="b" * 64,
        input_snapshot_json="{}",
        raw_response_text="",
        parsed_response_json="{}",
        status="succeeded",
        latency_ms=1,
        http_request_sent=True,
        http_status_code=200,
    )
    inv.created_at = created.replace(tzinfo=None)
    session.add(inv)
    session.commit()


def test_one_minute_after_settings_verify_is_fresh(session, pricing):
    _configure_plus(session)
    _add_old_success(session, hours_ago=30)
    store = Store()
    before = evaluate_manual_boundary_candidate(
        session,
        provider_name="aliyun_qwen_plus",
        capabilities=_caps(),
        store=store,
        pricing_path=Path(pricing),
    )
    assert before["health_state"] == "stale"

    record_validation_outcome(
        session,
        store,
        provider_id="aliyun_qwen_plus",
        ok=True,
        model_name="qwen3.7-plus",
    )
    after = evaluate_manual_boundary_candidate(
        session,
        provider_name="aliyun_qwen_plus",
        capabilities=_caps(),
        store=store,
        pricing_path=Path(pricing),
    )
    assert after["health_state"] == "healthy"
    assert after["health_source"] == "validation_snapshot"
    assert "provider_health_stale" not in after["manual_selection_blockers"]
    assert after["manual_boundary_candidate_eligible"] is True
    assert after.get("freshness_age_seconds") is not None
    assert after["freshness_age_seconds"] < 60


def test_utc_plus8_one_minute_still_fresh(session, pricing):
    _configure_plus(session)
    store = Store()
    from app.services import ai_validation_snapshot as snap_mod

    verified = datetime(2026, 7, 29, 11, 28, 0, tzinfo=timezone.utc)
    snap = record_validation_outcome(
        session, store, provider_id="aliyun_qwen_plus", ok=True, model_name="qwen3.7-plus"
    )
    snap["validated_at"] = verified.isoformat()
    snap_mod.save_validation_snapshot(session, snap)
    state, source, _checked, code, age = apply_validation_snapshot_health(
        session,
        provider_name="aliyun_qwen_plus",
        store=store,
        runtime_state="stale",
        health_source="cached_success",
        health_checked_at=verified - timedelta(days=2),
        now=datetime(2026, 7, 29, 11, 29, 0, tzinfo=timezone.utc),
    )
    assert state == "healthy"
    assert source == "validation_snapshot"
    assert code is None
    assert age == 60.0


@pytest.mark.parametrize(
    "offset,expected",
    [
        (timedelta(seconds=HEALTH_TTL_SECONDS - 1), "healthy"),
        (timedelta(seconds=HEALTH_TTL_SECONDS), "healthy"),
        (timedelta(seconds=HEALTH_TTL_SECONDS + 1), "stale"),
    ],
)
def test_ttl_boundaries(session, pricing, offset, expected):
    _configure_plus(session)
    store = Store()
    from app.services import ai_validation_snapshot as snap_mod

    now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
    verified = now - offset
    snap = record_validation_outcome(
        session, store, provider_id="aliyun_qwen_plus", ok=True, model_name="qwen3.7-plus"
    )
    snap["validated_at"] = verified.isoformat()
    snap_mod.save_validation_snapshot(session, snap)
    state, *_rest = apply_validation_snapshot_health(
        session,
        provider_name="aliyun_qwen_plus",
        store=store,
        runtime_state="stale",
        health_source="cached_success",
        health_checked_at=verified - timedelta(days=3),
        now=now,
    )
    assert state == expected


def test_model_mismatch_does_not_reuse(session, pricing):
    _configure_plus(session)
    store = Store()
    record_validation_outcome(
        session, store, provider_id="aliyun_qwen_plus", ok=True, model_name="qwen3.7-plus"
    )
    row = session.query(ProviderConfiguration).one()
    row.plus_model = "qwen-plus"
    session.commit()
    state, _source, _checked, code, _age = apply_validation_snapshot_health(
        session,
        provider_name="aliyun_qwen_plus",
        store=store,
        runtime_state="stale",
        health_source="cached_success",
        health_checked_at=datetime.now(timezone.utc),
        now=datetime.now(timezone.utc),
    )
    assert state == "stale"
    assert code == "PROVIDER_MODEL_NOT_VERIFIED"


def test_credential_change_invalidates(session, pricing):
    _configure_plus(session)
    store = Store("sk-original")
    record_validation_outcome(
        session, store, provider_id="aliyun_qwen_plus", ok=True, model_name="qwen3.7-plus"
    )
    store.secret = "sk-rotated"
    _st, _src, _ch, code, _age = apply_validation_snapshot_health(
        session,
        provider_name="aliyun_qwen_plus",
        store=store,
        runtime_state="healthy",
        health_source="configured_readiness",
        health_checked_at=datetime.now(timezone.utc),
        now=datetime.now(timezone.utc),
    )
    assert code == "PROVIDER_CREDENTIAL_CHANGED"


def test_parse_health_timestamp_naive_as_utc():
    dt = parse_health_timestamp("2026-07-29 11:28:00.000000")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(0)


def test_incident_db_replay_becomes_fresh(tmp_path: Path):
    import shutil

    src = Path(
        r"D:\StoryLensIncident\INC-20260729-004-provider-health-stale\database\storylens-consistent.db"
    )
    if not src.exists():
        pytest.skip("incident DB not available")
    dest = tmp_path / "incident-replay.db"
    shutil.copy2(src, dest)

    engine = create_engine(f"sqlite:///{dest}")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = SessionLocal()
    row = s.get(ApplicationSetting, "ai_service_validation_snapshot")
    assert row is not None
    snap = json.loads(row.value_json)
    assert snap["validation_status"] == "success"
    target_fp = snap["credential_version_fingerprint"]
    # Incident DB timestamps are historical; refresh checked_at into the active TTL
    # window so this case validates fingerprint continuity, not wall-clock archaeology.
    fresh_at = datetime.now(timezone.utc).isoformat()
    for key in ("validated_at", "health_checked_at", "checked_at"):
        if key in snap:
            snap[key] = fresh_at
    row.value_json = json.dumps(snap, ensure_ascii=False)
    s.commit()

    path, previous = install_verified_cloud_pricing(CLOUD_PRICING_PATH)
    import app.services.ai_validation_snapshot as snap_mod

    original = snap_mod.credential_version_fingerprint

    def _fake_cred(_store, _provider_id: str) -> str | None:
        return target_fp

    snap_mod.credential_version_fingerprint = _fake_cred  # type: ignore[assignment]
    try:
        result = evaluate_manual_boundary_candidate(
            s,
            provider_name="aliyun_qwen_plus",
            capabilities=_caps(),
            store=Store("sk-placeholder"),
            pricing_path=Path(path),
        )
    finally:
        snap_mod.credential_version_fingerprint = original  # type: ignore[assignment]
        restore_cloud_pricing(path, previous)
        s.close()
        engine.dispose()

    assert result["health_state"] == "healthy"
    assert result["health_source"] == "validation_snapshot"
    assert "provider_health_stale" not in result["manual_selection_blockers"]
    assert result["manual_boundary_candidate_eligible"] is True
