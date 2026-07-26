"""HTTP factory for Native Overview — production defaults to Private engine.

Fixture is explicit-opt-in only (provider_id/model_id). Never silent fallback.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_ENGINE_ID,
    PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
)
from app.narrative_core.services.native_overview_live_transport import (
    AliyunNativeOverviewTransport,
)
from app.narrative_core.services.native_overview_service import NativeOverviewService
from app.narrative_core.services.native_overview_smoke_fake_transport import (
    NativeOverviewSmokeFakeTransport,
    is_native_overview_smoke_fake_enabled,
)


def resolve_native_overview_engine_id(
    provider_id: str | None = None,
    model_id: str | None = None,
    *,
    default: str = PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
) -> str:
    """Map create-request identity to overview engine_id.

    Product default is Private. Fixture only when explicitly named.
    """

    tokens = {(provider_id or "").strip(), (model_id or "").strip()}
    tokens.discard("")
    if FIXTURE_ENGINE_ID in tokens or "fixture" in tokens:
        return FIXTURE_ENGINE_ID
    if PRIVATE_NATIVE_OVERVIEW_ENGINE_ID in tokens:
        return PRIVATE_NATIVE_OVERVIEW_ENGINE_ID
    return default


def _build_transport_for_engine(
    engine_id: str,
    *,
    model_id: str | None = None,
) -> Any | None:
    if engine_id == FIXTURE_ENGINE_ID:
        return None
    if is_native_overview_smoke_fake_enabled():
        return NativeOverviewSmokeFakeTransport()
    # Product Live path (G5). Missing key → engine raises PROVIDER_NOT_CONFIGURED.
    return AliyunNativeOverviewTransport(model=model_id or "qwen3.7-plus")


def build_native_overview_service(
    session: Session,
    *,
    provider_id: str | None = None,
    model_id: str | None = None,
) -> NativeOverviewService:
    from app.services.native_overview_ai_binding import (
        is_engine_identity,
        resolve_native_overview_ai_binding,
    )

    engine_id = resolve_native_overview_engine_id(provider_id, model_id)
    ai = resolve_native_overview_ai_binding(session)
    resolved_model = model_id if model_id and not is_engine_identity(model_id) else ai.model_id
    transport = _build_transport_for_engine(engine_id, model_id=resolved_model)
    return NativeOverviewService(
        session,
        engine_id=engine_id,
        transport=transport,
    )


def is_cloud_provider_configured_for_native_overview() -> bool:
    """Best-effort keyring check for preflight ``provider_configured``."""

    if is_native_overview_smoke_fake_enabled():
        return True
    try:
        from app.services.credentials.service import get_credential_store

        key = get_credential_store().get("aliyun_qwen_plus")
        return bool(key and str(key).strip())
    except Exception:  # noqa: BLE001
        return False


__all__ = [
    "build_native_overview_service",
    "is_cloud_provider_configured_for_native_overview",
    "resolve_native_overview_engine_id",
]
