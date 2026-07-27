"""Frozen Whole-Book Overview API error codes (STEP 2.1 / CHG-20260725-003).

Separate from NarrativeCoreErrorCode so Overview product errors stay additive
and carry HTTP / retry / UX metadata without rewriting Phase 1P codes.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, TypedDict


class WholeBookOverviewErrorCode(StrEnum):
    PRO_LICENSE_REQUIRED = "PRO_LICENSE_REQUIRED"
    BOOK_NOT_FOUND = "BOOK_NOT_FOUND"
    BOOK_CONTENT_EMPTY = "BOOK_CONTENT_EMPTY"
    BOOK_HAS_ACTIVE_TASK = "BOOK_HAS_ACTIVE_TASK"
    SNAPSHOT_INVALID = "SNAPSHOT_INVALID"
    SNAPSHOT_CONTENT_CHANGED = "SNAPSHOT_CONTENT_CHANGED"
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_OUTPUT_INVALID = "PROVIDER_OUTPUT_INVALID"
    PROVIDER_OUTPUT_EMPTY = "PROVIDER_OUTPUT_EMPTY"
    CITATION_INVALID = "CITATION_INVALID"
    EVIDENCE_INVALID = "EVIDENCE_INVALID"
    RUN_ALREADY_ACTIVE = "RUN_ALREADY_ACTIVE"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    RUN_NOT_RETRYABLE = "RUN_NOT_RETRYABLE"
    RUN_NOT_RESUMABLE = "RUN_NOT_RESUMABLE"
    RUN_ALREADY_COMPLETED = "RUN_ALREADY_COMPLETED"
    WINDOW_BUILD_FAILED = "WINDOW_BUILD_FAILED"
    WINDOW_EXECUTION_FAILED = "WINDOW_EXECUTION_FAILED"
    MATERIALIZATION_FAILED = "MATERIALIZATION_FAILED"
    PROJECTION_FAILED = "PROJECTION_FAILED"
    DATABASE_WRITE_FAILED = "DATABASE_WRITE_FAILED"
    COST_LIMIT_EXCEEDED = "COST_LIMIT_EXCEEDED"
    USER_CONSENT_REQUIRED = "USER_CONSENT_REQUIRED"
    PRIVATE_ENGINE_UNAVAILABLE = "PRIVATE_ENGINE_UNAVAILABLE"
    PRIVATE_ENGINE_INCOMPATIBLE = "PRIVATE_ENGINE_INCOMPATIBLE"


class OverviewErrorMeta(TypedDict):
    http_status: int
    retryable: bool
    user_message: str
    keep_run: bool
    allow_retry: bool
    requires_user_action: bool


WHOLE_BOOK_OVERVIEW_ERROR_META: dict[WholeBookOverviewErrorCode, OverviewErrorMeta] = {
    WholeBookOverviewErrorCode.PRO_LICENSE_REQUIRED: {
        "http_status": 403,
        "retryable": False,
        "user_message": "需要有效的 StoryLens Pro 授权才能创建原生全书概览。",
        "keep_run": False,
        "allow_retry": False,
        "requires_user_action": True,
    },
    WholeBookOverviewErrorCode.BOOK_NOT_FOUND: {
        "http_status": 404,
        "retryable": False,
        "user_message": "未找到指定书籍。",
        "keep_run": False,
        "allow_retry": False,
        "requires_user_action": True,
    },
    WholeBookOverviewErrorCode.BOOK_CONTENT_EMPTY: {
        "http_status": 422,
        "retryable": False,
        "user_message": "书籍没有可用于分析的正文段落。",
        "keep_run": False,
        "allow_retry": False,
        "requires_user_action": True,
    },
    WholeBookOverviewErrorCode.BOOK_HAS_ACTIVE_TASK: {
        "http_status": 409,
        "retryable": False,
        "user_message": "该书已有进行中的任务，请先完成或取消后再试。",
        "keep_run": True,
        "allow_retry": False,
        "requires_user_action": True,
    },
    WholeBookOverviewErrorCode.SNAPSHOT_INVALID: {
        "http_status": 409,
        "retryable": False,
        "user_message": "绑定的书籍快照无效，无法继续或恢复分析。",
        "keep_run": True,
        "allow_retry": False,
        "requires_user_action": True,
    },
    WholeBookOverviewErrorCode.SNAPSHOT_CONTENT_CHANGED: {
        "http_status": 409,
        "retryable": False,
        "user_message": "书籍正文相对快照已变化，请重新创建分析。",
        "keep_run": True,
        "allow_retry": False,
        "requires_user_action": True,
    },
    WholeBookOverviewErrorCode.PROVIDER_NOT_CONFIGURED: {
        "http_status": 422,
        "retryable": False,
        "user_message": "尚未配置可用的模型 Provider。",
        "keep_run": False,
        "allow_retry": False,
        "requires_user_action": True,
    },
    WholeBookOverviewErrorCode.PROVIDER_UNAVAILABLE: {
        "http_status": 503,
        "retryable": True,
        "user_message": "模型服务暂时不可用，请稍后重试。",
        "keep_run": True,
        "allow_retry": True,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.PROVIDER_TIMEOUT: {
        "http_status": 504,
        "retryable": True,
        "user_message": "模型调用超时，可重试未完成窗口。",
        "keep_run": True,
        "allow_retry": True,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.PROVIDER_RATE_LIMITED: {
        "http_status": 429,
        "retryable": True,
        "user_message": "模型调用触发限流，请稍后重试。",
        "keep_run": True,
        "allow_retry": True,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.PROVIDER_OUTPUT_INVALID: {
        "http_status": 422,
        "retryable": True,
        "user_message": "模型返回的分析结果格式不符合要求，任务未完成。",
        "keep_run": True,
        "allow_retry": True,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.PROVIDER_OUTPUT_EMPTY: {
        "http_status": 422,
        "retryable": True,
        "user_message": "模型返回空结果，可重试该窗口。",
        "keep_run": True,
        "allow_retry": True,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.CITATION_INVALID: {
        "http_status": 422,
        "retryable": True,
        "user_message": "引用定位无效，系统可尝试修复或重试。",
        "keep_run": True,
        "allow_retry": True,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.EVIDENCE_INVALID: {
        "http_status": 422,
        "retryable": True,
        "user_message": "证据未通过校验，不会写入正式资产。",
        "keep_run": True,
        "allow_retry": True,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.RUN_ALREADY_ACTIVE: {
        "http_status": 409,
        "retryable": False,
        "user_message": "已有进行中的全书概览任务。",
        "keep_run": True,
        "allow_retry": False,
        "requires_user_action": True,
    },
    WholeBookOverviewErrorCode.RUN_NOT_FOUND: {
        "http_status": 404,
        "retryable": False,
        "user_message": "未找到指定的全书概览任务。",
        "keep_run": False,
        "allow_retry": False,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.RUN_NOT_RETRYABLE: {
        "http_status": 409,
        "retryable": False,
        "user_message": "当前任务状态不允许重试。",
        "keep_run": True,
        "allow_retry": False,
        "requires_user_action": True,
    },
    WholeBookOverviewErrorCode.RUN_NOT_RESUMABLE: {
        "http_status": 409,
        "retryable": False,
        "user_message": "当前任务状态不允许恢复。",
        "keep_run": True,
        "allow_retry": False,
        "requires_user_action": True,
    },
    WholeBookOverviewErrorCode.RUN_ALREADY_COMPLETED: {
        "http_status": 409,
        "retryable": False,
        "user_message": "任务已完成，请直接查看结果或创建新任务。",
        "keep_run": True,
        "allow_retry": False,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.WINDOW_BUILD_FAILED: {
        "http_status": 500,
        "retryable": True,
        "user_message": "跨章节窗口构建失败。",
        "keep_run": True,
        "allow_retry": True,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.WINDOW_EXECUTION_FAILED: {
        "http_status": 500,
        "retryable": True,
        "user_message": "窗口分析执行失败，可重试未完成窗口。",
        "keep_run": True,
        "allow_retry": True,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.MATERIALIZATION_FAILED: {
        "http_status": 500,
        "retryable": True,
        "user_message": "候选资产落库失败。",
        "keep_run": True,
        "allow_retry": True,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.PROJECTION_FAILED: {
        "http_status": 500,
        "retryable": True,
        "user_message": "全书概览投影生成失败。",
        "keep_run": True,
        "allow_retry": True,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.DATABASE_WRITE_FAILED: {
        "http_status": 500,
        "retryable": True,
        "user_message": "数据库写入失败，请稍后重试。",
        "keep_run": True,
        "allow_retry": True,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.COST_LIMIT_EXCEEDED: {
        "http_status": 402,
        "retryable": False,
        "user_message": "已超出费用或配额上限。",
        "keep_run": True,
        "allow_retry": False,
        "requires_user_action": True,
    },
    WholeBookOverviewErrorCode.USER_CONSENT_REQUIRED: {
        "http_status": 422,
        "retryable": False,
        "user_message": "请先确认预估费用后再创建分析。",
        "keep_run": False,
        "allow_retry": False,
        "requires_user_action": True,
    },
    WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE: {
        "http_status": 503,
        "retryable": True,
        "user_message": "私有引擎暂时不可用。",
        "keep_run": True,
        "allow_retry": True,
        "requires_user_action": False,
    },
    WholeBookOverviewErrorCode.PRIVATE_ENGINE_INCOMPATIBLE: {
        "http_status": 409,
        "retryable": False,
        "user_message": "私有引擎版本与当前契约不兼容。",
        "keep_run": True,
        "allow_retry": False,
        "requires_user_action": True,
    },
}


def overview_error_meta(code: WholeBookOverviewErrorCode | str) -> OverviewErrorMeta:
    key = WholeBookOverviewErrorCode(code)
    return WHOLE_BOOK_OVERVIEW_ERROR_META[key]


def overview_error_payload(
    code: WholeBookOverviewErrorCode | str,
    *,
    message: str | None = None,
    details: dict[str, Any] | None = None,
    run_id: str | None = None,
    stage_key: str | None = None,
    window_index: int | None = None,
) -> dict[str, Any]:
    """Build the frozen unified ErrorEnvelope body."""
    key = WholeBookOverviewErrorCode(code)
    meta = WHOLE_BOOK_OVERVIEW_ERROR_META[key]
    return {
        "error": {
            "code": key.value,
            "message": message or meta["user_message"],
            "retryable": meta["retryable"],
            "details": details or {},
            "run_id": run_id,
            "stage_key": stage_key,
            "window_index": window_index,
        }
    }
