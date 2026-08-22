"""Free whole-book product coordination (WB-1.7 backend slice)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import utc_now
from app.db.models import Book, ProviderConfiguration, WholeBookRun
from app.narrative_core.contracts.whole_book_contract_v1 import ResultOrigin, WholeBookMode, WholeBookRunStatus
from app.narrative_core.services.whole_book_consent_service import create_whole_book_consent, validate_whole_book_consent
from app.narrative_core.services.whole_book_cost_estimate_service import (
    compute_book_revision_hash,
    estimate_whole_book_analysis,
)
from app.narrative_core.services.whole_book_hierarchical_estimate_v1 import (
    estimate_hierarchical_whole_book_analysis_v1,
    hierarchical_estimate_to_dict,
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
from app.narrative_core.services.whole_book_start_limits_v1 import suggest_limits_from_estimate
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


#: 一次付费调用最长能跑多久还算「活着」。抽取一块约 70 秒，加上重试和网络抖动，
#: 15 分钟没有任何进度写入，这个任务就不该再挡着别人。
LIVE_RUN_STALE_AFTER = timedelta(minutes=15)


def live_run_for_book(
    session: Session, book_id: int, *, now: datetime | None = None
) -> WholeBookRun | None:
    """这本书上真正在跑的那个任务；杵住的不算。

    今天同一本书两次起了两个任务：《我不是戏神》相差 10 秒，《余罪》相差 14 秒。多出来的那个
    做完一两次调用就杵住，而页面挑任务挑的是「最新的那个」——于是屏幕盯着空壳，真正在跑的那
    个反倒看不见，用户看到的是「卡在 4%」和「无法读取数据」。

    幂等键防不住这件事：它的输入里有 client_request_id，每次点击都是新的，所以它防的是「同一
    个请求重试」，不是「点了两次」。

    「活着」以 last_heartbeat_at 为准——那是最后一次真的完成付费调用的时刻，不是任务创建时刻。
    用创建时刻判活，1299 章跑三小时的任务会被误判成僵尸；用心跳判，跑得再久也认得出来。
    没有心跳的（刚创建、还没写出第一条进度）给一个同样的宽限期，用 started_at 兜底。
    """
    current = now or utc_now()
    for run in list_runs_for_book(session, book_id):
        if run.status not in {
            WholeBookRunStatus.pending.value,
            WholeBookRunStatus.running.value,
        }:
            continue
        beat = run.last_heartbeat_at or run.started_at or run.created_at
        if beat is None:
            return run
        if beat.tzinfo is None:
            beat = beat.replace(tzinfo=timezone.utc)
        if current - beat <= LIVE_RUN_STALE_AFTER:
            return run
    return None


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


def _completed_v2_run(session: Session, book_id: int) -> WholeBookRun | None:
    """Latest completed run with a real_provider V2 result (scaffold is NON_REAL)."""
    from app.narrative_core.whole_book_v2.repository import WholeBookV2Repository
    from app.narrative_core.whole_book_v2.result_origin import product_flags_for_result

    repo = WholeBookV2Repository(session)
    for run in list_runs_for_book(session, book_id):
        if run.status != WholeBookRunStatus.completed.value:
            continue
        result = repo.load_result(int(run.id))
        if result is None:
            continue
        flags = product_flags_for_result(result)
        if flags.get("is_real_provider_result"):
            return run
    return None


BREAKDOWN_ENGINE_SUFFIX = "+story_breakdown"


def reading_of_run(run: WholeBookRun) -> str:
    """Which reading produced this run: "story_breakdown" or "diagnostic".

    The pipeline stamps the reading onto ``engine_version`` (``…-1.0+story_breakdown``)
    because the runs table has no column for it. Reading it back here keeps that decision in
    one place rather than spreading string surgery through the API.
    """
    version = str(getattr(run, "engine_version", "") or "")
    return "story_breakdown" if version.endswith(BREAKDOWN_ENGINE_SUFFIX) else "diagnostic"


def _completed_v2_runs_by_reading(session: Session, book_id: int) -> dict[str, WholeBookRun]:
    """The newest real completed run of each reading.

    A book can hold both a 评测 and a 拆文 — they answer different questions and neither
    replaces the other. The page could only ever reach the newest one, so running the second
    reading made the first unreachable: the analysis was paid for, stored, and invisible.
    """
    from app.narrative_core.whole_book_v2.repository import WholeBookV2Repository
    from app.narrative_core.whole_book_v2.result_origin import product_flags_for_result

    repo = WholeBookV2Repository(session)
    newest: dict[str, WholeBookRun] = {}
    for run in list_runs_for_book(session, book_id):
        if run.status != WholeBookRunStatus.completed.value:
            continue
        reading = reading_of_run(run)
        if reading in newest:
            continue
        result = repo.load_result(int(run.id))
        if result is None:
            continue
        if product_flags_for_result(result).get("is_real_provider_result"):
            newest[reading] = run
    return newest


def _latest_failed_run(session: Session, book_id: int) -> WholeBookRun | None:
    for run in list_runs_for_book(session, book_id):
        if run.status == WholeBookRunStatus.failed.value:
            return run
    return None


def _non_real_completed_v2_run(session: Session, book_id: int) -> WholeBookRun | None:
    """Scaffold/legacy completed rows — visible as old result, never as formal completed."""
    from app.narrative_core.whole_book_v2.repository import WholeBookV2Repository
    from app.narrative_core.whole_book_v2.result_origin import product_flags_for_result

    repo = WholeBookV2Repository(session)
    for run in list_runs_for_book(session, book_id):
        if run.status != WholeBookRunStatus.completed.value:
            continue
        result = repo.load_result(int(run.id))
        if result is None:
            continue
        flags = product_flags_for_result(result)
        if not flags.get("is_real_provider_result"):
            return run
    return None


def prepare_free_whole_book_analysis_v1(
    session: Session, book_id: int, *, analysis_mode: str = "diagnostic"
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
    revision_hash = compute_book_revision_hash(session, book_id)
    provider = None
    active_name = "default"
    blockers: list[str] = []
    provider_available = False
    if real_provider_enabled():
        from app.narrative_core.services.whole_book_active_provider_v1 import (
            active_provider_availability,
        )

        provider, active_name, blockers = active_provider_availability(session)
        provider_available = provider is not None and not blockers
        # Never invent / substitute another formal provider for estimate identity.
        if provider is None:
            # Soft shell: still need a row for estimate display when bootstrap created one.
            from app.narrative_core.services.whole_book_active_provider_v1 import (
                ensure_active_provider_row,
            )

            provider = ensure_active_provider_row(session, active_name)
    if provider is None and not real_provider_enabled():
        # Reuse the placeholder row if one is already there. `provider_name` is unique, so
        # inserting unconditionally raises IntegrityError the second time this shell path is
        # reached for the same database — which is what a prepare call after any other call
        # that created it does.
        provider = (
            session.query(ProviderConfiguration)
            .filter(ProviderConfiguration.provider_name == "default")
            .one_or_none()
        )
        if provider is None:
            provider = ProviderConfiguration(
                provider_name="default",
                plus_model="default-model",
                enabled=False,
                disconnected=True,
            )
            session.add(provider)
            session.flush()
    if provider is None:
        # Real path with missing active row — fail closed for create; estimate shell blocked.
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_REAL_PROVIDER_DISABLED,
            f"当前服务商 {active_name} 尚未配置，无法准备全书分析",
        )
    # CHG-081: formal V2 start + reanalysis share Hierarchical planners (not legacy Free).
    try:
        estimate, hier_plan = estimate_hierarchical_whole_book_analysis_v1(
            session,
            book_id,
            WholeBookMode.whole_book_native.value,
            provider.id,
            provider_name=str(provider.provider_name or ""),
        )
    except ValueError as exc:
        # The planner fails closed on a chapter too big for one window, with a bare ValueError.
        # Left alone it became a 500, and the workspace reported it as the local service being
        # unavailable — which sends the reader to restart something that is running fine. The
        # real cause is upstream of the analysis entirely: the chapters were never split.
        if "single chapter exceeds safe context capacity" not in str(exc):
            raise
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_CHAPTER_TOO_LARGE,
            "这本书有单独一章超出了一次分析能读的长度，通常是章节没有被正确切分。"
            "请用「重新识别章节」检查分章，或换一个能识别章号的文件重新导入。",
            details={"planner_message": str(exc)},
        ) from exc
    latest = _latest_run_for_book(session, book_id)
    recoverable = _recoverable_run(session, book_id)
    live_now = live_run_for_book(session, book_id)
    snap_result = create_or_reuse_book_snapshot_v1(session, book_id)
    needs_new_snapshot = (
        latest is not None
        and latest.snapshot_id is not None
        and snap_result["reused"] is False
    )
    est = hierarchical_estimate_to_dict(estimate)
    real_on = real_provider_enabled()
    fixture_on = fixture_preview_enabled()
    run_creation_enabled = bool(real_on and provider_available)
    active_run = recoverable
    completed_v2 = _completed_v2_run(session, book_id)
    latest_failed = _latest_failed_run(session, book_id)
    non_real_completed = _non_real_completed_v2_run(session, book_id)
    model_name = str(est.get("model_name") or provider.plus_model or "")
    context_safe = bool(hier_plan.get("context_safe", True))
    # Which engine this book will actually get, and therefore which plan the panel should
    # describe. The estimate below priced the hierarchical planner's windows even for books
    # dispatched to the long-novel engine — the token total was close, because both engines
    # read the book once, but the call and window counts a user reads to judge duration were
    # out by roughly 4x.
    from app.narrative_core.services.long_novel_pipeline_v1 import (
        book_uses_long_novel_engine,
        estimate_long_novel_plan,
    )

    long_novel = book_uses_long_novel_engine(session, book_id)
    planner = "long_novel_engine" if long_novel else "hierarchical_v2"
    ln_plan = (
        estimate_long_novel_plan(
            chapter_count=int(est.get("chapter_count") or 0),
            character_count=int(est.get("character_count") or 0),
            mode=analysis_mode,
        )
        if long_novel
        else {}
    )

    def _ln_costs() -> "tuple[float | None, float | None]":
        """Price the long-novel token counts with the estimator's own pricing function.

        Scaling the hierarchical *total* by a token ratio was tried first and left a 7–8%
        error: the two engines have different input-to-output mixes, and input and output are
        not priced the same, so one multiplier cannot carry both. Calling the same pricing
        function with the right split keeps a single source of truth for rates while fixing
        the part that was actually wrong.
        """
        from app.narrative_core.services.whole_book_cost_estimate_service import (
            estimate_pre_run_cost_cny,
        )

        tokens_in = ln_plan.get("estimated_input_tokens")
        tokens_out = ln_plan.get("estimated_output_tokens")
        if not tokens_in or not tokens_out or not model_name:
            return est.get("estimated_cost_min_cny"), est.get("estimated_cost_max_cny")
        # Same ±band the estimator applies to output, which is the term that actually varies.
        low, high, failed = estimate_pre_run_cost_cny(
            model_name,
            estimated_input_tokens=int(tokens_in),
            estimated_output_tokens_min=int(round(tokens_out * 0.85)),
            estimated_output_tokens_max=int(round(tokens_out * 1.25)),
        )
        if failed or low is None or high is None:
            return est.get("estimated_cost_min_cny"), est.get("estimated_cost_max_cny")
        return round(float(low), 6), round(float(high), 6)

    _ln_cost_min, _ln_cost_max = (
        _ln_costs() if long_novel
        else (est.get("estimated_cost_min_cny"), est.get("estimated_cost_max_cny"))
    )
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
        "run_creation_enabled": run_creation_enabled,
        "active_provider_name": provider.provider_name,
        "active_model_name": model_name,
        "provider_available": provider_available,
        "fixture_preview_enabled": fixture_on,
        "latest_run": run_to_dict(latest) if latest is not None else None,
        "recoverable_run": run_to_dict(recoverable) if recoverable is not None else None,
        "active_run": run_to_dict(active_run) if active_run is not None else None,
        # 哪个任务真的还在跑 —— 由后端判，客户端照着渲染（INV-P4）。
        #
        # 以前客户端自己挑：active_run 空了就看 latest_run，再空看 recoverable_run，只要状态
        # 是 running/paused/recoverable 就当成「正在进行」。于是一个进程早已消失、状态还停在
        # running 的空壳，会把这本书的开始按钮永久堵住——今天《余罪》就是这样，我只能用取消
        # 接口手工解开。
        #
        # 判活以心跳为准（最后一次真的完成付费调用的时刻），所以跑三小时的大书不会被误判。
        "live_run_id": int(live_now.id) if live_now is not None else None,
        "completed_v2_run": run_to_dict(completed_v2) if completed_v2 is not None else None,
        # Both readings, newest of each, so the client can offer the other one instead of
        # silently hiding it behind the most recent run.
        "completed_v2_runs_by_reading": {
            reading: run_to_dict(run)
            for reading, run in _completed_v2_runs_by_reading(session, book_id).items()
        },
        "latest_failed_run": run_to_dict(latest_failed) if latest_failed is not None else None,
        "non_real_completed_v2_run": (
            run_to_dict(non_real_completed) if non_real_completed is not None else None
        ),
        "latest_run_id": latest.id if latest else None,
        "latest_run_status": latest.status if latest else None,
        "recoverable_run_id": recoverable.id if recoverable else None,
        "needs_new_snapshot": needs_new_snapshot,
        "snapshot_rebuild_required": needs_new_snapshot,
        "context_safe": context_safe,
        "planner": planner,
        "snapshot": {
            "snapshot_id": snap_result["snapshot"].id,
            "reused": snap_result["reused"],
        },
        "estimate": {
            "estimate_id": est["id"],
            "book_id": est["book_id"],
            "mode": est["mode"],
            "estimated_windows": ln_plan.get("blocks", est.get("estimated_window_count")),
            "estimated_provider_calls": ln_plan.get(
                "estimated_provider_calls", est.get("estimated_provider_call_count")
            ),
            "estimated_input_tokens": ln_plan.get(
                "estimated_input_tokens", est.get("estimated_input_tokens")
            ),
            "estimated_output_tokens": ln_plan.get(
                "estimated_output_tokens", est.get("estimated_output_tokens")
            ),
            "estimated_cost_min_cny": _ln_cost_min,
            "estimated_cost_max_cny": _ln_cost_max,
            "call_breakdown": est.get("call_breakdown"),
            "provider_name": provider.provider_name,
            "provider_config_id": provider.id,
            "model_name": est.get("model_name"),
            "price_known": str(est.get("pricing_status") or "") == "available",
            "currency": est.get("currency") or "CNY",
            "estimate_version": est.get("estimate_version"),
            "planner": planner,
        },
        "recommended_limits": suggest_limits_from_estimate(estimate),
        "blocking_reasons": blockers,
        "warnings": [],
        "resumable_checkpoint": _resumable_checkpoint_payload(session, latest_failed),
    }


def _resumable_checkpoint_payload(
    session: Session, failed: WholeBookRun | None
) -> dict[str, Any] | None:
    if failed is None:
        return None
    from app.narrative_core.whole_book_v2.failure_taxonomy import inspect_resumable_checkpoints

    info = inspect_resumable_checkpoints(session, int(failed.id))
    if not info.get("compatible"):
        return {
            **info,
            "can_resume": False,
        }
    return {
        **info,
        "can_resume": True,
    }


def resume_failed_free_whole_book_analysis_v1(
    session: Session,
    book_id: int,
    *,
    run_id: int,
) -> dict[str, Any]:
    """Resume a failed hierarchical V2 run from persisted same-run checkpoints (CHG-085).

    Does not create a new run. Does not re-execute completed real_provider windows.
    Force-full semantics do not apply to same-run resume.
    """
    _require_free_product_enabled()
    require_capability_access("whole_book.overview", AccessTier.free)
    if not real_provider_enabled():
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_REAL_PROVIDER_DISABLED,
            "真实模型分析尚未启用",
        )
    run = session.get(WholeBookRun, int(run_id))
    if run is None or int(run.book_id) != int(book_id):
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_NOT_FOUND,
            "分析任务不存在",
        )
    if run.status != WholeBookRunStatus.failed.value:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
            f"仅失败任务可继续分析，当前状态为 {run.status}",
        )
    from app.db.models import utc_now
    from app.narrative_core.whole_book_v2.failure_taxonomy import inspect_resumable_checkpoints

    info = inspect_resumable_checkpoints(session, int(run_id))
    if not info.get("compatible"):
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
            str(info.get("message") or "当前失败任务没有可恢复检查点，请重新分析"),
        )

    run.status = WholeBookRunStatus.running.value
    run.failure_code = None
    run.failure_message_safe = None
    run.resume_count = int(run.resume_count or 0) + 1
    run.resumed_at = utc_now()
    # Prefer next stage from checkpoint inspection (not stale windowing).
    run.current_stage_code = str(info.get("next_stage") or run.current_stage_code or "overview_synthesis")
    session.flush()
    from app.narrative_core.whole_book_v2.usage_ledger import ensure_task_projection

    ensure_task_projection(session, run)
    return {
        "run": run_to_dict(run),
        "run_id": int(run.id),
        "book_id": int(book_id),
        "resumed": True,
        "force_full_reanalysis": False,
        "previous_run_id": None,
        "resumable_checkpoint": info,
        "deferred_execution": True,
        "provider_config_id": None,
    }


def create_free_whole_book_analysis_v1(
    session: Session,
    book_id: int,
    *,
    estimate_id: int,
    consent_id: int,
    client_request_id: str,
    execute_pipeline: bool = True,
    defer_execution: bool = False,
    reanalyse: bool = False,
    force_full_reanalysis: bool = False,
    previous_run_id: int | None = None,
) -> dict[str, Any]:
    _require_free_product_enabled()
    # 这本书已经有一个真在跑的任务，就把它交回去，不再建第二个。
    #
    # 今天两次都栽在这里：《我不是戏神》相差 10 秒起了两个，《余罪》相差 14 秒起了两个。多出
    # 来的那个做完一两次调用就杵住，而页面挑的是「最新的那个」——屏幕上的「卡在 4%」和
    # 「无法读取数据」，都是它在盯一个空壳。
    #
    # 幂等键拦不住这件事：它的输入里含 client_request_id，每次点击都是新的，所以它防的是
    # 「同一个请求重试」，不是「点了两次」。
    #
    # 判活用心跳而不是创建时刻：跑三小时的大书不会被误判成僵尸，心跳停了 15 分钟的任务也不会
    # 把这本书永久锁死——那是反方向的同一个坑。
    live = live_run_for_book(session, book_id)
    if live is not None:
        return {
            "run": run_to_dict(live),
            "run_id": int(live.id),
            "book_id": book_id,
            "snapshot_id": int(live.snapshot_id or 0),
            "run_status": live.status,
            "reused_live_run": True,
            "deferred_execution": False,
            "message": "这本书已经有一个分析在进行中，已为你切换到那个任务。",
        }
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

    # Formal create: never fixture/fake fallback. CHG-078 → hierarchical V2.
    from app.db.models import WholeBookConsent, WholeBookCostEstimate
    from app.narrative_core.services.whole_book_gateway_transport_v1 import (
        resolve_formal_provider_row,
    )
    from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
        ENGINE_ID as V2_ENGINE_ID,
        ENGINE_VERSION as V2_ENGINE_VERSION,
        execute_hierarchical_v2_pipeline_v1,
    )

    consent = session.get(WholeBookConsent, consent_id)
    estimate_row = session.get(WholeBookCostEstimate, estimate_id)
    provider_config_id = None
    if consent is not None and consent.provider_config_id:
        provider_config_id = int(consent.provider_config_id)
    elif estimate_row is not None and estimate_row.provider_config_id:
        provider_config_id = int(estimate_row.provider_config_id)
    provider_row = resolve_formal_provider_row(
        session, provider_config_id=provider_config_id
    )  # fail-closed if provider/key unavailable
    from app.services.provider_runtime import get_active_cloud_provider

    active = get_active_cloud_provider(session)
    if provider_row.provider_name != active:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_ESTIMATE_EXPIRED,
            f"费用预估绑定的服务商为 {provider_row.provider_name}，与当前选择 {active} 不一致，请重新准备全书分析",
        )
    if (
        estimate_row is not None
        and int(estimate_row.provider_config_id) != int(provider_row.id)
    ):
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_ESTIMATE_EXPIRED,
            "费用预估与当前 Provider 配置不一致，请重新准备全书分析",
        )
    pinned_model = (
        (estimate_row.model_name if estimate_row is not None else None)
        or provider_row.plus_model
        or ""
    ).strip()
    request_id = client_request_id or str(uuid.uuid4())
    if reanalyse and previous_run_id is None:
        # CHG-086: a failed run still holds paid real-provider window extractions.
        # Only completed runs used to be considered, so every retry after a
        # mid-pipeline failure silently re-bought all windows.
        prev = (
            _completed_v2_run(session, book_id)
            or _latest_failed_run(session, book_id)
            or _non_real_completed_v2_run(session, book_id)
        )
        previous_run_id = int(prev.id) if prev is not None else None

    run = create_whole_book_run_v1(
        session,
        book_id,
        snap.id,
        WholeBookMode.whole_book_native.value,
        request_id,
        ResultOrigin.formal.value,
    )
    if reanalyse:
        if previous_run_id is not None and int(run.id) == int(previous_run_id):
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
                "重新分析必须创建新的 V2 任务，不能复用已完成结果",
            )
        if run.status == WholeBookRunStatus.completed.value:
            # Same client_request_id replay of a prior success — still not a fresh reanalysis.
            from app.narrative_core.whole_book_v2.repository import WholeBookV2Repository

            if WholeBookV2Repository(session).has_result(int(run.id)):
                raise WholeBookFoundationError(
                    WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
                    "重新分析请求与已完成任务冲突，请使用新的请求标识重试",
                )
    if run.consent_id is None:
        run.consent_id = consent_id
    # Pin at create — resume/transports must use these, not current settings.
    if not (run.provider_name or "").strip():
        run.provider_name = provider_row.provider_name
    if not (run.model_name or "").strip():
        run.model_name = pinned_model
    # Formal V1.2.0 product engine pin (CHG-078).
    run.engine_id = V2_ENGINE_ID
    run.engine_version = V2_ENGINE_VERSION
    session.flush()

    # CHG-084: Task Center projection + usage ledger bridge (AnalysisRun).
    from app.narrative_core.whole_book_v2.usage_ledger import ensure_task_projection

    ensure_task_projection(session, run)

    audit = assert_native_input_independence_v1(session, run.id)
    persist_native_input_audit_v1(session, audit)

    # CHG-081: Hierarchical V2 owns window planning inside the background executor.
    # Do NOT call legacy generate_whole_book_windows_v1 here — it loads every
    # snapshot paragraph text synchronously on create and can stall/OOM the
    # packaged sidecar on large books (e.g. 542 chapters / ~2.9M chars).
    # Mark running so prepare/progress can observe the run immediately after commit.
    if run.status == WholeBookRunStatus.pending.value:
        start_whole_book_run_v1(session, run.id)
    session.refresh(run)

    pipeline_result: dict[str, Any] | None = None
    # HTTP create must return before Provider work (CHG-077). Background task runs pipeline.
    if execute_pipeline and not defer_execution:
        pipeline_result = execute_hierarchical_v2_pipeline_v1(
            session,
            run.id,
            force_full_reanalysis=bool(force_full_reanalysis),
            previous_run_id=int(previous_run_id) if previous_run_id else None,
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
        "deferred_execution": bool(defer_execution and execute_pipeline),
        "provider_config_id": provider_config_id,
        "audit": audit.to_dict(),
        "reanalyse": bool(reanalyse),
        "force_full_reanalysis": bool(force_full_reanalysis),
        "previous_run_id": int(previous_run_id) if previous_run_id else None,
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

    from app.narrative_core.services.whole_book_windowing_v1_service import (
        generate_whole_book_windows_v1,
    )

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
