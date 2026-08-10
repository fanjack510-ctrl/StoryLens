"""CHG-20260810-077: formal Free create hang + call estimate/limit UX."""

from __future__ import annotations

import math
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import ProviderConfiguration, WholeBookConsent, WholeBookRun
from app.narrative_core.services.whole_book_consent_service import create_whole_book_consent
from app.narrative_core.services.whole_book_cost_estimate_service import (
    CF_MAX_CHAPTERS_PER_BATCH,
    CF_REPAIR_RESERVE_PER_BATCH,
    SYNTHESIS_PROVIDER_CALLS,
    _estimate_provider_call_breakdown,
    estimate_to_dict,
    estimate_whole_book_analysis,
)
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
from app.narrative_core.whole_book_v2.pipeline import (
    ChapterMeta,
    ProviderBudget,
    build_cost_plan,
    build_token_plan,
    plan_windows,
)
from app.services.credentials.fake_store import FakeCredentialStore
from app.services.provider_pricing import DEEPSEEK_MODEL_FLASH, DEEPSEEK_PROVIDER
from app.services.provider_runtime import set_active_cloud_provider
from tests.whole_book_minimal_test_helpers import make_engine, seed_sample_s_book


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED", "false")


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


def test_call_limit_exceeded_returns_clear_error(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch)
    engine = make_engine(tmp_path, "chg077-limit.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        provider = _seed_deepseek(session)
        estimate = estimate_whole_book_analysis(
            session, book.id, "whole_book_native", provider.id
        )
        estimate.estimated_provider_call_count = 2444
        estimate.estimated_input_tokens = 1_920_000
        estimate.estimated_output_tokens = 324_000
        estimate.estimated_cost_max_cny = Decimal("2.73")
        estimate.pricing_status = "available"
        session.flush()
        with pytest.raises(WholeBookFoundationError) as exc:
            assert_limits_cover_estimate(
                estimate,
                max_provider_calls=300,
                max_input_tokens=2_200_000,
                max_output_tokens=400_000,
                user_budget_limit_cny="10",
            )
        assert exc.value.code == WholeBookFoundationErrorCode.LIMIT_PROVIDER_CALLS_TOO_LOW.value
        assert "2444" in exc.value.message
        assert "300" in exc.value.message
        assert "请提高调用上限" in exc.value.message
    engine.dispose()


def test_no_task_created_when_consent_rejected(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch)
    store = FakeCredentialStore()
    store.set(DEEPSEEK_PROVIDER, "sk-ds")
    _patch_keyring(monkeypatch, store)
    engine = make_engine(tmp_path, "chg077-no-run.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        _seed_deepseek(session)
        set_active_cloud_provider(session, DEEPSEEK_PROVIDER)
        prepared = prepare_free_whole_book_analysis_v1(session, book.id)
        est = prepared["estimate"]
        before_runs = session.scalar(select(func.count()).select_from(WholeBookRun)) or 0
        before_consents = session.scalar(select(func.count()).select_from(WholeBookConsent)) or 0
        with pytest.raises(WholeBookFoundationError) as exc:
            create_whole_book_consent(
                session,
                book_id=book.id,
                estimate_id=int(est["estimate_id"]),
                user_budget_limit_cny="10.00",
                max_provider_calls=1,
                max_input_tokens=int(est["estimated_input_tokens"] or 1) + 10,
                max_output_tokens=int(est["estimated_output_tokens"] or 1) + 10,
            )
        assert exc.value.code == WholeBookFoundationErrorCode.LIMIT_PROVIDER_CALLS_TOO_LOW.value
        session.rollback()
        after_runs = session.scalar(select(func.count()).select_from(WholeBookRun)) or 0
        after_consents = session.scalar(select(func.count()).select_from(WholeBookConsent)) or 0
        assert after_runs == before_runs
        assert after_consents == before_consents
    engine.dispose()


def test_retry_after_create_failure_is_idempotent(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch)
    store = FakeCredentialStore()
    store.set(DEEPSEEK_PROVIDER, "sk-ds")
    _patch_keyring(monkeypatch, store)
    engine = make_engine(tmp_path, "chg077-idem.db")
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
        first = create_free_whole_book_analysis_v1(
            session,
            book.id,
            estimate_id=int(est["estimate_id"]),
            consent_id=consent.id,
            client_request_id="chg077-same",
            execute_pipeline=True,
            defer_execution=True,
        )
        second = create_free_whole_book_analysis_v1(
            session,
            book.id,
            estimate_id=int(est["estimate_id"]),
            consent_id=consent.id,
            client_request_id="chg077-same",
            execute_pipeline=True,
            defer_execution=True,
        )
        assert first["run_id"] == second["run_id"]
        assert first["deferred_execution"] is True
        assert first.get("pipeline") is None
        runs = session.scalars(select(WholeBookRun).where(WholeBookRun.book_id == book.id)).all()
        assert len(runs) == 1
    engine.dispose()


def test_call_estimate_breakdown() -> None:
    breakdown = _estimate_provider_call_breakdown(window_count=106, chapter_count=542)
    cf = int(math.ceil(542 / float(CF_MAX_CHAPTERS_PER_BATCH)))
    assert breakdown["window_extraction_calls"] == 106
    assert breakdown["final_synthesis_calls"] == SYNTHESIS_PROVIDER_CALLS
    assert breakdown["chapter_function_batch_calls"] == cf
    assert breakdown["repair_reserve_calls"] == cf * CF_REPAIR_RESERVE_PER_BATCH
    assert breakdown["estimated_total_calls"] == 106 + SYNTHESIS_PROVIDER_CALLS + cf + cf
    assert breakdown["estimated_total_calls"] == 244
    # User-reported 2444 is not produced by the Free minimal estimator.
    assert breakdown["estimated_total_calls"] != 2444
    sug = suggest_whole_book_limits(
        estimated_provider_calls=244,
        estimated_input_tokens=1_920_000,
        estimated_output_tokens=324_000,
        estimated_cost_max_cny="2.73",
    )
    assert sug["max_provider_calls"] == 300
    assert sug["max_input_tokens"] == 2_200_000
    assert sug["max_output_tokens"] == 400_000


def test_542_chapter_plan_call_count() -> None:
    chapter_count = 542
    character_count = 2_901_455
    per = max(1, character_count // chapter_count)
    rem = character_count - per * chapter_count
    chapters: list[ChapterMeta] = []
    for i in range(chapter_count):
        size = per + (rem if i == chapter_count - 1 else 0)
        chapters.append(
            ChapterMeta(
                chapter_id=i + 1,
                chapter_index=i + 1,
                title=f"第{i + 1}章",
                text=("汉" * size),
                snapshot_id=1,
                revision_hash="rev-yuzui",
            )
        )
    budget = ProviderBudget(provider="deepseek", model=DEEPSEEK_MODEL_FLASH)
    windows = plan_windows(chapters, book_id=77, budget=budget)
    token = build_token_plan(windows, budget=budget)
    cost = build_cost_plan(token, budget)
    assert token.window_count == len(windows)
    assert token.extract_calls == token.window_count
    assert token.final_synthesis_calls == 6
    assert token.estimated_total_calls == (
        token.extract_calls
        + token.consolidation_calls
        + token.final_synthesis_calls
        + token.repair_reserve_calls
    )
    assert token.context_safe == "YES"
    # Final synthesis counted as bounded units — not per-window raw text replay.
    assert token.final_synthesis_calls < token.window_count
    assert cost.estimated_cost_high >= cost.estimated_cost_low
    # Persist numbers for report assertions (deterministic).
    assert token.window_count >= 2
    assert token.estimated_total_calls < 2444


def test_cost_estimate_matches_hierarchical_plan() -> None:
    # Hierarchical V2 plan consistency (independent of Free minimal estimate).
    chapters = [
        ChapterMeta(
            chapter_id=i + 1,
            chapter_index=i + 1,
            title=f"c{i}",
            text="情节推进。" * 200,
            snapshot_id=1,
            revision_hash="r",
        )
        for i in range(40)
    ]
    budget = ProviderBudget(provider="deepseek", model=DEEPSEEK_MODEL_FLASH)
    windows = plan_windows(chapters, book_id=1, budget=budget)
    token = build_token_plan(windows, budget=budget)
    cost = build_cost_plan(token, budget)
    assert token.estimated_total_calls == (
        token.extract_calls
        + token.consolidation_calls
        + token.final_synthesis_calls
        + token.repair_reserve_calls
    )
    assert abs(
        cost.estimated_cost_high
        - (
            cost.extract_cost
            + cost.consolidation_cost
            + cost.synthesis_cost
            + cost.repair_reserve_cost
        )
    ) < 1e-5


def test_final_synthesis_not_counted_per_window_raw_text() -> None:
    from app.narrative_core.whole_book_v2.pipeline import WindowPlan

    windows = [
        WindowPlan(
            window_id=f"W-{i}",
            start_chapter_id=i,
            end_chapter_id=i,
            start_chapter_index=i,
            end_chapter_index=i,
            chapter_count=1,
            estimated_input_tokens=8_000,
            estimated_output_tokens=4_000,
            provider="deepseek",
            model=DEEPSEEK_MODEL_FLASH,
            snapshot_id=1,
            revision="r",
            chapter_ids=[i],
        )
        for i in range(1, 13)
    ]
    token = build_token_plan(
        windows,
        budget=ProviderBudget(provider="deepseek", model=DEEPSEEK_MODEL_FLASH),
    )
    assert token.window_count == 12
    assert token.extract_calls == 12
    assert token.final_synthesis_calls == 6
    # Must not multiply final synthesis by window count (no raw-text replay).
    assert token.final_synthesis_calls != token.window_count
    assert token.estimated_total_calls < token.window_count * token.final_synthesis_calls


def test_estimate_to_dict_exposes_breakdown(tmp_path, monkeypatch) -> None:
    _enable(monkeypatch)
    engine = make_engine(tmp_path, "chg077-breakdown.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        provider = _seed_deepseek(session)
        estimate = estimate_whole_book_analysis(
            session, book.id, "whole_book_native", provider.id
        )
        payload = estimate_to_dict(estimate)
        assert "call_breakdown" in payload
        assert payload["call_breakdown"]["estimated_total_calls"] == payload[
            "estimated_provider_call_count"
        ]
    engine.dispose()
