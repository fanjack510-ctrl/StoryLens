"""Canonical runtime Provider assembly for all formal generation paths."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, ApplicationSetting, ProviderConfiguration
from app.model_gateway.base import ModelProvider
from app.model_gateway.gateway import ModelGateway
from app.schemas.settings import CloudBudgetUpdate
from app.services.cloud_budget import daily_usage
from app.services.cloud_pricing import pricing_status
from app.services.credentials.base import CredentialStore
from app.services.provider_runtime import (
    apply_provider_runtime,
    bind_gateway_runtime,
    cloud_master_enabled,
)


@dataclass(frozen=True)
class ResolvedProviderRuntime:
    provider: ModelProvider
    provider_state_version: str
    eligibility: dict[str, object]


class ProviderRuntimeService:
    """Single entry for overlaying ProviderConfiguration onto gateway providers."""

    @staticmethod
    def bind_gateway(
        gateway: ModelGateway,
        session: Session,
        store: CredentialStore | None = None,
    ) -> ModelGateway:
        return bind_gateway_runtime(gateway, session, store)

    @staticmethod
    def resolve_for_run(
        gateway: ModelGateway,
        session: Session,
        run: AnalysisRun,
        store: CredentialStore | None = None,
        *,
        task_type: str = "scene_analysis",
        require_manual_boundary_eligibility: bool = False,
        pricing_path: Path = Path("config/cloud_pricing.json"),
    ) -> ResolvedProviderRuntime:
        """Assemble the run provider from DB + credentials. No external HTTP."""
        ProviderRuntimeService.bind_gateway(gateway, session, store)
        provider = gateway.get(run.provider)
        apply_provider_runtime(provider, session, store)
        caps = provider.capabilities()
        row = (
            session.query(ProviderConfiguration)
            .filter_by(provider_name=provider.name)
            .one_or_none()
        )
        cloud_enabled = cloud_master_enabled(session)
        budget_row = session.get(ApplicationSetting, "cloud_budget_settings")
        budget = CloudBudgetUpdate.model_validate(
            json.loads(budget_row.value_json) if budget_row else {}
        ).model_dump()
        pricing = pricing_status(pricing_path)
        usage = daily_usage(session, budget, cloud_enabled, pricing)
        credential = True
        if caps.cloud and store is not None and store.available():
            credential = bool(store.get(provider.name))
        elif caps.cloud:
            credential = bool(getattr(provider, "api_key", None))

        enabled = bool(row.enabled) if row and caps.cloud else bool(caps.enabled)
        # Runtime object must mirror DB for cloud providers after overlay.
        if caps.cloud and hasattr(provider, "enabled"):
            provider.enabled = enabled
        configured = (
            bool(row and (row.base_url or row.workspace_id)) if caps.cloud else True
        )
        connected = bool(row and not row.disconnected) if caps.cloud else True

        blockers: list[str] = []
        if caps.cloud and not cloud_enabled:
            blockers.append("cloud_master_switch_off")
        if not enabled:
            blockers.append("provider_disabled")
        if not configured:
            blockers.append("provider_not_configured")
        if not connected:
            blockers.append("provider_disconnected")
        if not credential:
            blockers.append("credential_missing")
        if caps.cloud and not pricing.get("enabled"):
            blockers.append("pricing_unavailable")
        if caps.cloud and not usage.get("within_budget"):
            blockers.append("budget_unavailable")

        if task_type == "scene_analysis":
            if not caps.supports_scene_analysis and caps.cloud:
                # Local/fake providers may omit the flag; only enforce for cloud.
                if row is not None:
                    blockers.append("scene_analysis_not_supported")
        elif task_type in {"scene_boundary", "boundary_candidate_detection"}:
            if not caps.supports_boundary_candidates:
                blockers.append("boundary_candidates_not_supported")

        if require_manual_boundary_eligibility:
            if not caps.supports_boundary_candidates:
                blockers.append("boundary_candidates_not_supported")
            if caps.cloud and not caps.requires_boundary_review:
                blockers.append("boundary_review_not_required_capability")

        # Never require default / allow_auto_route / automatic_boundary_routing.
        state_payload = {
            "provider_name": provider.name,
            "enabled": enabled,
            "configured": configured,
            "connected": connected,
            "credential": credential,
            "cloud_enabled": cloud_enabled,
            "model": getattr(provider, "default_model", None) or run.model,
            "base_url": getattr(provider, "base_url", None),
            "task_type": task_type,
            "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        }
        version = hashlib.sha256(
            json.dumps(state_payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        eligibility = {
            "enabled": enabled,
            "configured": configured,
            "connected": connected,
            "credential_configured": credential,
            "cloud_master_enabled": cloud_enabled,
            "pricing_enabled": bool(pricing.get("enabled")),
            "within_budget": bool(usage.get("within_budget")),
            "supports_scene_analysis": bool(caps.supports_scene_analysis) or not caps.cloud,
            "blockers": list(dict.fromkeys(blockers)),
            "eligible": not blockers,
            "provider_state_version": version,
            "remaining_budget": {
                "requests": usage.get("remaining_requests", 0),
                "tokens": usage.get("remaining_tokens", 0),
                "estimated_cost": usage.get("remaining_estimated_cost", 0.0),
            },
            "exceeded_dimensions": list(usage.get("exceeded_dimensions") or []),
        }
        return ResolvedProviderRuntime(
            provider=provider,
            provider_state_version=version,
            eligibility=eligibility,
        )
