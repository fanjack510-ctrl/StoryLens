"""CHG-20260808-062: Whole-Book start limit validation + create consent UX."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import ProviderConfiguration
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
from app.narrative_core.services.whole_book_start_limits_v1 import (
    assert_limits_cover_estimate,
    suggest_whole_book_limits,
)
from app.services.credentials.fake_store import FakeCredentialStore
from app.services.provider_pricing import DEEPSEEK_MODEL_FLASH, DEEPSEEK_PROVIDER
from app.services.provider_runtime import set_active_cloud_provider
from tests.whole_book_minimal_test_helpers import make_engine, seed_sample_s_book


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED", "true")


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


def _seed_deepseek(session) -> ProviderConfiguration:
    row = ProviderConfiguration(
        provider_name=DEEPSEEK_PROVIDER,
        enabled=True,
        disconnected=False,
        plus_model=DEEPSEEK_MODEL_FLASH,
        max_model=DEEPSEEK_MODEL_FLASH,
        flash_model=DEEPSEEK_MODEL_FLASH,
        base_url="https://api.deepseek.com",
        credential_reference="keyring:deepseek",
    )
    session.add(row)
    session.flush()
    return row


def test_suggest_limits_have_headroom_for_user_screenshot_numbers() -> None:
    sug = suggest_whole_book_limits(
        estimated_provider_calls=425,
        estimated_input_tokens=1_758_000,
        estimated_output_tokens=297_000,
        estimated_cost_max_cny="2.5005",
    )
    assert sug["max_provider_calls"] == 500
    assert sug["max_input_tokens"] == 2_000_000
    assert sug["max_output_tokens"] == 350_000
    assert sug["max_cost_budget_cny"] == "10.00"


def test_assert_limits_provider_calls_too_low(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch)
    engine = make_engine(tmp_path, "chg062-calls.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        provider = _seed_deepseek(session)
        estimate = estimate_whole_book_analysis(
            session, book.id, "whole_book_native", provider.id
        )
        # Force large estimate numbers matching product case.
        estimate.estimated_provider_call_count = 425
        estimate.estimated_input_tokens = 1_758_000
        estimate.estimated_output_tokens = 297_000
        estimate.estimated_cost_max_cny = Decimal("2.5005")
        estimate.pricing_status = "available"
        session.flush()
        with pytest.raises(WholeBookFoundationError) as exc:
            assert_limits_cover_estimate(
                estimate,
                max_provider_calls=200,
                max_input_tokens=2_000_000,
                max_output_tokens=400_000,
                user_budget_limit_cny="10",
            )
        assert exc.value.code == WholeBookFoundationErrorCode.LIMIT_PROVIDER_CALLS_TOO_LOW.value
    engine.dispose()


def test_assert_limits_input_and_output_too_low(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch)
    engine = make_engine(tmp_path, "chg062-tokens.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        provider = _seed_deepseek(session)
        estimate = estimate_whole_book_analysis(
            session, book.id, "whole_book_native", provider.id
        )
        estimate.estimated_provider_call_count = 425
        estimate.estimated_input_tokens = 1_758_000
        estimate.estimated_output_tokens = 297_000
        estimate.estimated_cost_max_cny = Decimal("2.5005")
        estimate.pricing_status = "available"
        session.flush()
        with pytest.raises(WholeBookFoundationError) as exc_in:
            assert_limits_cover_estimate(
                estimate,
                max_provider_calls=500,
                max_input_tokens=500_000,
                max_output_tokens=400_000,
                user_budget_limit_cny="10",
            )
        assert exc_in.value.code == WholeBookFoundationErrorCode.LIMIT_INPUT_TOKENS_TOO_LOW.value
        with pytest.raises(WholeBookFoundationError) as exc_out:
            assert_limits_cover_estimate(
                estimate,
                max_provider_calls=500,
                max_input_tokens=2_000_000,
                max_output_tokens=100_000,
                user_budget_limit_cny="10",
            )
        assert exc_out.value.code == WholeBookFoundationErrorCode.LIMIT_OUTPUT_TOKENS_TOO_LOW.value
    engine.dispose()


def test_budget_pass_when_above_estimate_max(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch)
    engine = make_engine(tmp_path, "chg062-budget.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        provider = _seed_deepseek(session)
        estimate = estimate_whole_book_analysis(
            session, book.id, "whole_book_native", provider.id
        )
        estimate.estimated_provider_call_count = 425
        estimate.estimated_input_tokens = 1_758_000
        estimate.estimated_output_tokens = 297_000
        estimate.estimated_cost_max_cny = Decimal("2.5005")
        estimate.pricing_status = "available"
        session.flush()
        assert_limits_cover_estimate(
            estimate,
            max_provider_calls=500,
            max_input_tokens=2_000_000,
            max_output_tokens=400_000,
            user_budget_limit_cny="10",
        )
    engine.dispose()


def test_consent_rejects_low_limits(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch)
    engine = make_engine(tmp_path, "chg062-consent.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        provider = _seed_deepseek(session)
        estimate = estimate_whole_book_analysis(
            session, book.id, "whole_book_native", provider.id
        )
        estimate.estimated_provider_call_count = 425
        estimate.estimated_input_tokens = 1_758_000
        estimate.estimated_output_tokens = 297_000
        estimate.estimated_cost_max_cny = Decimal("2.5005")
        estimate.pricing_status = "available"
        session.flush()
        with pytest.raises(WholeBookFoundationError) as exc:
            create_whole_book_consent(
                session,
                book_id=book.id,
                estimate_id=estimate.id,
                user_budget_limit_cny="10",
                max_provider_calls=200,
                max_input_tokens=500_000,
                max_output_tokens=100_000,
            )
        assert exc.value.code == WholeBookFoundationErrorCode.LIMIT_PROVIDER_CALLS_TOO_LOW.value
    engine.dispose()


def test_prepare_recommended_limits_cover_estimate(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch)
    store = FakeCredentialStore()
    store.set(DEEPSEEK_PROVIDER, "sk-ds")
    _patch_keyring(monkeypatch, store)
    engine = make_engine(tmp_path, "chg062-prepare-rec.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        _seed_deepseek(session)
        set_active_cloud_provider(session, DEEPSEEK_PROVIDER)
        payload = prepare_free_whole_book_analysis_v1(session, book.id)
        est = payload["estimate"]
        rec = payload["recommended_limits"]
        assert payload["active_provider_name"] == DEEPSEEK_PROVIDER
        assert est["model_name"] == DEEPSEEK_MODEL_FLASH
        assert rec["max_provider_calls"] >= int(est["estimated_provider_calls"] or 0)
        assert rec["max_input_tokens"] >= int(est["estimated_input_tokens"] or 0)
        assert rec["max_output_tokens"] >= int(est["estimated_output_tokens"] or 0)
    engine.dispose()


def test_create_inline_consent_with_sufficient_limits_no_pipeline(
    tmp_path, monkeypatch
) -> None:
    _enable(monkeypatch)
    store = FakeCredentialStore()
    store.set(DEEPSEEK_PROVIDER, "sk-ds")
    _patch_keyring(monkeypatch, store)
    engine = make_engine(tmp_path, "chg062-create-ok.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        _seed_deepseek(session)
        set_active_cloud_provider(session, DEEPSEEK_PROVIDER)
        prepared = prepare_free_whole_book_analysis_v1(session, book.id)
        est = prepared["estimate"]
        rec = prepared["recommended_limits"]
        consent = create_whole_book_consent(
            session,
            book_id=book.id,
            estimate_id=int(est["estimate_id"]),
            user_budget_limit_cny=rec["max_cost_budget_cny"],
            max_provider_calls=int(rec["max_provider_calls"]),
            max_input_tokens=int(rec["max_input_tokens"]),
            max_output_tokens=int(rec["max_output_tokens"]),
        )
        result = create_free_whole_book_analysis_v1(
            session,
            book.id,
            estimate_id=int(est["estimate_id"]),
            consent_id=consent.id,
            client_request_id="chg062-ok",
            execute_pipeline=False,
        )
        assert result["run"]["provider_name"] == DEEPSEEK_PROVIDER
        assert result["run"]["model_name"] == DEEPSEEK_MODEL_FLASH
    engine.dispose()


def test_free_create_schema_accepts_limits_without_consent_id() -> None:
    from pydantic import ValidationError

    from app.routers.whole_book_free_product_router import CreateFreeRunRequest

    body = CreateFreeRunRequest.model_validate(
        {
            "estimate_id": 1,
            "client_request_id": "chg062-schema",
            "max_provider_calls": 500,
            "max_input_tokens": 2_000_000,
            "max_output_tokens": 400_000,
            "max_cost_budget_cny": "10.00",
            "auto_retry_enabled": False,
        }
    )
    assert body.consent_id is None
    assert body.max_provider_calls == 500
    assert body.estimate_id == 1

    # Explicit null consent_id is accepted (desktop used to send this and 422).
    body_null = CreateFreeRunRequest.model_validate(
        {
            "estimate_id": 2,
            "consent_id": None,
            "client_request_id": "chg062-schema-null",
            "max_cost_budget_cny": "10.00",
        }
    )
    assert body_null.consent_id is None

    with pytest.raises(ValidationError):
        CreateFreeRunRequest.model_validate(
            {
                "consent_id": 1,
                "client_request_id": "missing-estimate",
            }
        )
