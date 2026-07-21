"""User-facing copy for AI setup / eligibility / budget blockers.

Technical codes stay available for diagnostics; ordinary UI uses these labels.
"""

from __future__ import annotations

# Primary short labels shown near Next / status cards.
BLOCKER_LABELS: dict[str, str] = {
    "credential_missing": "尚未填写 API Key",
    "CREDENTIAL_MISSING": "尚未保存 API Key",
    "credential_store_unavailable": "本机凭据保险柜不可用",
    "CREDENTIAL_STORE_UNAVAILABLE": "本机凭据保险柜不可用",
    "CREDENTIAL_INVALID": "API Key 无效或已失效",
    "AUTHENTICATION_FAILED": "API Key 无效或已失效",
    "PROVIDER_AUTHENTICATION_FAILED": "API Key 无效或已失效",
    "provider_disabled": "模型服务尚未启用",
    "PROVIDER_DISABLED": "模型服务尚未启用",
    "provider_not_configured": "模型服务尚未完成配置",
    "PROVIDER_NOT_CONFIGURED": "模型服务尚未完成配置",
    "provider_disconnected": "模型服务尚未连接",
    "PROVIDER_NOT_CONNECTED": "模型服务尚未连接",
    "cloud_master_switch_off": "云端模型服务尚未开启",
    "CLOUD_MASTER_SWITCH_OFF": "云端模型服务尚未开启",
    "CLOUD_DISABLED": "云端模型服务尚未开启",
    "pricing_unavailable": "当前模型缺少计价配置",
    "MODEL_PRICING_NOT_FOUND": "当前模型缺少计价信息",
    "BUDGET_NOT_AVAILABLE": "当前无法计算本次分析费用",
    "budget_unavailable": "每日预算不足",
    "INSUFFICIENT_BUDGET_RESERVATION": "无法为本次分析预留预算",
    "boundary_candidates_not_supported": "当前模型不支持场景分析",
    "provider_unhealthy": "模型服务暂时不可用",
    "provider_health_stale": "模型服务健康状态已过期",
    "MODEL_NOT_AVAILABLE": "当前模型不可用",
    "MODEL_NOT_FOUND": "当前模型不可用",
    "PROVIDER_MODEL_NOT_FOUND": "当前模型不可用",
    "cloud_consent_required": "请先确认正文发送说明",
    "CLOUD_CONSENT_REQUIRED": "请先确认正文发送说明",
    "connection_test_failed": "模型服务验证失败",
    "SETUP_INCOMPLETE": "分析配置尚未完成",
    "API_KEY_NOT_SAVED": "API Key 尚未保存",
    "RATE_LIMITED": "模型请求受到服务商限流",
    "rate_limited": "模型请求受到服务商限流",
    "PROVIDER_RATE_LIMITED": "模型请求受到服务商限流",
}

# Longer guidance for status cards / expandable help.
BLOCKER_GUIDANCE: dict[str, str] = {
    "BUDGET_NOT_AVAILABLE": (
        "StoryLens 暂时无法计算本次分析费用，因此无法为任务预留预算。\n"
        "处理方式：检查模型映射和计价配置，或切换到已有计价信息的模型。"
    ),
    "MODEL_PRICING_NOT_FOUND": (
        "StoryLens 暂时无法计算当前模型的分析费用，因此无法为任务预留预算。\n"
        "处理方式：检查模型映射和计价配置，或切换到已有计价信息的模型。"
    ),
    "pricing_unavailable": (
        "StoryLens 暂时无法计算当前模型的分析费用，因此无法为任务预留预算。\n"
        "处理方式：检查模型映射和计价配置，或切换到已有计价信息的模型。"
    ),
    "INSUFFICIENT_BUDGET_RESERVATION": (
        "当前预算不足以完成本次分析预留。\n"
        "处理方式：提高每日预算，或等待今日用量重置后再试。"
    ),
    "budget_unavailable": (
        "当前剩余预算不足以开始分析。\n"
        "处理方式：提高每日预算，或等待今日用量重置后再试。"
    ),
    "CREDENTIAL_MISSING": (
        "尚未保存 API Key。\n"
        "处理方式：填写 API Key 后点击“验证并保存”。"
    ),
    "credential_missing": (
        "尚未填写 API Key。\n"
        "处理方式：填写 API Key 后验证模型服务。"
    ),
    "CREDENTIAL_INVALID": (
        "API Key 无效或已失效。\n"
        "处理方式：在模型服务商控制台核对 Key 后重新验证并保存。"
    ),
    "CLOUD_DISABLED": (
        "云端模型服务尚未开启。\n"
        "处理方式：在 AI 服务设置中开启云端分析。"
    ),
    "cloud_master_switch_off": (
        "云端模型服务尚未开启。\n"
        "处理方式：确认正文发送说明并保存配置。"
    ),
    "MODEL_NOT_AVAILABLE": (
        "当前模型不可用。\n"
        "处理方式：切换分析模式或核对模型名称后重试。"
    ),
    "RATE_LIMITED": (
        "模型请求受到服务商限流（HTTP 429，error_category=rate_limited，retryable=true）。\n"
        "处理方式：稍后重试。此错误不表示云端开关或 Provider 未启用。"
    ),
    "rate_limited": (
        "模型请求受到服务商限流（HTTP 429，error_category=rate_limited，retryable=true）。\n"
        "处理方式：稍后重试。此错误不表示云端开关或 Provider 未启用。"
    ),
}


def blocker_label(code: str | None) -> str:
    if not code:
        return "分析配置尚未完成"
    return BLOCKER_LABELS.get(code, BLOCKER_LABELS.get(code.lower(), "分析配置尚未完成"))


def blocker_guidance(code: str | None, *, model: str | None = None) -> str:
    if not code:
        return "请完成 AI 服务配置后再开始分析。"
    text = BLOCKER_GUIDANCE.get(code) or BLOCKER_GUIDANCE.get(code.lower())
    if text and model and "当前模型" in text:
        text = text.replace("当前模型", model, 1)
    if text:
        return text
    return f"{blocker_label(code)}\n处理方式：请根据提示完成配置后重试。"


def next_disabled_reason(
    *,
    has_api_key_input: bool,
    credential_configured: bool,
    model_validated: bool,
    persisted: bool,
    provider_eligible: bool,
    blockers: list[str],
    cloud_enabled: bool,
) -> str | None:
    """Return a concrete reason why Next must stay disabled, or None when ready."""
    if not has_api_key_input and not credential_configured:
        return f"还不能继续：{blocker_label('credential_missing')}"
    if model_validated and not persisted:
        return f"还不能继续：{blocker_label('API_KEY_NOT_SAVED')}"
    if not cloud_enabled:
        return f"还不能继续：{blocker_label('cloud_master_switch_off')}"
    if not provider_eligible:
        primary = blockers[0] if blockers else "SETUP_INCOMPLETE"
        return f"还不能继续：{blocker_label(primary)}"
    return None
