"""当前 AI 服务的连接状态——按**用户实际选中的服务商**算。

这个模块是从 `recommended_ai_setup` 里分出来的，因为那份实现有一个具体的、用户看得见的错：
它把服务商写死成 `aliyun_qwen_plus`（`CANONICAL_PROVIDER_ID`），还断言 `is_aliyun_cloud_provider`。
于是一个用 DeepSeek 的人，设置页顶上那张状态卡是这样的：

    selected_provider_id  "aliyun_qwen_plus"       ← 状态按阿里云算
    connection_ui_label   "配置已更改，需要重新验证"   ← 说的是阿里云
    validated_model       "deepseek-v4-flash"      ← 模型名却来自全局验证快照
    当前活跃服务商         deepseek

一张卡里混着两个服务商。DeepSeek 明明是通的，卡片却一直催你「重新验证」——催的是另一家。

它需要的每一样东西本来都是与服务商无关的：`evaluate_manual_boundary_candidate` 接受
`provider_name`，`model_pricing_available` 接受 model，验证快照本来就是全局一份
（`analysis_execution_plan` 也在读同一份）。**只有那个常量是写死的。** 所以这里不重写逻辑，
只把「哪个服务商」变成参数，默认取当前活跃的那个。
"""

from __future__ import annotations

import json

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import ProviderConfiguration
from app.model_gateway.gateway import ModelGateway
from app.services.ai_validation_snapshot import (
    build_current_fingerprints,
    derive_connection_ui_state,
    format_validated_at_local,
    load_validation_snapshot,
    public_snapshot_view,
)
from app.services.cloud_pricing import model_pricing_available, resolve_cloud_pricing_path
from app.services.credentials.base import CredentialStore
from app.services.provider_eligibility import evaluate_manual_boundary_candidate
from app.services.setup_readiness_copy import blocker_guidance, blocker_label

__all__ = ["AiConnectionStatus", "get_ai_connection_status", "set_cloud_body_consent"]

CLOUD_KEY = "cloud_enabled"
CLOUD_BODY_CONSENT_KEY = "cloud_body_consent"


@dataclass
class AiConnectionStatus:
    """设置页那张状态卡要说的全部内容。"""

    provider_name: str = ""
    display_name: str = ""
    model: str = ""
    credential_configured: bool = False
    provider_enabled: bool = False
    cloud_enabled: bool = False
    cloud_body_consent: bool = False
    provider_eligible: bool = False
    analysis_ready: bool = False
    connection_state: str = "unconfigured"
    ui_state: str = "NOT_CONFIGURED"
    ui_label: str = ""
    ui_reason: str = ""
    validated_at: str | None = None
    validated_at_display: str | None = None
    validated_model: str | None = None
    validation_snapshot: dict[str, Any] | None = None
    blockers: list[str] = field(default_factory=list)
    blocker_labels: list[str] = field(default_factory=list)
    blocker_guidance: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _read_setting(session: Session, key: str, default: Any) -> Any:
    """跟 recommended_ai_setup 用同一种读法：主键是 key，值是 JSON。

    第一版这里我按 `setting_key` / `setting_value` 猜了列名，跑起来直接抛
    `has no property "setting_key"`。设置表的读法只该有一处定义。
    """
    from app.db.models import ApplicationSetting

    row = session.get(ApplicationSetting, key)
    if row is None:
        return default
    try:
        return json.loads(row.value_json)
    except Exception:  # noqa: BLE001
        return default


def _pricing_path():
    from pathlib import Path

    return resolve_cloud_pricing_path(Path("config/cloud_pricing.json"))


def get_ai_connection_status(
    session: Session,
    store: CredentialStore,
    gateway: ModelGateway,
    *,
    provider_id: str | None = None,
) -> AiConnectionStatus:
    """算出当前服务商的连接状态。`provider_id` 省略时取用户选中的那个。"""
    from app.services.provider_runtime import get_active_cloud_provider

    active = provider_id or get_active_cloud_provider(session)
    status = AiConnectionStatus(provider_name=active)

    row = (
        session.query(ProviderConfiguration).filter_by(provider_name=active).one_or_none()
    )
    status.display_name = (row.display_name if row else "") or active
    status.model = (row.plus_model if row else "") or ""

    caps = gateway.get(active).capabilities()
    evaluation = evaluate_manual_boundary_candidate(
        session,
        provider_name=active,
        capabilities=caps,
        store=store,
        pricing_path=_pricing_path(),
    )
    blockers = list(evaluation.get("manual_selection_blockers") or [])
    eligible = bool(evaluation.get("manual_boundary_candidate_eligible"))
    status.credential_configured = bool(evaluation.get("credential_configured"))
    status.provider_enabled = bool(evaluation.get("enabled"))
    status.cloud_enabled = bool(_read_setting(session, CLOUD_KEY, False))

    if eligible and status.model and not model_pricing_available(status.model, _pricing_path()):
        blockers.append("pricing_unavailable")
        eligible = False
    status.provider_eligible = eligible
    status.blockers = blockers
    status.blocker_labels = [blocker_label(code) for code in blockers]
    status.blocker_guidance = (
        blocker_guidance(blockers[0], model=status.model) if blockers else None
    )

    if row is None:
        status.connection_state = "unconfigured"
    elif not row.enabled:
        status.connection_state = "disabled"
    elif row.disconnected:
        status.connection_state = "disconnected"
    elif not status.credential_configured:
        status.connection_state = "unconfigured"
    elif eligible:
        status.connection_state = "connected"
    else:
        status.connection_state = "partial"

    consent = bool(_read_setting(session, CLOUD_BODY_CONSENT_KEY, False))
    snapshot = load_validation_snapshot(session)
    # 指纹也要按当前服务商取。以前这里同样写死阿里云，于是换了服务商之后指纹永远对不上，
    # 状态就永久停在「配置已更改，需要重新验证」——验证多少次都没用，因为比的不是同一家。
    current = build_current_fingerprints(
        session, store, provider_id=active, cloud_key=CLOUD_KEY
    )
    ui_state, label, reason = derive_connection_ui_state(
        credential_configured=status.credential_configured,
        provider_enabled=status.provider_enabled,
        cloud_enabled=status.cloud_enabled,
        cloud_body_consent=consent,
        provider_eligible=status.provider_eligible,
        snapshot=snapshot,
        current=current,
        provider_display_name=status.display_name,
    )
    status.cloud_body_consent = consent
    status.ui_state = ui_state
    status.ui_label = label
    status.ui_reason = reason
    status.analysis_ready = ui_state == "READY"
    status.validated_at = (snapshot or {}).get("validated_at")
    status.validated_at_display = format_validated_at_local(status.validated_at)
    status.validated_model = (snapshot or {}).get("response_model") or (snapshot or {}).get(
        "model_id"
    )
    status.validation_snapshot = public_snapshot_view(snapshot)
    return status


def set_cloud_body_consent(session: Session, value: bool) -> bool:
    """记下「分析时允许把正文发给当前服务商」。

    这个设置原本只有通义千问那条一键路径能写。那条路径删掉之后，如果不补一个与服务商无关
    的入口，用户就再也没有办法表达这个同意——而没有它，云端分析一步都走不了。
    """
    from app.db.models import ApplicationSetting

    row = session.get(ApplicationSetting, CLOUD_BODY_CONSENT_KEY)
    payload = json.dumps(bool(value))
    if row is None:
        session.add(ApplicationSetting(key=CLOUD_BODY_CONSENT_KEY, value_json=payload))
    else:
        row.value_json = payload
    session.flush()
    return bool(value)
