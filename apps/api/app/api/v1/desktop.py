import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.v1.router import error
from app.core.paths import get_project_root, user_data_root
from app.db.models import (
    AnalysisEvidence,
    AnalysisRun,
    ApplicationSetting,
    Book,
    Chapter,
    ModelInvocation,
    Paragraph,
    ProviderConfiguration,
    Scene,
)
from app.db.session import get_db
from app.model_gateway.gateway import ModelGateway, ProviderNotFoundError
from app.model_gateway.registry import get_model_gateway
from app.schemas.settings import (
    CloudBudgetSettings,
    CloudBudgetUpdate,
    CloudPricingStatus,
    CloudSettings,
    CloudSettingsUpdate,
    CloudUsageSummary,
    ConfigRuntimeProfile,
    DemoSettings,
    ProviderConfigurationResponse,
    ProviderConfigurationUpdate,
    ProviderConnectionTestPreflight,
    ProviderConnectionTestResponse,
    ProviderTestRequest,
)
from app.services.config_runtime_profile import build_config_runtime_profile
from app.services.credentials.base import CredentialStore
from app.services.credentials.service import get_credential_store
from app.services.cloud_budget import daily_usage
from app.services.cloud_pricing import pricing_status
from app.services.recommended_ai_setup import (
    CLOUD_BODY_CONSENT_KEY,
)
from app.services.runtime_info import build_runtime_payload

router = APIRouter(prefix="/api/v1")
CLOUD_KEY = "cloud_enabled"
DESKTOP_KEY = "desktop_settings"
CLOUD_BUDGET_KEY = "cloud_budget_settings"
PROJECT_ROOT = get_project_root()
PRICING_PATH = PROJECT_ROOT / "config" / "cloud_pricing.json"
LOCAL_PROFILES = {"safe", "qwen3_14b_dev", "qwen3_27b_manual"}


class LocalModelStart(BaseModel):
    profile: str = "safe"
    acknowledge_gpu_load: bool = False


def run_control_script(name: str, arguments: list[str] | None = None) -> dict[str, object]:
    script = PROJECT_ROOT / "scripts" / name
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *(arguments or [])],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=90, check=False,
    )
    return {"ok": completed.returncode == 0, "exit_code": completed.returncode,
            "output": (completed.stdout + completed.stderr)[-4000:]}


@router.post("/local-model/start")
def start_local_model(value: LocalModelStart):
    if value.profile not in LOCAL_PROFILES:
        raise error(422, "LOCAL_PROFILE_NOT_ALLOWED", "仅允许StoryLens白名单模型档位")
    if not value.acknowledge_gpu_load:
        raise error(422, "GPU_LOAD_ACKNOWLEDGEMENT_REQUIRED", "启动本地模型可能占用大量GPU资源")
    return run_control_script("start_profile_model.ps1", ["-Profile", value.profile])


@router.post("/local-model/stop")
def stop_local_model():
    return run_control_script("stop_local_model.ps1")


@router.get("/local-model/status")
def local_model_status():
    return run_control_script("status_local_model.ps1")


@router.get("/local-model/log-directory")
def local_model_log_directory():
    return {"path": str(PROJECT_ROOT / "data" / "runtime" / "local_llama")}


def setting(session: Session, key: str, default):
    row = session.get(ApplicationSetting, key)
    return json.loads(row.value_json) if row else default


def save_setting(session: Session, key: str, value) -> None:
    row = session.get(ApplicationSetting, key)
    if row is None:
        row = ApplicationSetting(key=key, value_json=json.dumps(value))
        session.add(row)
    else:
        row.value_json = json.dumps(value)
        row.updated_at = datetime.now(timezone.utc)
    session.commit()


@router.get("/settings/cloud", response_model=CloudSettings)
def get_cloud_settings(session: Session = Depends(get_db)) -> CloudSettings:
    enabled = bool(setting(session, CLOUD_KEY, False))
    configured = (
        session.scalar(
            select(func.count())
            .select_from(ProviderConfiguration)
            .where(ProviderConfiguration.credential_reference.is_not(None))
        )
        or 0
    )
    state = "disabled" if not enabled else ("unconfigured" if not configured else "available")
    return CloudSettings(enabled=enabled, state=state)


@router.put("/settings/cloud", response_model=CloudSettings)
def put_cloud_settings(value: CloudSettingsUpdate, session: Session = Depends(get_db)):
    save_setting(session, CLOUD_KEY, value.enabled)
    return get_cloud_settings(session)


class ModelTier(BaseModel):
    """一个可选的模型档位，以及它能不能真的用。

    `pricing_known=False` 的档位选了会让服务商变成不合格（`pricing_unavailable`），
    所以这件事必须随档位一起送到界面上——一个用不了的选项不该看起来可用。
    """

    id: str
    label: str
    hint: str = ""
    pricing_known: bool = True
    recommended: bool = False


class CloudProviderOption(BaseModel):
    """One switchable cloud vendor, with everything the picker needs to render it."""

    name: str
    display_name: str
    base_url: str = ""
    models: list[str] = []
    #: 档位目录。`models` 是「这一行当前存了哪几个模型」，去重之后常常只剩一个；
    #: 它回答不了「这家还能选什么」，所以选择器要读这一条。
    model_tiers: list[ModelTier] = []


class ActiveCloudProviderSettings(BaseModel):
    provider_name: str
    #: Which vendors may be made active. Emitted so the client stops hardcoding the set —
    #: it had 阿里云 and DeepSeek as two named constants and a boolean toggle between them,
    #: which is why a third vendor could not appear in the UI at all.
    options: list[CloudProviderOption] = []


#: 各家提供的模型档位。放在后端，是因为「有哪些档位、哪个推荐、贵不贵」是展示决策，
#: 而展示归后端（INV-P4）。以前这份知识散在两个前端表单的常量里，两处还对不上。
_MODEL_TIERS: dict[str, list[dict[str, object]]] = {
    "deepseek": [
        {"id": "deepseek-v4-flash", "label": "V4 Flash", "hint": "性价比优先", "recommended": True},
        {"id": "deepseek-v4-pro", "label": "V4 Pro", "hint": "质量更高，成本更高"},
    ],
    "aliyun_qwen_plus": [
        {"id": "qwen3.6-flash", "label": "Flash", "hint": "最快最省"},
        {"id": "qwen3.7-plus", "label": "Plus", "hint": "均衡", "recommended": True},
        {"id": "qwen3.7-max", "label": "Max", "hint": "质量最高，成本最高"},
    ],
}


def _model_tiers_for(name: str, saved: list[str]) -> list[ModelTier]:
    from pathlib import Path

    from app.services.cloud_pricing import model_pricing_available, resolve_cloud_pricing_path

    pricing_path = resolve_cloud_pricing_path(Path("config/cloud_pricing.json"))
    entries = list(_MODEL_TIERS.get(name) or [])
    known = {str(e["id"]) for e in entries}
    # 目录里没有、但这一行确实存着的模型也要列出来——否则用户会发现自己正在用的档位
    # 在选择器里不存在。
    for model in saved:
        if model and model not in known:
            entries.append({"id": model, "label": model})
            known.add(model)
    tiers: list[ModelTier] = []
    for entry in entries:
        model_id = str(entry["id"])
        tiers.append(
            ModelTier(
                id=model_id,
                label=str(entry.get("label") or model_id),
                hint=str(entry.get("hint") or ""),
                pricing_known=bool(model_pricing_available(model_id, pricing_path)),
                recommended=bool(entry.get("recommended")),
            )
        )
    return tiers


def _cloud_provider_options(session: Session) -> list[CloudProviderOption]:
    from app.db.models import ProviderConfiguration
    from app.services.provider_runtime import FORMAL_CLOUD_PROVIDERS

    rows = {
        row.provider_name: row
        for row in session.scalars(select(ProviderConfiguration))
        if row.provider_name in FORMAL_CLOUD_PROVIDERS
    }
    options: list[CloudProviderOption] = []
    for name in sorted(FORMAL_CLOUD_PROVIDERS):
        row = rows.get(name)
        # A vendor with several model tiers stores them on one row; the picker shows the
        # distinct ones so choosing a model never means choosing a different "provider".
        models = [
            model
            for model in dict.fromkeys(
                [
                    str(getattr(row, "plus_model", "") or ""),
                    str(getattr(row, "max_model", "") or ""),
                    str(getattr(row, "flash_model", "") or ""),
                ]
            )
            if model
        ] if row is not None else []
        options.append(
            CloudProviderOption(
                name=name,
                display_name=str(getattr(row, "display_name", "") or "") or name,
                base_url=str(getattr(row, "base_url", "") or ""),
                models=models,
                model_tiers=_model_tiers_for(name, models),
            )
        )
    return options


@router.get("/settings/active-cloud-provider", response_model=ActiveCloudProviderSettings)
def get_active_cloud_provider_setting(session: Session = Depends(get_db)):
    from app.services.provider_runtime import get_active_cloud_provider

    return ActiveCloudProviderSettings(
        provider_name=get_active_cloud_provider(session),
        options=_cloud_provider_options(session),
    )


@router.put("/settings/active-cloud-provider", response_model=ActiveCloudProviderSettings)
def put_active_cloud_provider_setting(
    value: ActiveCloudProviderSettings, session: Session = Depends(get_db)
):
    from app.services.provider_runtime import set_active_cloud_provider

    try:
        name = set_active_cloud_provider(session, value.provider_name)
    except ValueError as exc:
        raise error(422, "UNSUPPORTED_CLOUD_PROVIDER", str(exc)) from exc
    session.commit()
    return ActiveCloudProviderSettings(
        provider_name=name, options=_cloud_provider_options(session)
    )


def cloud_budget_value(session: Session) -> CloudBudgetUpdate:
    return CloudBudgetUpdate.model_validate(setting(session, CLOUD_BUDGET_KEY, {}))


@router.get("/settings/cloud-budget", response_model=CloudBudgetSettings)
def get_cloud_budget(session: Session = Depends(get_db)):
    value = cloud_budget_value(session)
    pricing = pricing_status(PRICING_PATH)
    return CloudBudgetSettings(**value.model_dump(), pricing_configured=bool(pricing["enabled"]),
                               pricing_version=pricing["pricing_version"])


@router.put("/settings/cloud-budget", response_model=CloudBudgetSettings)
def put_cloud_budget(value: CloudBudgetUpdate, session: Session = Depends(get_db)):
    save_setting(session, CLOUD_BUDGET_KEY, value.model_dump())
    return get_cloud_budget(session)


@router.get("/cloud-pricing/status", response_model=CloudPricingStatus)
def get_cloud_pricing_status():
    return pricing_status(PRICING_PATH)


@router.get("/cloud-usage/summary", response_model=CloudUsageSummary)
def get_cloud_usage_summary(session: Session = Depends(get_db)):
    budget = cloud_budget_value(session).model_dump()
    return daily_usage(session, budget, bool(setting(session, CLOUD_KEY, False)),
                       pricing_status(PRICING_PATH))


@router.get("/settings/desktop", response_model=DemoSettings)
def get_desktop_settings(session: Session = Depends(get_db)):
    return DemoSettings.model_validate(setting(session, DESKTOP_KEY, {}))


@router.put("/settings/desktop", response_model=DemoSettings)
def put_desktop_settings(value: DemoSettings, session: Session = Depends(get_db)):
    save_setting(session, DESKTOP_KEY, value.model_dump())
    return value


def configuration_response(row: ProviderConfiguration | None, name: str, store: CredentialStore):
    if row is None:
        # A transient ORM instance does NOT carry its column defaults — SQLAlchemy applies
        # those on INSERT — so every field came back None and the response model failed with
        # 13 validation errors. On a fresh install that is four 500s in the first seconds of
        # the app's life, before any provider row exists. The fallback has to state the
        # defaults itself; they mirror ProviderConfiguration in db/models.py.
        row = ProviderConfiguration(
            provider_name=name,
            display_name="",
            region="cn-beijing",
            workspace_id="",
            base_url="",
            plus_model="qwen3.7-plus",
            max_model="qwen3.7-max",
            flash_model="qwen3.6-flash",
            timeout_seconds=300,
            max_retries=3,
            enabled=False,
            disconnected=True,
            allow_auto_route=False,
            raw_logging_enabled=False,
        )
    credential = store.get(name) if store.available() else None
    credential_state = (
        "configured" if credential else ("missing" if store.available() else "unknown")
    )
    if not row.enabled:
        connection = "disabled"
    elif row.disconnected:
        connection = "disconnected"
    elif not credential:
        connection = "unconfigured"
    else:
        connection = "connected"
    return ProviderConfigurationResponse(
        provider_name=name,
        display_name=row.display_name,
        region=row.region,
        workspace_id=row.workspace_id,
        base_url=row.base_url,
        plus_model=row.plus_model,
        max_model=row.max_model,
        flash_model=row.flash_model,
        timeout_seconds=row.timeout_seconds,
        max_retries=row.max_retries,
        enabled=row.enabled,
        disconnected=row.disconnected,
        allow_auto_route=row.allow_auto_route,
        raw_logging_enabled=row.raw_logging_enabled,
        credential_state=credential_state,
        connection_state=connection,
        updated_at=row.updated_at,
    )


def _bootstrap_provider_row(session: Session, provider_name: str) -> ProviderConfiguration | None:
    from app.services.provider_bootstrap import (
        ensure_aliyun_provider_configuration,
        ensure_deepseek_provider_configuration,
        is_aliyun_cloud_provider,
        is_deepseek_provider,
    )

    if is_deepseek_provider(provider_name):
        return ensure_deepseek_provider_configuration(session, create_if_missing=True)
    if not is_aliyun_cloud_provider(provider_name):
        return None
    return ensure_aliyun_provider_configuration(
        session, provider_name, create_if_missing=False
    )


# Back-compat alias for older call sites / tests.
_bootstrap_aliyun_row = _bootstrap_provider_row
class CloudBodyConsentUpdate(BaseModel):
    accepted: bool


@router.put("/desktop/ai-connection/consent")
def put_cloud_body_consent(
    value: CloudBodyConsentUpdate,
    session: Session = Depends(get_db),
):
    """与服务商无关的「正文发送同意」写入口。"""
    from app.services.ai_connection_status import set_cloud_body_consent

    accepted = set_cloud_body_consent(session, value.accepted)
    session.commit()
    return {"accepted": accepted}


@router.get("/desktop/ai-connection")
def get_ai_connection(
    session: Session = Depends(get_db),
    store: CredentialStore = Depends(get_credential_store),
    gateway: ModelGateway = Depends(get_model_gateway),
):
    """设置页那张状态卡的数据源，按用户实际选中的服务商算。

    取代 `/desktop/ai-setup/recommended-qwen`：那一支把服务商写死成阿里云，于是用
    DeepSeek 的人会看到一张混着两家的卡——状态和「需要重新验证」来自阿里云，模型名却是
    DeepSeek 的。这里只有一个来源：当前活跃服务商。
    """
    from app.services.ai_connection_status import get_ai_connection_status

    return get_ai_connection_status(session, store, gateway).to_dict()
@router.get("/settings/config-profile", response_model=ConfigRuntimeProfile)
def get_config_runtime_profile(
    store: CredentialStore = Depends(get_credential_store),
) -> ConfigRuntimeProfile:
    return ConfigRuntimeProfile.model_validate(build_config_runtime_profile(store))


@router.get("/runtime")
def get_runtime(store: CredentialStore = Depends(get_credential_store)) -> dict:
    """Read-only shell / capability description for desktop and local web."""
    return build_runtime_payload(store)


@router.get("/entitlements")
def get_entitlements(session: Session = Depends(get_db)) -> dict:
    from app.services.entitlement import entitlement_snapshot

    return entitlement_snapshot(session)


@router.get("/entitlements/features/{feature_key}")
def get_feature_entitlement(feature_key: str, session: Session = Depends(get_db)) -> dict:
    from app.services.entitlement import can_use_feature

    return can_use_feature(session, feature_key)


class LicenseActivateRequest(BaseModel):
    license_code: str


@router.post("/licenses/activate")
def activate_license(value: LicenseActivateRequest, session: Session = Depends(get_db)) -> dict:
    from app.services.entitlement import activate_license_code
    from app.services.license_crypto import LicenseError

    try:
        return activate_license_code(session, value.license_code)
    except LicenseError as exc:
        raise error(400, exc.code, exc.message) from exc


@router.post("/system/open-data-directory")
def open_data_directory() -> dict[str, object]:
    """Open the local data folder in the OS file manager (loopback API only)."""
    root = user_data_root()
    root.mkdir(parents=True, exist_ok=True)
    try:
        if platform.system() == "Windows":
            subprocess.Popen(["explorer", str(root)])  # noqa: S603
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(root)])  # noqa: S603
        else:
            subprocess.Popen(["xdg-open", str(root)])  # noqa: S603
    except OSError as exc:
        raise error(500, "OPEN_DATA_DIR_FAILED", f"无法打开数据目录：{exc}") from exc
    return {"ok": True, "path": str(root)}
@router.get(
    "/model-providers/{provider_name}/configuration", response_model=ProviderConfigurationResponse
)
def get_provider_configuration(
    provider_name: str,
    session: Session = Depends(get_db),
    store: CredentialStore = Depends(get_credential_store),
):
    _bootstrap_provider_row(session, provider_name)
    return configuration_response(
        session.scalar(
            select(ProviderConfiguration).where(
                ProviderConfiguration.provider_name == provider_name
            )
        ),
        provider_name,
        store,
    )


@router.put(
    "/model-providers/{provider_name}/configuration", response_model=ProviderConfigurationResponse
)
def put_provider_configuration(
    provider_name: str,
    value: ProviderConfigurationUpdate,
    session: Session = Depends(get_db),
    store: CredentialStore = Depends(get_credential_store),
):
    row = session.scalar(
        select(ProviderConfiguration).where(ProviderConfiguration.provider_name == provider_name)
    )
    if row is None:
        row = ProviderConfiguration(provider_name=provider_name)
        session.add(row)
    for key, item in value.model_dump(exclude={"api_key"}).items():
        if key == "base_url":
            setattr(row, key, str(item) if item else "")
        else:
            setattr(row, key, item)
    if value.api_key:
        # Independent keyring username per provider (aliyun_* vs deepseek).
        store.set(provider_name, value.api_key)
        row.credential_reference = f"keyring:{provider_name}"
    row.updated_at = datetime.now(timezone.utc)
    session.commit()
    # Fill public Bailian / DeepSeek endpoint defaults when client omitted base_url.
    from app.services.provider_bootstrap import (
        ensure_aliyun_provider_configuration,
        ensure_deepseek_provider_configuration,
        is_aliyun_cloud_provider,
        is_deepseek_provider,
    )

    if is_deepseek_provider(provider_name):
        ensure_deepseek_provider_configuration(session, create_if_missing=True)
    elif is_aliyun_cloud_provider(provider_name):
        ensure_aliyun_provider_configuration(
            session, provider_name, create_if_missing=True
        )
    else:
        _bootstrap_provider_row(session, provider_name)
    # Saving Provider configuration must NOT change active_cloud_provider (CHG-065).
    # Default switching is explicit via PUT /settings/active-cloud-provider or UI「设为默认」.
    return configuration_response(
        session.scalar(
            select(ProviderConfiguration).where(
                ProviderConfiguration.provider_name == provider_name
            )
        ),
        provider_name,
        store,
    )


def change_provider_state(provider_name: str, action: str, session: Session):
    row = session.scalar(
        select(ProviderConfiguration).where(ProviderConfiguration.provider_name == provider_name)
    )
    if row is None:
        row = ProviderConfiguration(provider_name=provider_name)
        session.add(row)
    if action == "connect":
        row.disconnected = False
    elif action == "disconnect":
        row.disconnected = True
    elif action == "enable":
        row.enabled = True
    elif action == "disable":
        row.enabled = False
    session.commit()
    if action in {"connect", "enable"}:
        _bootstrap_aliyun_row(session, provider_name)
    return {"provider_name": provider_name, "action": action, "status": "ok"}


@router.post("/model-providers/{provider_name}/connect")
def connect_provider(provider_name: str, session: Session = Depends(get_db)):
    return change_provider_state(provider_name, "connect", session)


@router.post("/model-providers/{provider_name}/disconnect")
def disconnect_provider(provider_name: str, session: Session = Depends(get_db)):
    return change_provider_state(provider_name, "disconnect", session)


@router.post("/model-providers/{provider_name}/enable")
def enable_provider(provider_name: str, session: Session = Depends(get_db)):
    return change_provider_state(provider_name, "enable", session)


@router.post("/model-providers/{provider_name}/disable")
def disable_provider(provider_name: str, session: Session = Depends(get_db)):
    return change_provider_state(provider_name, "disable", session)


@router.post("/model-providers/{provider_name}/validate-configuration")
def validate_provider_configuration(
    provider_name: str,
    session: Session = Depends(get_db),
    store: CredentialStore = Depends(get_credential_store),
):
    result = get_provider_configuration(provider_name, session, store)
    valid = bool(result.base_url and result.credential_state == "configured")
    return {"valid": valid, "credential_state": result.credential_state}


@router.post("/model-providers/{provider_name}/transport-diagnostic")
def transport_diagnostic(
    provider_name: str,
    gateway: ModelGateway = Depends(get_model_gateway),
    session: Session = Depends(get_db),
    store: CredentialStore = Depends(get_credential_store),
):
    from app.services.transport_diagnostic import run_transport_diagnostic

    try:
        provider = gateway.get(provider_name)
    except ProviderNotFoundError as exc:
        raise error(404, "PROVIDER_NOT_FOUND", "Provider不存在") from exc
    return run_transport_diagnostic(
        provider_name=provider_name,
        provider=provider,
        session=session,
        store=store,
    )


@router.post("/model-providers/{provider_name}/test")
async def test_provider_connection(
    provider_name: str,
    request: ProviderTestRequest,
    gateway: ModelGateway = Depends(get_model_gateway),
    session: Session = Depends(get_db),
    store: CredentialStore = Depends(get_credential_store),
) -> ProviderConnectionTestResponse:
    from fastapi import HTTPException

    from app.services.provider_connection_test import (
        ConnectionTestFailure,
        run_connection_test,
    )

    try:
        provider = gateway.get(provider_name)
    except ProviderNotFoundError as exc:
        raise error(404, "PROVIDER_NOT_FOUND", "Provider不存在") from exc
    try:
        return await run_connection_test(
            session=session,
            provider=provider,
            provider_name=provider_name,
            store=store,
            confirmed=request.confirmed,
            max_output_tokens=request.max_output_tokens,
        )
    except ConnectionTestFailure as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post(
    "/model-providers/{provider_name}/test/preflight",
    response_model=ProviderConnectionTestPreflight,
)
def provider_connection_test_preflight(
    provider_name: str,
    gateway: ModelGateway = Depends(get_model_gateway),
    session: Session = Depends(get_db),
    store: CredentialStore = Depends(get_credential_store),
) -> ProviderConnectionTestPreflight:
    from app.services.provider_connection_test import connection_test_preflight

    try:
        provider = gateway.get(provider_name)
    except ProviderNotFoundError as exc:
        raise error(404, "PROVIDER_NOT_FOUND", "Provider不存在") from exc
    return connection_test_preflight(
        session=session,
        provider=provider,
        provider_name=provider_name,
        store=store,
        max_output_tokens=32,
    )


@router.delete("/model-providers/{provider_name}/credentials")
def delete_credentials(
    provider_name: str,
    session: Session = Depends(get_db),
    store: CredentialStore = Depends(get_credential_store),
):
    store.delete(provider_name)
    row = session.scalar(
        select(ProviderConfiguration).where(ProviderConfiguration.provider_name == provider_name)
    )
    if row:
        row.credential_reference = None
        row.disconnected = True
        session.commit()
    return {"provider_name": provider_name, "credential_state": "missing"}


@router.get("/dashboard/summary")
def dashboard_summary(session: Session = Depends(get_db)):
    def count(model):
        return session.scalar(select(func.count()).select_from(model)) or 0
    return {
        "books": count(Book),
        "chapters": count(Chapter),
        "paragraphs": count(Paragraph),
        "scenes": count(Scene),
        "successful_runs": session.scalar(
            select(func.count()).select_from(AnalysisRun).where(AnalysisRun.status == "succeeded")
        )
        or 0,
        "failed_runs": session.scalar(
            select(func.count()).select_from(AnalysisRun).where(AnalysisRun.status == "failed")
        )
        or 0,
        "cloud_invocations": session.scalar(
            select(func.count())
            .select_from(ModelInvocation)
            .where(ModelInvocation.is_cloud.is_(True))
        )
        or 0,
        "local_invocations": session.scalar(
            select(func.count())
            .select_from(ModelInvocation)
            .where(ModelInvocation.is_cloud.is_(False))
        )
        or 0,
    }


@router.get("/model-routing/preview")
def routing_preview(
    gateway: ModelGateway = Depends(get_model_gateway),
    session: Session = Depends(get_db),
):
    """Task routing preview — reflects TaskRoutingPolicy + active default (CHG-065)."""
    from app.services.cloud_provider_resolver_v1 import build_routing_preview

    providers = {item.name: item for item in gateway.providers()}
    return build_routing_preview(session, gateway_provider_names=set(providers.keys()))


@router.get("/system/diagnostics")
def diagnostics(
    session: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_model_gateway),
    store: CredentialStore = Depends(get_credential_store),
):
    session.execute(text("SELECT 1"))
    profile = build_config_runtime_profile(store)
    return {
        "fastapi": "ok",
        "sqlite": "ok",
        "python": platform.python_version(),
        "providers": [
            {"name": item.name, "enabled": item.capabilities().enabled}
            for item in gateway.providers()
        ],
        "data_directory": str(user_data_root()),
        "database_path": profile["database_path"],
        "app_env": profile["app_env"],
        "config_profile": profile,
        "recent_error": None,
    }


@router.get("/artifacts/{artifact_id}/evidence")
def artifact_evidence(artifact_id: int, session: Session = Depends(get_db)):
    return list(
        session.execute(
            select(AnalysisEvidence.field_path, AnalysisEvidence.paragraph_id).where(
                AnalysisEvidence.artifact_id == artifact_id
            )
        ).mappings()
    )
