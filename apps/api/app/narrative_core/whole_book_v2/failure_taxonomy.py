"""CHG-085: Map Whole-Book V2 failures to accurate stages and user-safe messages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class FailureCategory(StrEnum):
    PROVIDER_NETWORK = "provider_network"
    SCHEMA_VALIDATION = "schema_validation"
    CONSOLIDATION = "consolidation"
    EVIDENCE_VALIDATION = "evidence_validation"
    PERSISTENCE = "persistence"
    BACKGROUND_RUNTIME = "background_runtime"
    UNKNOWN = "unknown"


UNIT_TO_FAILURE_STAGE: dict[str, str] = {
    "overview_type": "overview_synthesis",
    "story": "story_synthesis",
    "characters": "characters_synthesis",
    "suspense": "suspense_synthesis",
    "pacing": "pacing_synthesis",
    "assessment": "assessment_synthesis",
    "synthesis": "overview_synthesis",
}

TOPIC_TO_FAILURE_STAGE: dict[str, str] = {
    "story_intermediate": "story_consolidation",
    "character_intermediate": "character_consolidation",
    "relationship_intermediate": "relationship_consolidation",
    "protagonist_arc_intermediate": "protagonist_arc_consolidation",
    "suspense_intermediate": "suspense_consolidation",
    "pacing_intermediate": "pacing_consolidation",
    "chapter_function_intermediate": "chapter_function_consolidation",
}

CATEGORY_MESSAGES: dict[FailureCategory, str] = {
    FailureCategory.PROVIDER_NETWORK: "模型服务调用失败，请检查网络或 Provider 配置后重试。",
    FailureCategory.SCHEMA_VALIDATION: "模型中间结果格式不符合要求，可从已完成阶段继续。",
    FailureCategory.CONSOLIDATION: "窗口结果合并失败，可从已完成阶段继续。",
    FailureCategory.EVIDENCE_VALIDATION: "证据引用校验失败，请从失败阶段继续或重新分析。",
    FailureCategory.PERSISTENCE: "分析结果持久化失败，请稍后重试。",
    FailureCategory.BACKGROUND_RUNTIME: "全书分析后台执行失败，可重试。",
    FailureCategory.UNKNOWN: "全书分析失败，可重试。",
}

UNIT_SCHEMA_MESSAGES: dict[str, str] = {
    "overview_type": "全书总览生成失败：模型返回的数据结构不完整。",
    "story": "故事结构合成失败：模型中间结果格式不符合要求。",
    "characters": "人物关系合成失败：模型中间结果格式不符合要求。",
    "suspense": "悬念合成失败：模型中间结果格式不符合要求。",
    "pacing": "节奏与章节功能合成失败：模型中间结果格式不符合要求。",
    "assessment": "综合诊断合成失败：模型中间结果格式不符合要求。",
}


@dataclass(frozen=True)
class ClassifiedFailure:
    category: FailureCategory
    failure_code: str
    failure_stage: str
    message_safe: str
    unit_key: str | None = None


def failure_stage_for_unit_key(unit_key: str | None) -> str:
    if not unit_key:
        return "background_runtime"
    if unit_key.startswith("window:"):
        return "window_extraction"
    if unit_key.startswith("topic:"):
        topic = unit_key.split(":", 1)[-1]
        return TOPIC_TO_FAILURE_STAGE.get(topic, "story_consolidation")
    return UNIT_TO_FAILURE_STAGE.get(unit_key, "background_runtime")


def classify_pipeline_exception(exc: BaseException) -> ClassifiedFailure:
    """Classify the earliest actionable failure for UI / run.current_stage_code."""
    from app.narrative_core.whole_book_v2.provider_engine import (
        SynthesisUnitError,
        UnitFailureCode,
    )

    if isinstance(exc, SynthesisUnitError):
        unit = str(exc.unit_key or "")
        stage = failure_stage_for_unit_key(unit)
        code = str(getattr(exc, "code", "") or "")
        if code in {
            UnitFailureCode.EVIDENCE_REFERENCE_INVALID.value,
        }:
            category = FailureCategory.EVIDENCE_VALIDATION
            message = "证据引用校验失败：合成结果引用了未知证据。"
        elif code in {
            UnitFailureCode.CONTEXT_UNSAFE.value,
        }:
            category = FailureCategory.BACKGROUND_RUNTIME
            message = "上下文不安全：请求规模超出安全边界。"
        elif code in {
            UnitFailureCode.SCAFFOLD_FORBIDDEN.value,
        }:
            category = FailureCategory.SCHEMA_VALIDATION
            message = "禁止使用本地脚手架结果作为正式全书分析。"
        elif unit.startswith("topic:") or "consolidat" in stage:
            category = FailureCategory.CONSOLIDATION
            message = UNIT_SCHEMA_MESSAGES.get(unit, CATEGORY_MESSAGES[category])
        else:
            category = FailureCategory.SCHEMA_VALIDATION
            message = UNIT_SCHEMA_MESSAGES.get(
                unit.split(":", 1)[0] if unit else "",
                CATEGORY_MESSAGES[category],
            )
        failure_code = f"WHOLE_BOOK_V2_{code}" if code else "WHOLE_BOOK_V2_SCHEMA_VALIDATION"
        return ClassifiedFailure(
            category=category,
            failure_code=failure_code,
            failure_stage=stage,
            message_safe=message,
            unit_key=unit or None,
        )

    text = f"{type(exc).__name__}: {exc}".lower()
    if any(x in text for x in ("timeout", "connection", "apikey", "api key", "401", "403", "429", "provider")):
        return ClassifiedFailure(
            category=FailureCategory.PROVIDER_NETWORK,
            failure_code="WHOLE_BOOK_PROVIDER_NETWORK_FAILED",
            failure_stage="background_runtime",
            message_safe=CATEGORY_MESSAGES[FailureCategory.PROVIDER_NETWORK],
        )
    if any(x in text for x in ("validationerror", "schema", "missing", "json")):
        return ClassifiedFailure(
            category=FailureCategory.SCHEMA_VALIDATION,
            failure_code="WHOLE_BOOK_V2_SCHEMA_VALIDATION",
            failure_stage="overview_synthesis",
            message_safe=CATEGORY_MESSAGES[FailureCategory.SCHEMA_VALIDATION],
        )
    if any(x in text for x in ("database", "operationalerror", "locked", "integrity")):
        return ClassifiedFailure(
            category=FailureCategory.PERSISTENCE,
            failure_code="WHOLE_BOOK_PERSISTENCE_FAILED",
            failure_stage="background_runtime",
            message_safe=CATEGORY_MESSAGES[FailureCategory.PERSISTENCE],
        )
    return ClassifiedFailure(
        category=FailureCategory.BACKGROUND_RUNTIME,
        failure_code="WHOLE_BOOK_BACKGROUND_FAILED",
        failure_stage="background_runtime",
        message_safe=CATEGORY_MESSAGES[FailureCategory.BACKGROUND_RUNTIME],
    )


def inspect_resumable_checkpoints(session: Any, run_id: int) -> dict[str, Any]:
    """Read-only resume preflight for a failed hierarchical V2 run."""
    from sqlalchemy import select

    from app.db.models import WholeBookCheckpoint, WholeBookRun
    from app.narrative_core.whole_book_v2.repository import INTERMEDIATE_STAGE
    from app.narrative_core.whole_book_v2.window_extraction import (
        is_reusable_real_provider_intermediate,
    )
    import json

    run = session.get(WholeBookRun, int(run_id))
    if run is None:
        return {"compatible": False, "reason": "run_not_found"}
    if str(run.engine_id or "") != "whole_book_v2_hierarchical":
        return {"compatible": False, "reason": "engine_incompatible"}

    rows = list(
        session.scalars(
            select(WholeBookCheckpoint).where(
                WholeBookCheckpoint.run_id == int(run_id),
                WholeBookCheckpoint.stage_code == INTERMEDIATE_STAGE,
            )
        ).all()
    )
    windows: list[dict[str, Any]] = []
    topics = 0
    for row in rows:
        key = str(row.checkpoint_key or "")
        if key.startswith("topic:"):
            topics += 1
            continue
        if not key.startswith("window:"):
            continue
        try:
            data = json.loads(row.checkpoint_payload_json)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if not is_reusable_real_provider_intermediate(data):
            continue
        windows.append(
            {
                "window_id": data.get("window_id"),
                "origin": data.get("origin"),
                "status": "completed",
            }
        )

    progress_row = session.scalars(
        select(WholeBookCheckpoint).where(
            WholeBookCheckpoint.run_id == int(run_id),
            WholeBookCheckpoint.stage_code == "v2_progress",
            WholeBookCheckpoint.checkpoint_key == "latest",
        )
    ).first()
    progress: dict[str, Any] = {}
    if progress_row is not None:
        try:
            progress = json.loads(progress_row.checkpoint_payload_json)
        except json.JSONDecodeError:
            progress = {}

    completed = len(windows)
    total = int(progress.get("total_windows") or completed or 0)
    progress_windows = int(progress.get("current_window") or 0)
    windows_done = max(completed, progress_windows)
    calls_done = int(progress.get("provider_calls_completed") or completed)
    calls_est = int(progress.get("provider_calls_estimated") or 0)
    compatible = completed > 0 and str(run.status) == "failed"
    progress_stage = str(progress.get("current_stage") or "")
    run_stage = str(run.current_stage_code or "")
    stage_map = {
        "generate_overview": "overview_synthesis",
        "generate_assessment": "assessment_synthesis",
        "consolidate_story": "story_synthesis",
        "consolidate_characters": "characters_synthesis",
        "merge_suspense": "suspense_synthesis",
        "compute_pacing": "pacing_synthesis",
        "windowing": "window_extraction",
        "extract_windows": "window_extraction",
    }
    if windows_done > 0 and total > 0 and windows_done >= total:
        # Windows finished — do not advertise windowing as the resume target.
        candidate = progress_stage or run_stage or "overview_synthesis"
        next_stage = stage_map.get(candidate, candidate)
        if next_stage in {"windowing", "window_extraction", "extract_windows"}:
            next_stage = "overview_synthesis"
    else:
        next_stage = stage_map.get(
            run_stage or progress_stage, run_stage or progress_stage or "window_extraction"
        )
    return {
        "compatible": compatible,
        "run_id": int(run_id),
        "status": run.status,
        "completed_windows": completed,
        "total_windows": total or completed,
        "topic_intermediates": topics,
        "provider_calls_completed": calls_done,
        "provider_calls_estimated": calls_est,
        "next_stage": next_stage,
        "failure_code": run.failure_code,
        "failure_message_safe": run.failure_message_safe,
        "message": (
            f"已完成 {completed}/{total or completed} 个分析窗口，将从失败阶段继续，"
            "不会重复已成功的窗口调用。"
            if compatible
            else "当前失败任务没有可恢复的真实窗口检查点，需要重新分析。"
        ),
    }


__all__ = [
    "FailureCategory",
    "ClassifiedFailure",
    "classify_pipeline_exception",
    "failure_stage_for_unit_key",
    "inspect_resumable_checkpoints",
]
