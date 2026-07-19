from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

from sqlalchemy.orm import Session

from app.db.models import ApplicationSetting, ModelInvocation, ProviderConfiguration
from app.model_gateway.base import ProviderCapabilities
from app.schemas.settings import CloudBudgetUpdate
from app.services.cloud_budget import daily_usage
from app.services.cloud_pricing import pricing_status
from app.services.credentials.base import CredentialStore

# Application-layer failures after a successful Provider HTTP round-trip.
# These must NOT mark the Provider itself unhealthy for manual eligibility.
_APPLICATION_ERROR_CODES = {
    "BUSINESS_VALIDATION_ERROR",
    "BUSINESS_VALIDATION_FAILED",
    "SCHEMA_VALIDATION_FAILED",
    "EVIDENCE_VALIDATION_ERROR",
    "EVIDENCE_VALIDATION_FAILED",
    "STRUCTURED_OUTPUT_ERROR",
    "CANDIDATE_TRUE_WITHOUT_LEGAL_REASON",
}

_TRANSPORT_ERROR_PREFIXES = ("PROVIDER_",)
_TRANSPORT_ERROR_CODES = {
    "PROVIDER_ERROR",
    "HTTP_ERROR",
    "TIMEOUT",
    "CONNECT_TIMEOUT",
    "READ_TIMEOUT",
}


def provider_eligibility(
    session: Session,
    *,
    provider_name: str,
    capabilities: ProviderCapabilities,
    healthy: bool,
    store: CredentialStore,
    pricing_path: Path,
) -> dict[str, object]:
    row = session.query(ProviderConfiguration).filter_by(provider_name=provider_name).one_or_none()
    cloud_row = session.get(ApplicationSetting, "cloud_enabled")
    budget_row = session.get(ApplicationSetting, "cloud_budget_settings")
    cloud_enabled = bool(json.loads(cloud_row.value_json)) if cloud_row else False
    budget = CloudBudgetUpdate.model_validate_json(
        budget_row.value_json if budget_row else "{}"
    ).model_dump()
    pricing = pricing_status(pricing_path)
    usage = daily_usage(session, budget, cloud_enabled, pricing)
    credential = bool(store.get(provider_name)) if store.available() and capabilities.cloud else True
    # Cloud providers use ProviderConfiguration.enabled — never registry default
    # capabilities.enabled / settings.aliyun_enabled / allow_auto_route.
    enabled = bool(row.enabled) if row and capabilities.cloud else capabilities.enabled
    configured = bool(row and (row.base_url or row.workspace_id)) if capabilities.cloud else True
    connected = bool(row and not row.disconnected) if capabilities.cloud else healthy
    manual_blockers: list[str] = []
    if capabilities.cloud and not cloud_enabled:
        manual_blockers.append("cloud_master_switch_off")
    if not enabled:
        manual_blockers.append("provider_disabled")
    if not configured:
        manual_blockers.append("provider_not_configured")
    if not connected:
        manual_blockers.append("provider_disconnected")
    if not credential:
        manual_blockers.append("credential_missing")
    if not capabilities.supports_boundary_candidates:
        manual_blockers.append("boundary_candidates_not_supported")
    if capabilities.cloud and not pricing.get("enabled"):
        manual_blockers.append("pricing_unavailable")
    if capabilities.cloud and not usage.get("within_budget"):
        manual_blockers.append("budget_unavailable")
    if not healthy:
        manual_blockers.append("provider_unhealthy")
    automatic_blockers = list(manual_blockers)
    if not bool(row and row.allow_auto_route):
        automatic_blockers.append("auto_route_disabled")
    if not capabilities.automatic_boundary_routing:
        automatic_blockers.append("automatic_boundary_routing_unsupported")
    manual_eligible = not manual_blockers and capabilities.requires_boundary_review
    automatic_eligible = not automatic_blockers
    return {
        "enabled": enabled,
        "configured": configured,
        "connected": connected,
        "healthy": healthy,
        "credential_configured": credential,
        "allow_auto_route": bool(row and row.allow_auto_route),
        "manual_boundary_candidate_eligible": manual_eligible,
        "automatic_route_eligible": automatic_eligible,
        "manual_short_task_eligible": bool(
            capabilities.manual_only and enabled and configured and connected and healthy
        ),
        "manual_selection_blockers": list(dict.fromkeys(manual_blockers)),
        "automatic_route_blockers": list(dict.fromkeys(automatic_blockers)),
        "workflow_prompts": {
            "boundary_candidate": "v3.5",
            "boundary_adjudication": "v1",
            "scene_analysis": "v3.2",
            "thinking": False,
            "boundary_confirmation": "human_required",
        }
        if capabilities.supports_boundary_candidates
        else None,
    }


def _is_transport_failure(invocation: ModelInvocation) -> bool:
    code = (invocation.error_code or "").upper()
    if code in _APPLICATION_ERROR_CODES:
        return False
    if any(code.startswith(prefix) for prefix in _TRANSPORT_ERROR_PREFIXES):
        return True
    if code in _TRANSPORT_ERROR_CODES:
        return True
    status = invocation.http_status_code
    if status is not None and int(status) >= 500:
        return True
    if status is not None and int(status) in {401, 403, 408, 429}:
        return True
    return False


def _proves_provider_reachable(invocation: ModelInvocation) -> bool:
    """HTTP round-trip evidence that the Provider itself is reachable."""
    if invocation.status == "succeeded":
        return True
    if not invocation.http_request_sent:
        return False
    status = invocation.http_status_code
    if status is not None and 200 <= int(status) < 300:
        return True
    # Application validation after a response body is also connectivity proof.
    code = (invocation.error_code or "").upper()
    return code in _APPLICATION_ERROR_CODES and not _is_transport_failure(invocation)


def _runtime_health_from_invocations(
    session: Session, provider_name: str
) -> tuple[str, str, datetime]:
    """Derive cached health without network I/O.

    Business/schema validation failures after HTTP 200 do not mark the Provider
    unhealthy. Prefer recent connection_test evidence when available.
    """
    now = datetime.now(timezone.utc)
    latest_test = (
        session.query(ModelInvocation)
        .filter(
            ModelInvocation.provider_name == provider_name,
            ModelInvocation.http_request_sent.is_(True),
            ModelInvocation.invocation_kind == "connection_test",
        )
        .order_by(ModelInvocation.created_at.desc(), ModelInvocation.id.desc())
        .first()
    )
    latest_any = (
        session.query(ModelInvocation)
        .filter(
            ModelInvocation.provider_name == provider_name,
            ModelInvocation.http_request_sent.is_(True),
        )
        .order_by(ModelInvocation.created_at.desc(), ModelInvocation.id.desc())
        .first()
    )
    evidence = latest_test or latest_any
    if evidence is None:
        row = (
            session.query(ProviderConfiguration)
            .filter_by(provider_name=provider_name)
            .one_or_none()
        )
        checked = row.updated_at if row and row.updated_at is not None else now
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return "healthy", "configured_readiness", checked

    checked = evidence.created_at
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    age = (now - checked).total_seconds()
    source = (
        "cached_connection_test"
        if evidence.invocation_kind == "connection_test"
        else "cached_success"
    )

    if _proves_provider_reachable(evidence):
        if age > 24 * 60 * 60:
            return "stale", source, checked
        return "healthy", source, checked

    if _is_transport_failure(evidence):
        return "unhealthy", "cached_failure", checked

    # Non-transport failure without clear reachability: fall back to readiness.
    row = (
        session.query(ProviderConfiguration)
        .filter_by(provider_name=provider_name)
        .one_or_none()
    )
    fallback = row.updated_at if row and row.updated_at is not None else checked
    if fallback.tzinfo is None:
        fallback = fallback.replace(tzinfo=timezone.utc)
    return "healthy", "configured_readiness", fallback


def evaluate_manual_boundary_candidate(
    session: Session,
    *,
    provider_name: str,
    capabilities: ProviderCapabilities,
    store: CredentialStore,
    pricing_path: Path,
) -> dict[str, object]:
    """Single zero-network source of truth for manual boundary readiness."""
    runtime_state, health_source, health_checked_at = _runtime_health_from_invocations(
        session, provider_name
    )
    now = datetime.now(timezone.utc)
    result = provider_eligibility(
        session,
        provider_name=provider_name,
        capabilities=capabilities,
        healthy=runtime_state == "healthy",
        store=store,
        pricing_path=pricing_path,
    )
    readiness = all(
        bool(result[field])
        for field in ("enabled", "configured", "connected", "credential_configured")
    )
    result["healthy"] = readiness and runtime_state == "healthy"
    # Stale health is advisory for preflight refresh; it must not use the
    # generic provider_unhealthy label (which implies transport failure).
    if runtime_state == "stale":
        result["manual_selection_blockers"] = [
            item
            for item in result["manual_selection_blockers"]
            if item != "provider_unhealthy"
        ] + ["provider_health_stale"]
    if not readiness and "provider_unhealthy" not in result["manual_selection_blockers"]:
        # Readiness failure is already covered by specific blockers; keep
        # provider_unhealthy only for true transport unhealthy state.
        pass
    if runtime_state == "unhealthy" and "provider_unhealthy" not in result[
        "manual_selection_blockers"
    ]:
        result["manual_selection_blockers"].append("provider_unhealthy")
    result["manual_boundary_candidate_eligible"] = bool(
        not result["manual_selection_blockers"] and capabilities.requires_boundary_review
    )
    evaluated_at = now.isoformat()
    state_payload = {
        "provider": provider_name,
        "eligible": result["manual_boundary_candidate_eligible"],
        "blockers": result["manual_selection_blockers"],
        "enabled": result["enabled"],
        "configured": result["configured"],
        "connected": result["connected"],
        "credential": result["credential_configured"],
        "health_state": runtime_state,
        "health_checked_at": health_checked_at.isoformat(),
    }
    result.update({
        "status": "eligible" if result["manual_boundary_candidate_eligible"] else "blocked",
        "evaluated_at": evaluated_at,
        "health_state": runtime_state if readiness else "unhealthy",
        "health_source": health_source,
        "health_checked_at": health_checked_at.isoformat(),
        "capability_schema_version": "1c-a-2",
        "provider_state_version": hashlib.sha256(
            json.dumps(state_payload, sort_keys=True).encode()
        ).hexdigest()[:16],
        "provider_name": provider_name,
    })
    return result


class ProviderEligibilityService:
    """Canonical eligibility facade shared by listing, create, and recover."""

    @staticmethod
    def evaluate_manual_boundary_candidate(
        session: Session,
        *,
        provider_name: str,
        capabilities: ProviderCapabilities,
        store: CredentialStore,
        pricing_path: Path,
    ) -> dict[str, object]:
        return evaluate_manual_boundary_candidate(
            session,
            provider_name=provider_name,
            capabilities=capabilities,
            store=store,
            pricing_path=pricing_path,
        )
