"""Frozen capability metadata registry (Phase 1C-P).

Public narrative asset APIs (entity/asset/relation storage) must NOT call Pro gating.
Only whole_book_analysis *runs* require CapabilityService evaluation.
"""

from __future__ import annotations

from app.narrative_core.contracts.capability import CapabilityMetadata, QuotaPolicy
from app.narrative_core.enums import (
    CapabilityAvailability,
    CapabilityKey,
    CostClass,
    QuotaPolicyKind,
    WholeBookAnalysisMode,
)

CAPABILITY_REGISTRY: dict[CapabilityKey, CapabilityMetadata] = {
    CapabilityKey.WHOLE_BOOK_ANALYSIS: CapabilityMetadata(
        key=CapabilityKey.WHOLE_BOOK_ANALYSIS,
        display_name="整书分析",
        description=(
            "全书结构化叙事分析流水线。"
            "Legacy internal capability key retained for compatibility. "
            "Current entitlement in StoryLens 1.1.x: whole_book_native + book_overview "
            "is FREE (see NativeOverviewService); whole_book_enhanced remains Pro "
            "and starts product-wise at 1.2.0. Capability still marked requires_license "
            "for Enhanced / future advanced modes — do not treat NATIVE overview as Pro-only."
        ),
        shipped=False,
        requires_license=True,
        availability=CapabilityAvailability.PREVIEW,
        preview_visible=True,
        supported_modes=(
            WholeBookAnalysisMode.NATIVE,
            WholeBookAnalysisMode.ENHANCED,
        ),
        quota_policy_key="whole_book_analysis_default",
        estimated_cost_class=CostClass.HIGH,
        quota_policies=(
            QuotaPolicy(
                kind=QuotaPolicyKind.PER_BOOK,
                policy_key="whole_book_per_book",
                limit=1,
                description="One active whole-book run per book snapshot",
            ),
            QuotaPolicy(
                kind=QuotaPolicyKind.CONCURRENT_RUNS,
                policy_key="whole_book_concurrent",
                limit=1,
            ),
        ),
        offline_allowed=False,
    ),
    CapabilityKey.NARRATIVE_ASSET_LIBRARY: CapabilityMetadata(
        key=CapabilityKey.NARRATIVE_ASSET_LIBRARY,
        display_name="叙事资产库",
        description="叙事实体/资产/关系存储基础层（免费基础；Pro 扩展未发货）。",
        shipped=False,
        requires_license=False,
        availability=CapabilityAvailability.UNAVAILABLE,
        preview_visible=False,
        estimated_cost_class=CostClass.FREE,
    ),
    CapabilityKey.STORY_LAB: CapabilityMetadata(
        key=CapabilityKey.STORY_LAB,
        display_name="故事实验台",
        description="实验性叙事探索（Pro；未发货）。",
        shipped=False,
        requires_license=True,
        availability=CapabilityAvailability.UNAVAILABLE,
        preview_visible=False,
        estimated_cost_class=CostClass.MEDIUM,
    ),
    CapabilityKey.CROSS_BOOK_SEARCH: CapabilityMetadata(
        key=CapabilityKey.CROSS_BOOK_SEARCH,
        display_name="跨书检索",
        description="跨作品叙事模式检索（Pro；未发货）。",
        shipped=False,
        requires_license=True,
        availability=CapabilityAvailability.UNAVAILABLE,
        preview_visible=False,
        estimated_cost_class=CostClass.MEDIUM,
    ),
    CapabilityKey.ADVANCED_EXPORT: CapabilityMetadata(
        key=CapabilityKey.ADVANCED_EXPORT,
        display_name="进阶导出",
        description="进阶结构化报告导出（Pro；未发货）。",
        shipped=False,
        requires_license=True,
        availability=CapabilityAvailability.UNAVAILABLE,
        preview_visible=False,
        estimated_cost_class=CostClass.LOW,
    ),
    CapabilityKey.PRO_WHOLE_BOOK_INSIGHTS: CapabilityMetadata(
        key=CapabilityKey.PRO_WHOLE_BOOK_INSIGHTS,
        display_name="章节聚合洞察",
        description=(
            "Chapter Asset Aggregation Insights / 章节聚合洞察："
            "基于已经完成的单章精细分析资产，对章节覆盖、阅读旅程、节奏、钩子、回报和章节功能进行聚合展示。"
            "不直接分析全书原文，也不表示原生整书/全书分析能力已完成。"
        ),
        shipped=True,
        requires_license=True,
        availability=CapabilityAvailability.AVAILABLE,
        preview_visible=True,
        estimated_cost_class=CostClass.MEDIUM,
        offline_allowed=True,
    ),
}


def get_capability_metadata(key: CapabilityKey | str) -> CapabilityMetadata:
    resolved = CapabilityKey(key) if isinstance(key, str) else key
    return CAPABILITY_REGISTRY[resolved]


def list_capability_metadata() -> list[CapabilityMetadata]:
    return list(CAPABILITY_REGISTRY.values())
