"""Free whole-book product coordination (WB-1.7 backend slice)."""

from __future__ import annotations

import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Book, ProviderConfiguration, WholeBookRun
from app.narrative_core.contracts.whole_book_contract_v1 import ResultOrigin, WholeBookMode, WholeBookRunStatus
from app.narrative_core.services.whole_book_consent_service import create_whole_book_consent, validate_whole_book_consent
from app.narrative_core.services.whole_book_cost_estimate_service import (
    compute_book_revision_hash,
    estimate_to_dict,
    estimate_whole_book_analysis,
)
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_fixture_pipeline_v1_service import execute_fixture_minimal_pipeline_v1
from app.narrative_core.services.whole_book_minimal_helpers_v1 import real_provider_enabled
from app.narrative_core.services.whole_book_native_input_audit_v1 import (
    assert_native_input_independence_v1,
    persist_native_input_audit_v1,
)
from app.narrative_core.services.whole_book_product_capability_v1 import (
    AccessTier,
    require_capability_access,
)
from app.narrative_core.services.whole_book_run_v1_service import (
    create_whole_book_run_v1,
    list_runs_for_book,
    run_to_dict,
    start_whole_book_run_v1,
)
from app.narrative_core.services.whole_book_snapshot_v1_service import create_or_reuse_book_snapshot_v1
from app.narrative_core.services.whole_book_windowing_v1_service import generate_whole_book_windows_v1


def free_product_enabled() -> bool:
    # V1.2.0 Free contract: formal whole-book product ON by default in production.
    # Explicit false/0/off still disables. Fixture preview remains default OFF.
    return os.environ.get("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def fixture_preview_enabled() -> bool:
    return os.environ.get("STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _require_free_product_enabled() -> None:
    if not free_product_enabled():
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_FREE_PRODUCT_DISABLED,
            "全书分析 Free 产品尚未启用",
        )


def _latest_run_for_book(session: Session, book_id: int) -> WholeBookRun | None:
    runs = list_runs_for_book(session, book_id)
    return runs[0] if runs else None


def _recoverable_run(session: Session, book_id: int) -> WholeBookRun | None:
    for run in list_runs_for_book(session, book_id):
        if run.status in {
            WholeBookRunStatus.paused.value,
            WholeBookRunStatus.recoverable.value,
            WholeBookRunStatus.running.value,
            WholeBookRunStatus.pending.value,
        }:
            return run
    return None


def prepare_free_whole_book_analysis_v1(session: Session, book_id: int) -> dict[str, Any]:
    _require_free_product_enabled()
    require_capability_access("whole_book.overview", AccessTier.free)
    require_capability_access("whole_book.characters_events", AccessTier.free)
    require_capability_access("whole_book.structure", AccessTier.free)
    require_capability_access("whole_book.chapter_functions", AccessTier.free)
    book = session.get(Book, book_id)
    if book is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_NOT_FOUND,
            "书籍不存在",
        )
    revision_hash = compute_book_revision_hash(session, book_id)
    provider = None
    if real_provider_enabled():
        # Prefer canonical Bailian row for formal Free cost estimate binding.
        provider = session.scalar(
            select(ProviderConfiguration).where(
                ProviderConfiguration.provider_name == "aliyun_qwen_plus"
            )
        )
    if provider is None:
        provider = session.scalar(select(ProviderConfiguration).limit(1))
    if provider is None:
        provider = ProviderConfiguration(
            provider_name="aliyun_qwen_plus" if real_provider_enabled() else "default",
            plus_model="qwen3.7-plus" if real_provider_enabled() else "default-model",
            enabled=bool(real_provider_enabled()),
            disconnected=not bool(real_provider_enabled()),
        )
        session.add(provider)
        session.flush()
    estimate = estimate_whole_book_analysis(
        session, book_id, WholeBookMode.whole_book_native.value, provider.id
    )
    latest = _latest_run_for_book(session, book_id)
    recoverable = _recoverable_run(session, book_id)
    snap_result = create_or_reuse_book_snapshot_v1(session, book_id)
    needs_new_snapshot = (
        latest is not None
        and latest.snapshot_id is not None
        and snap_result["reused"] is False
    )
    est = estimate_to_dict(estimate)
    real_on = real_provider_enabled()
    fixture_on = fixture_preview_enabled()
    return {
        "book_id": book_id,
        "book_title": book.title or "",
        "book_revision_hash": revision_hash,
        "chapter_count": int(est.get("chapter_count") or 0),
        "character_count": int(est.get("character_count") or 0),
        "mode": WholeBookMode.whole_book_native.value,
        "mode_label": "原生全书分析",
        "product_enabled": True,
        "real_provider_enabled": real_on,
        "run_creation_enabled": real_on,
        "fixture_preview_enabled": fixture_on,
        "latest_run": run_to_dict(latest) if latest is not None else None,
        "recoverable_run": run_to_dict(recoverable) if recoverable is not None else None,
        "latest_run_id": latest.id if latest else None,
        "latest_run_status": latest.status if latest else None,
        "recoverable_run_id": recoverable.id if recoverable else None,
        "needs_new_snapshot": needs_new_snapshot,
        "snapshot_rebuild_required": needs_new_snapshot,
        "snapshot": {
            "snapshot_id": snap_result["snapshot"].id,
            "reused": snap_result["reused"],
        },
        "estimate": {
            "estimate_id": est["id"],
            "book_id": est["book_id"],
            "mode": est["mode"],
            "estimated_windows": est.get("estimated_window_count"),
            "estimated_provider_calls": est.get("estimated_provider_call_count"),
            "estimated_input_tokens": est.get("estimated_input_tokens"),
            "estimated_output_tokens": est.get("estimated_output_tokens"),
            "estimated_cost_min_cny": est.get("estimated_cost_min_cny"),
            "estimated_cost_max_cny": est.get("estimated_cost_max_cny"),
            "provider_name": provider.provider_name,
            "model_name": est.get("model_name"),
            "price_known": str(est.get("pricing_status") or "") == "available",
            "currency": est.get("currency") or "CNY",
        },
        "recommended_limits": {
            "max_provider_calls": 200,
            "max_input_tokens": 500_000,
            "max_output_tokens": 100_000,
            "max_cost_budget_cny": "10.00",
        },
        "blocking_reasons": [],
        "warnings": [],
    }


def create_free_whole_book_analysis_v1(
    session: Session,
    book_id: int,
    *,
    estimate_id: int,
    consent_id: int,
    client_request_id: str,
    execute_pipeline: bool = True,
) -> dict[str, Any]:
    _require_free_product_enabled()
    require_capability_access("whole_book.overview", AccessTier.free)
    require_capability_access("whole_book.characters_events", AccessTier.free)
    require_capability_access("whole_book.structure", AccessTier.free)
    require_capability_access("whole_book.chapter_functions", AccessTier.free)
    book = session.get(Book, book_id)
    if book is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_NOT_FOUND,
            "书籍不存在",
        )
    snap = create_or_reuse_book_snapshot_v1(session, book_id)["snapshot"]
    # Same Consent Contract as create-fixture (book / estimate / snapshot / revision).
    validate_whole_book_consent(
        session,
        consent_id,
        book_id=book_id,
        estimate_id=estimate_id,
        snapshot_id=snap.id,
    )
    if not real_provider_enabled():
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_REAL_PROVIDER_DISABLED,
            "真实模型分析尚未启用，请使用测试数据预览",
        )

    # Formal create: never fixture/fake fallback.
    from app.narrative_core.services.whole_book_gateway_transport_v1 import (
        resolve_formal_provider_row,
    )
    from app.narrative_core.services.whole_book_minimal_pipeline_v1_service import (
        build_formal_gateway_transports,
        execute_minimal_pipeline_v1,
    )

    resolve_formal_provider_row(session)  # fail-closed if provider/key unavailable
    request_id = client_request_id or str(uuid.uuid4())
    run = create_whole_book_run_v1(
        session,
        book_id,
        snap.id,
        WholeBookMode.whole_book_native.value,
        request_id,
        ResultOrigin.formal.value,
    )
    if run.consent_id is None:
        run.consent_id = consent_id
        session.flush()

    audit = assert_native_input_independence_v1(session, run.id)
    persist_native_input_audit_v1(session, audit)

    generate_whole_book_windows_v1(session, run.id)
    if run.status == WholeBookRunStatus.pending.value:
        start_whole_book_run_v1(session, run.id)
    session.refresh(run)

    pipeline_result: dict[str, Any] | None = None
    if execute_pipeline:
        transports = build_formal_gateway_transports(session)
        pipeline_result = execute_minimal_pipeline_v1(
            session, run.id, transports=transports
        )
        session.refresh(run)

    return {
        "run": run_to_dict(run),
        "run_id": run.id,
        "book_id": book_id,
        "snapshot_id": snap.id,
        "result_origin": ResultOrigin.formal.value,
        "run_status": run.status,
        "pipeline": pipeline_result,
        "audit": audit.to_dict(),
    }


def create_fixture_free_whole_book_analysis_v1(
    session: Session,
    book_id: int,
    *,
    client_request_id: str | None = None,
    execute_pipeline: bool = True,
) -> dict[str, Any]:
    _require_free_product_enabled()
    if not fixture_preview_enabled():
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_FIXTURE_PREVIEW_DISABLED,
            "测试数据预览尚未启用",
        )
    require_capability_access("whole_book.overview", AccessTier.free)
    require_capability_access("whole_book.characters_events", AccessTier.free)
    require_capability_access("whole_book.structure", AccessTier.free)
    require_capability_access("whole_book.chapter_functions", AccessTier.free)
    book = session.get(Book, book_id)
    if book is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_NOT_FOUND,
            "书籍不存在",
        )
    snap = create_or_reuse_book_snapshot_v1(session, book_id)["snapshot"]
    provider = session.scalar(select(ProviderConfiguration).limit(1))
    if provider is None:
        provider = ProviderConfiguration(provider_name="fixture", plus_model="fixture-model")
        session.add(provider)
        session.flush()
    estimate = estimate_whole_book_analysis(
        session, book_id, WholeBookMode.whole_book_native.value, provider.id
    )
    consent = create_whole_book_consent(
        session,
        book_id=book_id,
        estimate_id=estimate.id,
        user_budget_limit_cny="1000",
        max_provider_calls=500,
        max_input_tokens=10_000_000,
        max_output_tokens=10_000_000,
        auto_retry_enabled=False,
        max_retries_per_unit=0,
    )
    # Formal Create Run Consent Contract (keyword bindings only).
    validate_whole_book_consent(
        session,
        consent.id,
        book_id=book_id,
        estimate_id=estimate.id,
        snapshot_id=snap.id,
    )
    request_id = client_request_id or str(uuid.uuid4())
    run = create_whole_book_run_v1(
        session,
        book_id,
        snap.id,
        WholeBookMode.whole_book_native.value,
        request_id,
        ResultOrigin.fixture.value,
    )
    if run.consent_id is None:
        run.consent_id = consent.id
        session.flush()

    audit = assert_native_input_independence_v1(session, run.id)
    persist_native_input_audit_v1(session, audit)

    generate_whole_book_windows_v1(session, run.id)
    if run.status == WholeBookRunStatus.pending.value:
        start_whole_book_run_v1(session, run.id)
    session.refresh(run)

    pipeline_result: dict[str, Any] | None = None
    if execute_pipeline:
        pipeline_result = execute_fixture_minimal_pipeline_v1(session, run.id)
        session.refresh(run)

    return {
        "run": run_to_dict(run),
        "run_id": run.id,
        "book_id": book_id,
        "snapshot_id": snap.id,
        "result_origin": ResultOrigin.fixture.value,
        "run_status": run.status,
        "pipeline": pipeline_result,
        "audit": audit.to_dict(),
    }
