"""CHG-20260808-061: Whole-Book follows active_cloud_provider; no silent Aliyun fallback."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import ProviderConfiguration, WholeBookRun
from app.narrative_core.services.whole_book_consent_service import create_whole_book_consent
from app.narrative_core.services.whole_book_cost_estimate_service import estimate_whole_book_analysis
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_free_product_v1_service import (
    create_free_whole_book_analysis_v1,
    prepare_free_whole_book_analysis_v1,
)
from app.narrative_core.services.whole_book_gateway_transport_v1 import resolve_formal_provider_row
from app.narrative_core.services.whole_book_minimal_pipeline_v1_service import (
    build_formal_gateway_transports,
)
from app.narrative_core.services.whole_book_run_v1_service import create_whole_book_run_v1
from app.services.credentials.fake_store import FakeCredentialStore
from app.services.provider_pricing import DEEPSEEK_MODEL_FLASH, DEEPSEEK_PROVIDER
from app.services.provider_runtime import get_active_cloud_provider, set_active_cloud_provider
from tests.whole_book_minimal_test_helpers import make_engine, seed_sample_s_book

ALIYUN = "aliyun_qwen_plus"
ALIYUN_MODEL = "qwen3.7-plus"


def _enable_flags(monkeypatch: pytest.MonkeyPatch, *, real: bool = True) -> None:
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED", "true")
    monkeypatch.setenv(
        "STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED",
        "true" if real else "false",
    )


def _patch_keyring(monkeypatch: pytest.MonkeyPatch, store: FakeCredentialStore) -> None:
    class _Store:
        def available(self) -> bool:
            return True

        def get(self, name: str) -> str | None:
            return store.get(name)

    monkeypatch.setattr(
        "app.narrative_core.services.whole_book_active_provider_v1.KeyringCredentialStore",
        lambda: _Store(),
    )
    monkeypatch.setattr(
        "app.narrative_core.services.whole_book_gateway_transport_v1.KeyringCredentialStore",
        lambda: _Store(),
    )


def _seed_deepseek(session, *, enabled: bool = True, with_key: bool = True) -> ProviderConfiguration:
    row = ProviderConfiguration(
        provider_name=DEEPSEEK_PROVIDER,
        display_name="DeepSeek",
        enabled=enabled,
        disconnected=not enabled,
        plus_model=DEEPSEEK_MODEL_FLASH,
        max_model=DEEPSEEK_MODEL_FLASH,
        flash_model=DEEPSEEK_MODEL_FLASH,
        base_url="https://api.deepseek.com",
        credential_reference="keyring:deepseek" if with_key else None,
    )
    session.add(row)
    session.flush()
    return row


def _seed_aliyun(session, *, enabled: bool = True, with_key: bool = True) -> ProviderConfiguration:
    row = ProviderConfiguration(
        provider_name=ALIYUN,
        display_name="Aliyun",
        enabled=enabled,
        disconnected=not enabled,
        plus_model=ALIYUN_MODEL,
        max_model=ALIYUN_MODEL,
        flash_model=ALIYUN_MODEL,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        credential_reference="keyring:aliyun_qwen_plus" if with_key else None,
    )
    session.add(row)
    session.flush()
    return row


def test_deepseek_set_current_prepare_provider_and_model(tmp_path, monkeypatch) -> None:
    _enable_flags(monkeypatch)
    store = FakeCredentialStore()
    store.set(DEEPSEEK_PROVIDER, "sk-ds-test")
    _patch_keyring(monkeypatch, store)
    engine = make_engine(tmp_path, "chg061-prepare-ds.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        _seed_deepseek(session)
        _seed_aliyun(session)
        set_active_cloud_provider(session, DEEPSEEK_PROVIDER)
        assert get_active_cloud_provider(session) == DEEPSEEK_PROVIDER
        payload = prepare_free_whole_book_analysis_v1(session, book.id)
        assert payload["active_provider_name"] == DEEPSEEK_PROVIDER
        assert payload["active_model_name"] == DEEPSEEK_MODEL_FLASH
        assert payload["estimate"]["provider_name"] == DEEPSEEK_PROVIDER
        assert payload["estimate"]["model_name"] == DEEPSEEK_MODEL_FLASH
        assert payload["provider_available"] is True
        assert payload["run_creation_enabled"] is True
        assert payload["blocking_reasons"] == []
    engine.dispose()


def test_deepseek_cost_estimate_uses_deepseek_pricing(tmp_path, monkeypatch) -> None:
    _enable_flags(monkeypatch)
    store = FakeCredentialStore()
    store.set(DEEPSEEK_PROVIDER, "sk-ds-test")
    _patch_keyring(monkeypatch, store)
    engine = make_engine(tmp_path, "chg061-ds-cost.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        _seed_deepseek(session)
        aliyun = _seed_aliyun(session)
        set_active_cloud_provider(session, DEEPSEEK_PROVIDER)
        payload = prepare_free_whole_book_analysis_v1(session, book.id)
        est = payload["estimate"]
        assert est["provider_name"] == DEEPSEEK_PROVIDER
        assert est["model_name"] == DEEPSEEK_MODEL_FLASH
        assert est["price_known"] is True
        assert Decimal(str(est["estimated_cost_min_cny"])) > 0
        aliyun_est = estimate_whole_book_analysis(
            session, book.id, "whole_book_native", aliyun.id
        )
        # Same book, different registry prices → ranges must not be identical.
        assert (
            Decimal(str(est["estimated_cost_min_cny"])),
            Decimal(str(est["estimated_cost_max_cny"])),
        ) != (
            Decimal(str(aliyun_est.estimated_cost_min_cny or 0)),
            Decimal(str(aliyun_est.estimated_cost_max_cny or 0)),
        )
        assert aliyun_est.model_name == ALIYUN_MODEL
    engine.dispose()


def test_deepseek_disabled_blocks_formal_create_no_aliyun_fallback(tmp_path, monkeypatch) -> None:
    _enable_flags(monkeypatch)
    store = FakeCredentialStore()
    store.set(DEEPSEEK_PROVIDER, "sk-ds-test")
    store.set(ALIYUN, "sk-aliyun-test")
    _patch_keyring(monkeypatch, store)
    engine = make_engine(tmp_path, "chg061-ds-disabled.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        _seed_deepseek(session, enabled=False)
        _seed_aliyun(session, enabled=True)
        set_active_cloud_provider(session, DEEPSEEK_PROVIDER)
        payload = prepare_free_whole_book_analysis_v1(session, book.id)
        assert payload["estimate"]["provider_name"] == DEEPSEEK_PROVIDER
        assert payload["run_creation_enabled"] is False
        assert payload["provider_available"] is False
        assert any("当前服务商" in b for b in payload["blocking_reasons"])
        with pytest.raises(WholeBookFoundationError) as exc:
            resolve_formal_provider_row(session, provider_name=DEEPSEEK_PROVIDER)
        assert "未启用" in exc.value.message or "deepseek" in exc.value.message.lower()
        # Active DeepSeek disabled → must not silently resolve Aliyun.
        with pytest.raises(WholeBookFoundationError):
            resolve_formal_provider_row(session)
    engine.dispose()


def test_switch_provider_produces_new_estimate_identity(tmp_path, monkeypatch) -> None:
    _enable_flags(monkeypatch)
    store = FakeCredentialStore()
    store.set(DEEPSEEK_PROVIDER, "sk-ds-test")
    store.set(ALIYUN, "sk-aliyun-test")
    _patch_keyring(monkeypatch, store)
    engine = make_engine(tmp_path, "chg061-switch-est.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        _seed_deepseek(session)
        _seed_aliyun(session)
        set_active_cloud_provider(session, ALIYUN)
        a = prepare_free_whole_book_analysis_v1(session, book.id)
        set_active_cloud_provider(session, DEEPSEEK_PROVIDER)
        d = prepare_free_whole_book_analysis_v1(session, book.id)
        assert a["estimate"]["provider_name"] == ALIYUN
        assert d["estimate"]["provider_name"] == DEEPSEEK_PROVIDER
        assert a["estimate"]["estimate_id"] != d["estimate"]["estimate_id"]
        assert a["estimate"]["provider_config_id"] != d["estimate"]["provider_config_id"]
        assert a["estimate"]["model_name"] == ALIYUN_MODEL
        assert d["estimate"]["model_name"] == DEEPSEEK_MODEL_FLASH
    engine.dispose()


def test_stale_estimate_rejected_after_provider_switch(tmp_path, monkeypatch) -> None:
    _enable_flags(monkeypatch)
    store = FakeCredentialStore()
    store.set(DEEPSEEK_PROVIDER, "sk-ds-test")
    store.set(ALIYUN, "sk-aliyun-test")
    _patch_keyring(monkeypatch, store)
    engine = make_engine(tmp_path, "chg061-stale-est.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        _seed_deepseek(session)
        _seed_aliyun(session)
        set_active_cloud_provider(session, ALIYUN)
        prepared = prepare_free_whole_book_analysis_v1(session, book.id)
        estimate_id = int(prepared["estimate"]["estimate_id"])
        consent = create_whole_book_consent(
            session,
            book_id=book.id,
            estimate_id=estimate_id,
            user_budget_limit_cny="1000",
            max_provider_calls=100,
            max_input_tokens=10_000_000,
            max_output_tokens=10_000_000,
        )
        set_active_cloud_provider(session, DEEPSEEK_PROVIDER)
        with pytest.raises(WholeBookFoundationError) as exc:
            create_free_whole_book_analysis_v1(
                session,
                book.id,
                estimate_id=estimate_id,
                consent_id=consent.id,
                client_request_id="stale-est-1",
                execute_pipeline=False,
            )
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_ESTIMATE_EXPIRED.value
    engine.dispose()


def test_create_pins_provider_and_model(tmp_path, monkeypatch) -> None:
    _enable_flags(monkeypatch)
    store = FakeCredentialStore()
    store.set(DEEPSEEK_PROVIDER, "sk-ds-test")
    _patch_keyring(monkeypatch, store)
    engine = make_engine(tmp_path, "chg061-pin-create.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        _seed_deepseek(session)
        set_active_cloud_provider(session, DEEPSEEK_PROVIDER)
        prepared = prepare_free_whole_book_analysis_v1(session, book.id)
        consent = create_whole_book_consent(
            session,
            book_id=book.id,
            estimate_id=int(prepared["estimate"]["estimate_id"]),
            user_budget_limit_cny="1000",
            max_provider_calls=100,
            max_input_tokens=10_000_000,
            max_output_tokens=10_000_000,
        )
        result = create_free_whole_book_analysis_v1(
            session,
            book.id,
            estimate_id=int(prepared["estimate"]["estimate_id"]),
            consent_id=consent.id,
            client_request_id="pin-create-1",
            execute_pipeline=False,
        )
        run = result["run"]
        assert run["provider_name"] == DEEPSEEK_PROVIDER
        assert run["model_name"] == DEEPSEEK_MODEL_FLASH
        run_id = run.get("id") or run.get("run_id")
        set_active_cloud_provider(session, ALIYUN)
        _seed_aliyun(session)
        refreshed = session.get(WholeBookRun, run_id)
        assert refreshed is not None
        assert refreshed.provider_name == DEEPSEEK_PROVIDER
        assert refreshed.model_name == DEEPSEEK_MODEL_FLASH
    engine.dispose()


def test_old_aliyun_run_resume_transport_stays_aliyun(tmp_path, monkeypatch) -> None:
    _enable_flags(monkeypatch)
    store = FakeCredentialStore()
    store.set(ALIYUN, "sk-aliyun-test")
    store.set(DEEPSEEK_PROVIDER, "sk-ds-test")
    _patch_keyring(monkeypatch, store)
    engine = make_engine(tmp_path, "chg061-pin-aliyun.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snap_id = seed_sample_s_book(session)
        aliyun = _seed_aliyun(session)
        _seed_deepseek(session)
        run = create_whole_book_run_v1(
            session,
            book.id,
            snap_id,
            "whole_book_native",
            "old-aliyun-run",
            "formal",
        )
        run.provider_name = ALIYUN
        run.model_name = ALIYUN_MODEL
        session.flush()
        set_active_cloud_provider(session, DEEPSEEK_PROVIDER)
        transports = build_formal_gateway_transports(
            session, run=run, provider_config_id=aliyun.id
        )
        assert transports.window.provider_id == ALIYUN
        assert transports.window.model_name == ALIYUN_MODEL
    engine.dispose()


def test_old_deepseek_run_resume_transport_stays_deepseek(tmp_path, monkeypatch) -> None:
    _enable_flags(monkeypatch)
    store = FakeCredentialStore()
    store.set(ALIYUN, "sk-aliyun-test")
    store.set(DEEPSEEK_PROVIDER, "sk-ds-test")
    _patch_keyring(monkeypatch, store)
    engine = make_engine(tmp_path, "chg061-pin-ds.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snap_id = seed_sample_s_book(session)
        ds = _seed_deepseek(session)
        _seed_aliyun(session)
        run = create_whole_book_run_v1(
            session,
            book.id,
            snap_id,
            "whole_book_native",
            "old-ds-run",
            "formal",
        )
        run.provider_name = DEEPSEEK_PROVIDER
        run.model_name = DEEPSEEK_MODEL_FLASH
        session.flush()
        set_active_cloud_provider(session, ALIYUN)
        transports = build_formal_gateway_transports(
            session, run=run, provider_config_id=ds.id
        )
        assert transports.window.provider_id == DEEPSEEK_PROVIDER
        assert transports.window.model_name == DEEPSEEK_MODEL_FLASH
    engine.dispose()


def test_aliyun_path_regression_prepare(tmp_path, monkeypatch) -> None:
    _enable_flags(monkeypatch)
    store = FakeCredentialStore()
    store.set(ALIYUN, "sk-aliyun-test")
    _patch_keyring(monkeypatch, store)
    engine = make_engine(tmp_path, "chg061-aliyun-ok.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        _seed_aliyun(session)
        set_active_cloud_provider(session, ALIYUN)
        payload = prepare_free_whole_book_analysis_v1(session, book.id)
        assert payload["estimate"]["provider_name"] == ALIYUN
        assert payload["estimate"]["model_name"] == ALIYUN_MODEL
        assert payload["run_creation_enabled"] is True
        assert payload["provider_available"] is True
    engine.dispose()


def test_routing_preview_includes_whole_book_active_provider(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    _enable_flags(monkeypatch)
    engine = make_engine(tmp_path, "chg061-routing.db")
    factory = sessionmaker(bind=engine)

    def _override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    try:
        with factory() as session:
            _seed_deepseek(session)
            set_active_cloud_provider(session, DEEPSEEK_PROVIDER)
            session.commit()
        client = TestClient(app)
        resp = client.get("/api/v1/model-routing/preview")
        assert resp.status_code == 200
        rows = resp.json()
        whole = next(r for r in rows if r["task"] == "全书分析")
        assert whole["provider"] == DEEPSEEK_PROVIDER
        assert whole["model"] == DEEPSEEK_MODEL_FLASH
        boundary = next(r for r in rows if r["task"] == "场景边界")
        assert boundary["provider"] == ALIYUN
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
