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
    DemoSettings,
    ProviderConfigurationResponse,
    ProviderConfigurationUpdate,
    ProviderConnectionTestPreflight,
    ProviderConnectionTestResponse,
    ProviderTestRequest,
)
from app.services.credentials.base import CredentialStore
from app.services.credentials.service import get_credential_store
from app.services.cloud_budget import daily_usage
from app.services.cloud_pricing import pricing_status

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
        row = ProviderConfiguration(provider_name=name)
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


def _bootstrap_aliyun_row(session: Session, provider_name: str) -> ProviderConfiguration | None:
    from app.services.provider_bootstrap import (
        ensure_aliyun_provider_configuration,
        is_aliyun_cloud_provider,
    )

    if not is_aliyun_cloud_provider(provider_name):
        return None
    return ensure_aliyun_provider_configuration(
        session, provider_name, create_if_missing=False
    )


@router.get(
    "/model-providers/{provider_name}/configuration", response_model=ProviderConfigurationResponse
)
def get_provider_configuration(
    provider_name: str,
    session: Session = Depends(get_db),
    store: CredentialStore = Depends(get_credential_store),
):
    _bootstrap_aliyun_row(session, provider_name)
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
        store.set(provider_name, value.api_key)
        row.credential_reference = f"keyring:{provider_name}"
    row.updated_at = datetime.now(timezone.utc)
    session.commit()
    _bootstrap_aliyun_row(session, provider_name)
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
def routing_preview(gateway: ModelGateway = Depends(get_model_gateway)):
    providers = {item.name: item for item in gateway.providers()}
    # Repair / retry inherit the run-frozen provider (DEFECT-CANARY-015).
    # Do not advertise silent Flash fallback for JSON/schema repair.
    routes = [
        ("场景边界", "aliyun_qwen_plus"),
        ("场景结构", "aliyun_qwen_plus"),
        ("JSON/Schema修复(继承Run策略)", "aliyun_qwen_plus"),
        ("高难度人工复核", "aliyun_qwen_max"),
        ("本地人工测试", "local_qwen14"),
        ("27B手工短任务", "local_qwen27_manual"),
    ]
    return [
        {
            "task": task,
            "provider": name,
            "available": name in providers and providers[name].capabilities().enabled,
            "sends_content_to_cloud": providers[name].capabilities().sends_content_to_cloud
            if name in providers
            else False,
        }
        for task, name in routes
    ]


@router.get("/system/diagnostics")
def diagnostics(
    session: Session = Depends(get_db), gateway: ModelGateway = Depends(get_model_gateway)
):
    session.execute(text("SELECT 1"))
    return {
        "fastapi": "ok",
        "sqlite": "ok",
        "python": platform.python_version(),
        "providers": [
            {"name": item.name, "enabled": item.capabilities().enabled}
            for item in gateway.providers()
        ],
        "data_directory": str(user_data_root()),
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
