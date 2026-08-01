"""Free/Pro whole-book product capability scope (WB-1.6A) — separate from Wave A registry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)


class AccessTier(StrEnum):
    free = "free"
    pro = "pro"


class CapabilityReleaseStatus(StrEnum):
    available = "available"
    planned = "planned"


class CapabilityAccessStatus(StrEnum):
    granted = "granted"
    locked = "locked"
    planned = "planned"


class ProductCapabilityReasonCode(StrEnum):
    capability_planned = "capability_planned"
    pro_required = "pro_required"
    capability_unknown = "capability_unknown"


@dataclass(frozen=True)
class ProductCapabilityDefinition:
    capability_id: str
    display_name: str
    required_tier: AccessTier
    release_status: CapabilityReleaseStatus


PRODUCT_CAPABILITY_REGISTRY: dict[str, ProductCapabilityDefinition] = {
    "whole_book.overview": ProductCapabilityDefinition(
        capability_id="whole_book.overview",
        display_name="全书总览",
        required_tier=AccessTier.free,
        release_status=CapabilityReleaseStatus.available,
    ),
    "whole_book.characters_events": ProductCapabilityDefinition(
        capability_id="whole_book.characters_events",
        display_name="主要人物与关键事件",
        required_tier=AccessTier.free,
        release_status=CapabilityReleaseStatus.available,
    ),
    "whole_book.structure": ProductCapabilityDefinition(
        capability_id="whole_book.structure",
        display_name="故事结构",
        required_tier=AccessTier.free,
        release_status=CapabilityReleaseStatus.available,
    ),
    "whole_book.chapter_functions": ProductCapabilityDefinition(
        capability_id="whole_book.chapter_functions",
        display_name="章节功能",
        required_tier=AccessTier.free,
        release_status=CapabilityReleaseStatus.planned,
    ),
    "whole_book.storylines": ProductCapabilityDefinition(
        capability_id="whole_book.storylines",
        display_name="故事线",
        required_tier=AccessTier.pro,
        release_status=CapabilityReleaseStatus.planned,
    ),
    "whole_book.character_arcs_relationships": ProductCapabilityDefinition(
        capability_id="whole_book.character_arcs_relationships",
        display_name="人物弧与关系",
        required_tier=AccessTier.pro,
        release_status=CapabilityReleaseStatus.planned,
    ),
    "whole_book.gcc_chain": ProductCapabilityDefinition(
        capability_id="whole_book.gcc_chain",
        display_name="GCC 链",
        required_tier=AccessTier.pro,
        release_status=CapabilityReleaseStatus.planned,
    ),
    "whole_book.hooks_foreshadow_payoff": ProductCapabilityDefinition(
        capability_id="whole_book.hooks_foreshadow_payoff",
        display_name="伏笔与回收",
        required_tier=AccessTier.pro,
        release_status=CapabilityReleaseStatus.planned,
    ),
    "whole_book.causality_timeline": ProductCapabilityDefinition(
        capability_id="whole_book.causality_timeline",
        display_name="因果时间线",
        required_tier=AccessTier.pro,
        release_status=CapabilityReleaseStatus.planned,
    ),
    "whole_book.reader_journey": ProductCapabilityDefinition(
        capability_id="whole_book.reader_journey",
        display_name="读者旅程",
        required_tier=AccessTier.pro,
        release_status=CapabilityReleaseStatus.planned,
    ),
    "whole_book.diagnosis": ProductCapabilityDefinition(
        capability_id="whole_book.diagnosis",
        display_name="诊断",
        required_tier=AccessTier.pro,
        release_status=CapabilityReleaseStatus.planned,
    ),
    "whole_book.enhanced": ProductCapabilityDefinition(
        capability_id="whole_book.enhanced",
        display_name="增强分析",
        required_tier=AccessTier.pro,
        release_status=CapabilityReleaseStatus.planned,
    ),
}


def _normalize_tier(access_tier: AccessTier | str) -> AccessTier:
    return access_tier if isinstance(access_tier, AccessTier) else AccessTier(access_tier)


def resolve_capability_access(
    capability_id: str,
    access_tier: AccessTier | str = AccessTier.free,
) -> dict[str, Any]:
    tier = _normalize_tier(access_tier)
    definition = PRODUCT_CAPABILITY_REGISTRY.get(capability_id)
    if definition is None:
        return {
            "capability_id": capability_id,
            "required_tier": AccessTier.free.value,
            "release_status": CapabilityReleaseStatus.planned.value,
            "access_status": CapabilityAccessStatus.locked.value,
            "reason_code": ProductCapabilityReasonCode.capability_unknown.value,
        }

    if definition.release_status == CapabilityReleaseStatus.planned:
        return {
            "capability_id": definition.capability_id,
            "display_name": definition.display_name,
            "required_tier": definition.required_tier.value,
            "release_status": definition.release_status.value,
            "access_status": CapabilityAccessStatus.planned.value,
            "reason_code": ProductCapabilityReasonCode.capability_planned.value,
        }

    if definition.required_tier == AccessTier.pro and tier != AccessTier.pro:
        return {
            "capability_id": definition.capability_id,
            "display_name": definition.display_name,
            "required_tier": definition.required_tier.value,
            "release_status": definition.release_status.value,
            "access_status": CapabilityAccessStatus.locked.value,
            "reason_code": ProductCapabilityReasonCode.pro_required.value,
        }

    return {
        "capability_id": definition.capability_id,
        "display_name": definition.display_name,
        "required_tier": definition.required_tier.value,
        "release_status": definition.release_status.value,
        "access_status": CapabilityAccessStatus.granted.value,
        "reason_code": None,
    }


def list_product_capabilities(access_tier: AccessTier | str = AccessTier.free) -> list[dict[str, Any]]:
    return [
        resolve_capability_access(definition.capability_id, access_tier)
        for definition in PRODUCT_CAPABILITY_REGISTRY.values()
    ]


def require_capability_access(
    capability_id: str,
    access_tier: AccessTier | str = AccessTier.free,
) -> dict[str, Any]:
    resolved = resolve_capability_access(capability_id, access_tier)
    if resolved["access_status"] != CapabilityAccessStatus.granted.value:
        reason = resolved.get("reason_code") or ProductCapabilityReasonCode.capability_unknown.value
        messages = {
            ProductCapabilityReasonCode.capability_planned.value: "该功能尚未开放",
            ProductCapabilityReasonCode.pro_required.value: "该功能需要 Pro 版本",
            ProductCapabilityReasonCode.capability_unknown.value: "未知的产品能力",
        }
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_CAPABILITY_DISABLED,
            messages.get(reason, "当前无法访问该功能"),
        )
    return resolved


def capability_to_dict(definition: ProductCapabilityDefinition) -> dict[str, Any]:
    return {
        "capability_id": definition.capability_id,
        "display_name": definition.display_name,
        "required_tier": definition.required_tier.value,
        "release_status": definition.release_status.value,
    }
