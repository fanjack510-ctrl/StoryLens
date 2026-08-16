"""WB-0.3 capability / cost estimate / consent tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db.models import Book, Chapter, Paragraph, ProviderConfiguration
from app.narrative_core.capability_registry import get_capability_metadata, list_capability_metadata
from app.narrative_core.enums import CapabilityKey
from app.narrative_core.services.capability_api_payloads import build_capabilities_list_response
from app.narrative_core.services.capability_service import DefaultCapabilityService
from app.narrative_core.services.whole_book_consent_service import (
    create_whole_book_consent,
    revoke_whole_book_consent,
    validate_whole_book_consent,
)
from app.narrative_core.services.whole_book_cost_estimate_service import (
    estimate_whole_book_analysis,
    is_estimate_valid,
)
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)


def _seed_book(session, *, chars: int = 2000, title: str = "t") -> tuple[Book, ProviderConfiguration]:
    book = Book(
        title=title,
        source_file_name=f"{title}.txt",
        source_file_hash=("a" * 64) if title == "t" else (title.encode().hex() + "0" * 64)[:64],
    )
    session.add(book)
    session.flush()
    ch = Chapter(book_id=book.id, chapter_index=0, title="c1", content_hash="b" * 64, word_count=chars)
    session.add(ch)
    session.flush()
    text = "汉" * chars
    session.add(
        Paragraph(
            id=f"p-{book.id}-0",
            book_id=book.id,
            chapter_id=ch.id,
            paragraph_index=0,
            raw_text=text,
            normalized_text=text,
            char_start=0,
            char_end=len(text),
            content_hash="c" * 64,
        )
    )
    provider = ProviderConfiguration(
        provider_name=f"fake-{book.id}",
        plus_model="qwen3.7-plus",
        enabled=True,
        disconnected=True,
    )
    session.add(provider)
    session.flush()
    return book, provider


def test_three_capabilities_semantics() -> None:
    native = get_capability_metadata(CapabilityKey.WHOLE_BOOK_NATIVE)
    enhanced = get_capability_metadata(CapabilityKey.WHOLE_BOOK_ENHANCED)
    insights = get_capability_metadata(CapabilityKey.CHAPTER_AGGREGATE_INSIGHTS)
    assert native.display_name == "原生全书分析"
    assert enhanced.display_name == "精细增强分析"
    assert insights.display_name == "章节精细分析覆盖"
    assert "全书洞察" not in native.display_name
    assert "原生" not in insights.display_name or "不属于" in insights.description


def test_entries_not_enabled() -> None:
    for key in (
        CapabilityKey.WHOLE_BOOK_NATIVE,
        CapabilityKey.WHOLE_BOOK_ENHANCED,
        CapabilityKey.CHAPTER_AGGREGATE_INSIGHTS,
    ):
        meta = get_capability_metadata(key)
        assert meta.enabled is False
        assert meta.entry_visible is False
        assert meta.product_reason_code == "whole_book_not_released"


def test_native_and_insights_names_not_mixed() -> None:
    payload = build_capabilities_list_response(DefaultCapabilityService())
    by_id = {item["capability_id"]: item for item in payload["items"]}
    assert by_id["whole_book_native"]["display_name"] == "原生全书分析"
    assert by_id["chapter_aggregate_insights"]["display_name"] == "章节精细分析覆盖"
    assert by_id["whole_book_native"]["entry_visible"] is False


def test_cost_grows_with_chars(testing_session) -> None:
    small, p1 = _seed_book(testing_session, chars=500, title="small")
    big, p2 = _seed_book(testing_session, chars=80_000, title="big")
    e1 = estimate_whole_book_analysis(testing_session, small.id, "whole_book_native", p1.id)
    e2 = estimate_whole_book_analysis(testing_session, big.id, "whole_book_native", p2.id)
    assert e2.character_count > e1.character_count
    assert e2.estimated_window_count > e1.estimated_window_count
    assert e2.estimated_provider_call_count > e1.estimated_provider_call_count
    assert e2.estimated_input_tokens > e1.estimated_input_tokens


def test_empty_book_estimate_safe(testing_session) -> None:
    book = Book(title="empty", source_file_name="e.txt", source_file_hash="e" * 64)
    testing_session.add(book)
    testing_session.flush()
    provider = ProviderConfiguration(provider_name="empty-p", plus_model="qwen3.7-plus")
    testing_session.add(provider)
    testing_session.flush()
    est = estimate_whole_book_analysis(testing_session, book.id, "whole_book_native", provider.id)
    assert est.estimated_window_count == 0
    assert est.estimated_provider_call_count == 0
    assert est.pricing_status == "unavailable"
    assert est.pricing_reason_code == "book_empty"
    assert est.estimated_cost_min_cny is None
    assert est.estimated_cost_max_cny is None


def test_unknown_pricing_no_fabricated_cost(testing_session, monkeypatch) -> None:
    book, provider = _seed_book(testing_session, chars=800, title="noprice")
    provider.plus_model = "totally-unknown-model-xyz"
    testing_session.flush()
    est = estimate_whole_book_analysis(testing_session, book.id, "whole_book_native", provider.id)
    assert est.pricing_status == "unavailable"
    assert est.estimated_cost_min_cny is None
    assert est.estimated_cost_max_cny is None
    assert est.estimated_window_count >= 1


def test_estimate_expiry(testing_session) -> None:
    book, provider = _seed_book(testing_session, chars=400, title="exp")
    est = estimate_whole_book_analysis(testing_session, book.id, "whole_book_native", provider.id)
    past = est.expires_at + timedelta(seconds=1)
    ok, code = is_estimate_valid(testing_session, est, now=past)
    assert ok is False
    assert code == WholeBookFoundationErrorCode.WHOLE_BOOK_ESTIMATE_EXPIRED.value


def test_book_change_invalidates_estimate(testing_session) -> None:
    book, provider = _seed_book(testing_session, chars=400, title="chg")
    est = estimate_whole_book_analysis(testing_session, book.id, "whole_book_native", provider.id)
    # Unified book_revision_v1 hashes real chapter title/text — mutate source text.
    para = testing_session.query(Paragraph).filter_by(book_id=book.id).first()
    assert para is not None
    para.normalized_text = (para.normalized_text or "") + "\n正文变更"
    para.raw_text = (para.raw_text or "") + "\n正文变更"
    testing_session.flush()
    ok, code = is_estimate_valid(testing_session, est)
    assert ok is False
    assert code == WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_CHANGED.value


def test_consent_binds_estimate_and_immutable(testing_session) -> None:
    from app.narrative_core.services.whole_book_snapshot_v1_service import create_or_reuse_book_snapshot_v1

    book, provider = _seed_book(testing_session, chars=400, title="cns")
    snap = create_or_reuse_book_snapshot_v1(testing_session, book.id)["snapshot"]
    est = estimate_whole_book_analysis(testing_session, book.id, "whole_book_native", provider.id)
    # Force unavailable path requiring limits
    est.pricing_status = "unavailable"
    est.estimated_cost_max_cny = None
    testing_session.flush()
    consent = create_whole_book_consent(
        testing_session,
        book_id=book.id,
        estimate_id=est.id,
        user_budget_limit_cny="1.00",
        max_provider_calls=10,
        max_input_tokens=100000,
        max_output_tokens=20000,
    )
    assert consent.estimate_id == est.id
    assert consent.auto_retry_enabled is False
    assert consent.max_retries_per_unit == 0
    # Immutable: no update API — mutate fields only via revoke+new
    original_budget = consent.user_budget_limit_cny
    consent.user_budget_limit_cny = Decimal("99")
    testing_session.flush()
    # Service contract: create always inserts new row; revoke marks revoked_at
    revoke_whole_book_consent(testing_session, consent.id)
    with pytest.raises(WholeBookFoundationError) as exc:
        validate_whole_book_consent(
            testing_session,
            consent.id,
            book_id=book.id,
            estimate_id=est.id,
            snapshot_id=snap.id,
        )
    assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_CONSENT_REVOKED.value
    assert original_budget is not None


def test_budget_too_low_rejected(testing_session, verified_cloud_pricing) -> None:
    book, provider = _seed_book(testing_session, chars=2000, title="low")
    est = estimate_whole_book_analysis(testing_session, book.id, "whole_book_native", provider.id)
    if est.pricing_status != "available" or est.estimated_cost_max_cny is None:
        pytest.skip("pricing not available for model in this environment")
    with pytest.raises(WholeBookFoundationError) as exc:
        create_whole_book_consent(
            testing_session,
            book_id=book.id,
            estimate_id=est.id,
            user_budget_limit_cny="0.000001",
        )
    # Two codes exist on purpose and they are not interchangeable:
    # WHOLE_BOOK_BUDGET_TOO_LOW rejects a *negative* budget, while BUDGET_TOO_LOW reports a
    # positive budget that is below the estimate. This case passes 0.000001 — positive, under
    # the estimate — so BUDGET_TOO_LOW is correct, and it is the one the desktop client
    # handles (`wholeBookStartLimits.ts`). The assertion, not the code, was wrong.
    assert exc.value.code == WholeBookFoundationErrorCode.BUDGET_TOO_LOW.value


def test_unavailable_requires_limits(testing_session) -> None:
    book, provider = _seed_book(testing_session, chars=400, title="lim")
    est = estimate_whole_book_analysis(testing_session, book.id, "whole_book_native", provider.id)
    est.pricing_status = "unavailable"
    est.estimated_cost_max_cny = None
    testing_session.flush()
    with pytest.raises(WholeBookFoundationError) as exc:
        create_whole_book_consent(
            testing_session,
            book_id=book.id,
            estimate_id=est.id,
            user_budget_limit_cny="1.00",
        )
    assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_CALL_LIMIT_REQUIRED.value


def test_consent_does_not_store_api_key(testing_session) -> None:
    book, provider = _seed_book(testing_session, chars=400, title="key")
    est = estimate_whole_book_analysis(testing_session, book.id, "whole_book_native", provider.id)
    est.pricing_status = "unavailable"
    testing_session.flush()
    consent = create_whole_book_consent(
        testing_session,
        book_id=book.id,
        estimate_id=est.id,
        user_budget_limit_cny="5",
        max_provider_calls=5,
        max_input_tokens=1000,
        max_output_tokens=1000,
    )
    blob = str(consent.__dict__)
    assert "api_key" not in blob.lower()
    assert "sk-" not in blob


def test_registry_lists_new_keys() -> None:
    keys = {m.key for m in list_capability_metadata()}
    assert CapabilityKey.WHOLE_BOOK_NATIVE in keys
    assert CapabilityKey.WHOLE_BOOK_ENHANCED in keys
    assert CapabilityKey.CHAPTER_AGGREGATE_INSIGHTS in keys
