"""Capability API response builders (FastAPI-free for unit tests).

Routers wrap these payloads; no license secrets or credentials are included.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.narrative_core.contracts.api_dto import (
    WHOLE_BOOK_RUNS_ENDPOINT_DISABLED,
    CapabilityDecisionDTO,
    CapabilityListItemDTO,
)
from app.narrative_core.contracts.capability import (
    CapabilityDecision,
    CapabilityMetadata,
    QuotaDecision,
    is_pro_gated_capability,
)
from app.narrative_core.enums import CapabilityKey, CapabilityReasonCode
from app.narrative_core.services.capability_service import DefaultCapabilityService


class CapabilityApiError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        super().__init__(message)


def metadata_payload(meta: CapabilityMetadata) -> dict[str, Any]:
    return {
        "key": meta.key.value,
        "display_name": meta.display_name,
        "label": meta.label,
        "description": meta.description,
        "shipped": meta.shipped,
        "requires_license": meta.requires_license,
        "availability": meta.availability.value,
        "preview_visible": meta.preview_visible,
        "supported_modes": [mode.value for mode in meta.supported_modes],
        "quota_policy_key": meta.quota_policy_key,
        "estimated_cost_class": meta.estimated_cost_class.value,
        "offline_allowed": meta.offline_allowed,
        "pro_gated": is_pro_gated_capability(meta.key),
        "quota_policies": [
            {
                "kind": policy.kind.value,
                "policy_key": policy.policy_key,
                "limit": policy.limit,
                "window_seconds": policy.window_seconds,
                "description": policy.description,
            }
            for policy in meta.quota_policies
        ],
    }


def quota_payload(quota: QuotaDecision | None) -> dict[str, Any] | None:
    if quota is None:
        return None
    reset_at = quota.reset_at
    return {
        "allowed": quota.allowed,
        "reason_code": quota.reason_code.value,
        "policy_key": quota.policy_key,
        "policy_kind": quota.policy_kind.value,
        "limit": quota.limit,
        "used": quota.used,
        "reserved": quota.reserved,
        "remaining": quota.remaining,
        "reset_at": reset_at.isoformat() if isinstance(reset_at, datetime) else None,
        "message": quota.message,
    }


def decision_payload(decision: CapabilityDecision) -> dict[str, Any]:
    key_value = (
        decision.capability_key.value
        if isinstance(decision.capability_key, CapabilityKey)
        else str(decision.capability_key)
    )
    return {
        "capability_key": key_value,
        "allowed": decision.allowed,
        "reason_code": decision.reason_code.value,
        "availability": decision.availability.value,
        "display_message": decision.display_message,
        "message": decision.message,
        "supported_modes": [mode.value for mode in decision.supported_modes],
        "quota": quota_payload(decision.quota),
        "usage": decision.usage,
        "remaining": decision.remaining,
        "offline_status": decision.offline_status,
        "license_status": decision.license_status,
        "evaluated_at": decision.evaluated_at.isoformat()
        if isinstance(decision.evaluated_at, datetime)
        else None,
        "preview_only": decision.preview_only,
    }


def build_capabilities_list_response(service: DefaultCapabilityService) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for meta in service.list_capabilities():
        decision = service.evaluate_capability(meta.key)
        list_item = CapabilityListItemDTO(
            key=meta.key,
            label=meta.display_name,
            description=meta.description,
            shipped=meta.shipped,
            availability=meta.availability,
            requires_license=meta.requires_license,
        )
        items.append(
            {
                "key": list_item.key.value,
                "label": list_item.label,
                "description": list_item.description,
                "shipped": list_item.shipped,
                "availability": list_item.availability.value,
                "requires_license": list_item.requires_license,
                "preview_visible": meta.preview_visible,
                "pro_gated": is_pro_gated_capability(meta.key),
                "decision": decision_payload(decision),
                "metadata": metadata_payload(meta),
            }
        )
    return {
        "items": items,
        "whole_book_runs_endpoint_disabled": WHOLE_BOOK_RUNS_ENDPOINT_DISABLED,
        "run_creation_enabled": False,
    }


def build_capability_detail_response(
    service: DefaultCapabilityService, capability_key: str
) -> dict[str, Any]:
    try:
        key = CapabilityKey(capability_key)
    except ValueError as exc:
        raise CapabilityApiError(
            404,
            CapabilityReasonCode.CAPABILITY_UNKNOWN.value,
            f"Unknown capability: {capability_key}",
        ) from exc

    decision = service.evaluate_capability(key)
    if decision.reason_code == CapabilityReasonCode.CAPABILITY_UNKNOWN:
        raise CapabilityApiError(
            404,
            CapabilityReasonCode.CAPABILITY_UNKNOWN.value,
            decision.display_message or f"Unknown capability: {capability_key}",
        )

    meta = service.get_capability_metadata(key)
    dto = CapabilityDecisionDTO(
        capability_key=key,
        allowed=decision.allowed,
        reason_code=decision.reason_code,
        availability=decision.availability,
        message=decision.display_message,
        preview_only=decision.preview_only,
    )
    foundation_note = None
    if key == CapabilityKey.NARRATIVE_ASSET_LIBRARY:
        foundation_note = (
            "Public entity/asset/relation APIs are not Pro-gated by this capability key."
        )
    return {
        "capability_key": dto.capability_key.value,
        "allowed": dto.allowed,
        "reason_code": dto.reason_code.value,
        "availability": dto.availability.value,
        "message": dto.message,
        "preview_only": dto.preview_only,
        "decision": decision_payload(decision),
        "metadata": metadata_payload(meta),
        "foundation_note": foundation_note,
        "whole_book_runs_endpoint_disabled": WHOLE_BOOK_RUNS_ENDPOINT_DISABLED,
        "run_creation_enabled": False,
    }
