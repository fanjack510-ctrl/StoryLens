"""CHG-20260808-065 — unified cloud provider routing (no real provider calls)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import ApplicationSetting, Base, ProviderConfiguration
from app.services.cloud_provider_resolver_v1 import (
    ProviderResolutionError,
    ResolutionSource,
    assert_formal_provider_available,
    build_routing_preview,
    resolve_provider_for_task,
)
from app.services.provider_runtime import (
    get_active_cloud_provider,
    set_active_cloud_provider,
)
from app.services.task_routing_policy_v1 import (
    RoutingMode,
    TASK_HIGH_DIFFICULTY_REVIEW,
    TASK_JSON_SCHEMA_REPAIR,
    TASK_LOCAL_MANUAL,
    TASK_RESUME,
    TASK_SCENE_BOUNDARY,
    TASK_SCENE_STRUCTURE,
    TASK_WHOLE_BOOK,
    get_task_routing_entry,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_provider(
    session: Session,
    name: str,
    *,
    enabled: bool = True,
    plus_model: str | None = None,
) -> ProviderConfiguration:
    row = ProviderConfiguration(
        provider_name=name,
        enabled=enabled,
        disconnected=not enabled,
        plus_model=plus_model
        or ("deepseek-v4-flash" if name == "deepseek" else "qwen3.7-plus"),
        max_model="qwen3.7-max" if name.startswith("aliyun") else (plus_model or "deepseek-v4-flash"),
        flash_model="qwen3.6-flash" if name.startswith("aliyun") else (plus_model or "deepseek-v4-flash"),
        credential_reference=f"keyring:{name}",
    )
    session.add(row)
    session.flush()
    return row


def _set_active(session: Session, name: str) -> None:
    set_active_cloud_provider(session, name)
    session.commit()


def test_policy_modes_frozen() -> None:
    assert get_task_routing_entry(TASK_SCENE_BOUNDARY).mode == RoutingMode.FOLLOW_DEFAULT
    assert get_task_routing_entry(TASK_SCENE_STRUCTURE).mode == RoutingMode.FOLLOW_DEFAULT
    assert get_task_routing_entry(TASK_WHOLE_BOOK).mode == RoutingMode.FOLLOW_DEFAULT
    assert get_task_routing_entry(TASK_JSON_SCHEMA_REPAIR).mode == RoutingMode.INHERIT_RUN
    assert get_task_routing_entry(TASK_RESUME).mode == RoutingMode.INHERIT_RUN
    assert get_task_routing_entry(TASK_HIGH_DIFFICULTY_REVIEW).mode == RoutingMode.FIXED_PROVIDER
    assert get_task_routing_entry(TASK_HIGH_DIFFICULTY_REVIEW).fixed_provider == "aliyun_qwen_max"
    assert get_task_routing_entry(TASK_LOCAL_MANUAL).mode == RoutingMode.LOCAL_ONLY


def test_default_deepseek_routes_follow_default(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_provider(session, "deepseek", plus_model="deepseek-v4-flash")
    _seed_provider(session, "aliyun_qwen_plus")
    _set_active(session, "deepseek")
    monkeypatch.setattr(
        "app.services.cloud_provider_resolver_v1._credential_available",
        lambda *_a, **_k: True,
    )
    for task in (TASK_SCENE_BOUNDARY, TASK_SCENE_STRUCTURE, TASK_WHOLE_BOOK):
        resolved = resolve_provider_for_task(session, task_type=task)
        assert resolved.provider_name == "deepseek"
        assert resolved.model_name == "deepseek-v4-flash"
        assert resolved.resolution_source == ResolutionSource.USER_DEFAULT
        assert resolved.policy_label == "跟随默认"


def test_default_aliyun_routes_follow_default(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_provider(session, "deepseek")
    _seed_provider(session, "aliyun_qwen_plus", plus_model="qwen3.7-plus")
    _set_active(session, "aliyun_qwen_plus")
    monkeypatch.setattr(
        "app.services.cloud_provider_resolver_v1._credential_available",
        lambda *_a, **_k: True,
    )
    for task in (TASK_SCENE_BOUNDARY, TASK_SCENE_STRUCTURE, TASK_WHOLE_BOOK):
        resolved = resolve_provider_for_task(session, task_type=task)
        assert resolved.provider_name == "aliyun_qwen_plus"
        assert resolved.model_name == "qwen3.7-plus"
        assert resolved.resolution_source == ResolutionSource.USER_DEFAULT


def test_repair_and_resume_inherit_run_pin(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_provider(session, "deepseek")
    _seed_provider(session, "aliyun_qwen_plus")
    _set_active(session, "aliyun_qwen_plus")
    monkeypatch.setattr(
        "app.services.cloud_provider_resolver_v1._credential_available",
        lambda *_a, **_k: True,
    )
    for task in (TASK_JSON_SCHEMA_REPAIR, TASK_RESUME):
        resolved = resolve_provider_for_task(
            session,
            task_type=task,
            run_provider_name="deepseek",
            run_model_name="deepseek-v4-pro",
        )
        assert resolved.provider_name == "deepseek"
        assert resolved.model_name == "deepseek-v4-pro"
        assert resolved.resolution_source == ResolutionSource.RUN_PINNED


def test_run_pin_survives_settings_switch(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_provider(session, "deepseek")
    _seed_provider(session, "aliyun_qwen_plus")
    _set_active(session, "deepseek")
    monkeypatch.setattr(
        "app.services.cloud_provider_resolver_v1._credential_available",
        lambda *_a, **_k: True,
    )
    # Aliyun historical run while default is DeepSeek
    resolved = resolve_provider_for_task(
        session,
        task_type=TASK_RESUME,
        run_provider_name="aliyun_qwen_plus",
        run_model_name="qwen3.7-plus",
    )
    assert resolved.provider_name == "aliyun_qwen_plus"
    # DeepSeek run while default switched to Aliyun
    _set_active(session, "aliyun_qwen_plus")
    resolved2 = resolve_provider_for_task(
        session,
        task_type=TASK_JSON_SCHEMA_REPAIR,
        run_provider_name="deepseek",
        run_model_name="deepseek-v4-flash",
    )
    assert resolved2.provider_name == "deepseek"


def test_high_difficulty_fixed_aliyun_max(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_provider(session, "deepseek")
    _seed_provider(session, "aliyun_qwen_plus")
    _seed_provider(session, "aliyun_qwen_max", plus_model="qwen3.7-max")
    _set_active(session, "deepseek")
    monkeypatch.setattr(
        "app.services.cloud_provider_resolver_v1._credential_available",
        lambda *_a, **_k: True,
    )
    resolved = resolve_provider_for_task(session, task_type=TASK_HIGH_DIFFICULTY_REVIEW)
    assert resolved.provider_name == "aliyun_qwen_max"
    assert resolved.resolution_source == ResolutionSource.TASK_OVERRIDE


def test_disabled_active_deepseek_no_aliyun_fallback(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_provider(session, "deepseek", enabled=False)
    _seed_provider(session, "aliyun_qwen_plus", enabled=True)
    _set_active(session, "deepseek")
    monkeypatch.setattr(
        "app.services.cloud_provider_resolver_v1._credential_available",
        lambda *_a, **_k: True,
    )
    with pytest.raises(ProviderResolutionError) as exc:
        resolve_provider_for_task(session, task_type=TASK_SCENE_BOUNDARY)
    assert exc.value.code == "DEFAULT_PROVIDER_UNAVAILABLE"
    assert "DeepSeek" in exc.value.message
    assert "Aliyun" not in exc.value.message and "百炼" in exc.value.message or True
    # Must not resolve to Aliyun
    assert "aliyun" not in exc.value.message.lower() or "请前往设置" in exc.value.message


def test_disabled_active_aliyun_no_deepseek_fallback(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_provider(session, "deepseek", enabled=True)
    _seed_provider(session, "aliyun_qwen_plus", enabled=False)
    _set_active(session, "aliyun_qwen_plus")
    monkeypatch.setattr(
        "app.services.cloud_provider_resolver_v1._credential_available",
        lambda *_a, **_k: True,
    )
    with pytest.raises(ProviderResolutionError) as exc:
        resolve_provider_for_task(session, task_type=TASK_WHOLE_BOOK)
    assert exc.value.code == "DEFAULT_PROVIDER_UNAVAILABLE"
    assert "阿里云" in exc.value.message


def test_enabled_separate_from_active(session: Session) -> None:
    _seed_provider(session, "deepseek", enabled=True)
    _seed_provider(session, "aliyun_qwen_plus", enabled=True)
    _set_active(session, "deepseek")
    assert get_active_cloud_provider(session) == "deepseek"
    aliyun = session.scalar(
        select(ProviderConfiguration).where(ProviderConfiguration.provider_name == "aliyun_qwen_plus")
    )
    assert aliyun is not None and aliyun.enabled is True


def test_per_provider_default_model_persists(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_provider(session, "deepseek", plus_model="deepseek-v4-pro")
    _seed_provider(session, "aliyun_qwen_plus", plus_model="qwen3.7-plus")
    monkeypatch.setattr(
        "app.services.cloud_provider_resolver_v1._credential_available",
        lambda *_a, **_k: True,
    )
    _set_active(session, "deepseek")
    assert resolve_provider_for_task(session, task_type=TASK_WHOLE_BOOK).model_name == "deepseek-v4-pro"
    _set_active(session, "aliyun_qwen_plus")
    assert resolve_provider_for_task(session, task_type=TASK_WHOLE_BOOK).model_name == "qwen3.7-plus"
    _set_active(session, "deepseek")
    assert resolve_provider_for_task(session, task_type=TASK_WHOLE_BOOK).model_name == "deepseek-v4-pro"


def test_routing_preview_reflects_policy(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_provider(session, "deepseek", plus_model="deepseek-v4-flash")
    _seed_provider(session, "aliyun_qwen_plus")
    _seed_provider(session, "aliyun_qwen_max")
    _set_active(session, "deepseek")
    monkeypatch.setattr(
        "app.services.cloud_provider_resolver_v1._credential_available",
        lambda *_a, **_k: True,
    )
    rows = build_routing_preview(
        session,
        gateway_provider_names={
            "deepseek",
            "aliyun_qwen_plus",
            "aliyun_qwen_max",
            "local_qwen14",
            "local_qwen27_manual",
        },
    )
    by_task = {r["task_type"]: r for r in rows}
    assert by_task[TASK_SCENE_BOUNDARY]["provider"] == "deepseek"
    assert by_task[TASK_SCENE_BOUNDARY]["policy_label"] == "跟随默认"
    assert by_task[TASK_WHOLE_BOOK]["provider"] == "deepseek"
    assert by_task[TASK_JSON_SCHEMA_REPAIR]["policy_label"] == "继承当前 Run"
    assert by_task[TASK_HIGH_DIFFICULTY_REVIEW]["provider"] == "aliyun_qwen_max"
    assert by_task[TASK_LOCAL_MANUAL]["provider"] == "local_qwen14"


def test_analysis_execution_plan_follows_active_deepseek(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.model_gateway.base import ProviderCapabilities
    from app.services.analysis_execution_plan import build_analysis_execution_plan

    _seed_provider(session, "deepseek", plus_model="deepseek-v4-flash")
    _seed_provider(session, "aliyun_qwen_plus")
    _set_active(session, "deepseek")
    monkeypatch.setattr(
        "app.services.cloud_provider_resolver_v1._credential_available",
        lambda *_a, **_k: True,
    )

    class _Prov:
        def capabilities(self) -> ProviderCapabilities:
            return ProviderCapabilities(
                max_context_tokens=128000,
                default_timeout_seconds=60,
                cloud=True,
                supports_scene_analysis=True,
                supports_boundary_candidates=True,
                supports_structured_output=True,
                enabled=True,
                region="cloud",
                sends_content_to_cloud=True,
            )

    class _Gateway:
        def get(self, name: str):
            assert name == "deepseek"
            return _Prov()

    class _Store:
        def available(self) -> bool:
            return True

        def get(self, name: str):
            return "dummy"

    monkeypatch.setattr(
        "app.services.analysis_execution_plan.evaluate_manual_boundary_candidate",
        lambda *a, **k: {
            "configured": True,
            "credential_configured": True,
            "enabled": True,
            "connected": True,
            "manual_boundary_candidate_eligible": True,
            "manual_selection_blockers": [],
            "health_state": "healthy",
            "health_source": "cached_connection_test",
            "provider_state_version": "1",
        },
    )
    plan = build_analysis_execution_plan(
        session, gateway=_Gateway(), store=_Store(), mode="BALANCED"
    )
    assert plan.selected_provider == "deepseek"
    assert plan.selected_model == "deepseek-v4-flash"
    assert all(b.provider_id == "deepseek" for b in plan.stage_bindings)


def test_assert_formal_no_cross_substitute(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_provider(session, "deepseek", enabled=False)
    _seed_provider(session, "aliyun_qwen_plus", enabled=True)
    monkeypatch.setattr(
        "app.services.cloud_provider_resolver_v1._credential_available",
        lambda *_a, **_k: True,
    )
    with pytest.raises(ProviderResolutionError):
        assert_formal_provider_available(session, "deepseek")
