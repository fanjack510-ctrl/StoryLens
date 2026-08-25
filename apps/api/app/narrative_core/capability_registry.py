"""Frozen capability metadata registry (Phase 1C-P + WB-0.3).

Public narrative asset APIs (entity/asset/relation storage) must NOT call Pro gating.
Whole-book product entries remain disabled until a later release gate.
"""

from __future__ import annotations

from app.narrative_core.contracts.capability import CapabilityMetadata, QuotaPolicy
from app.narrative_core.enums import (
    CapabilityAvailability,
    CapabilityKey,
    CapabilityReasonCode,
    CostClass,
    QuotaPolicyKind,
    WholeBookAnalysisMode,
)

_NOT_RELEASED = CapabilityReasonCode.WHOLE_BOOK_NOT_RELEASED.value

CAPABILITY_REGISTRY: dict[CapabilityKey, CapabilityMetadata] = {
    CapabilityKey.WHOLE_BOOK_ANALYSIS: CapabilityMetadata(
        key=CapabilityKey.WHOLE_BOOK_ANALYSIS,
        display_name="整书分析（Legacy）",
        description=(
            "Legacy internal whole-book analysis capability key retained for compatibility. "
            "Prefer whole_book_native / whole_book_enhanced for product semantics."
        ),
        shipped=False,
        requires_license=True,
        availability=CapabilityAvailability.UNAVAILABLE,
        preview_visible=False,
        enabled=False,
        entry_visible=False,
        product_reason_code=_NOT_RELEASED,
        minimum_version="1.2.0",
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
        enabled=False,
        entry_visible=False,
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
        enabled=False,
        entry_visible=False,
        estimated_cost_class=CostClass.MEDIUM,
    ),
    CapabilityKey.CROSS_BOOK_SEARCH: CapabilityMetadata(
        key=CapabilityKey.CROSS_BOOK_SEARCH,
        display_name="找相似写法",
        description=(
            "在所有分析过的书里找东西。关键词检索免费——它确定、即时、可核对，"
            "而且覆盖全部条目；付费的是「找相似写法」：用自己的话描述要找的写法，"
            "由模型在写法层里挑出来并说明为什么符合。"
        ),
        shipped=True,
        requires_license=True,
        availability=CapabilityAvailability.AVAILABLE,
        preview_visible=True,
        enabled=True,
        entry_visible=True,
        # 一次调用，输入是写法层条目（实测三本书约四千 token）。
        estimated_cost_class=CostClass.LOW,
    ),
    CapabilityKey.ADVANCED_EXPORT: CapabilityMetadata(
        key=CapabilityKey.ADVANCED_EXPORT,
        display_name="进阶导出",
        description="全书分析报告 PDF 导出（Pro，支持爱发电授权）。",
        shipped=True,
        requires_license=True,
        availability=CapabilityAvailability.AVAILABLE,
        preview_visible=True,
        enabled=True,
        entry_visible=True,
        estimated_cost_class=CostClass.LOW,
    ),
    CapabilityKey.COMMON_PATTERNS: CapabilityMetadata(
        key=CapabilityKey.COMMON_PATTERNS,
        display_name="共性视图",
        description=(
            "把一组书摆在一起，看它们共同做对了什么（Pro）。"
            "数出来的那一屏——类型分布、每本读到第几章、哪几本还没拆过文——保持免费；"
            "付费的是把这些书归纳成共同手法这一步。"
        ),
        shipped=True,
        requires_license=True,
        availability=CapabilityAvailability.AVAILABLE,
        preview_visible=True,
        enabled=True,
        entry_visible=True,
        # 一次调用，输入是十几本书的技法清单，几千 token。
        estimated_cost_class=CostClass.LOW,
    ),
    CapabilityKey.KNOWLEDGE_EXTRACTION: CapabilityMetadata(
        key=CapabilityKey.KNOWLEDGE_EXTRACTION,
        display_name="从全书提取素材",
        description=(
            "从已经完成全文拆文的小说中，按题材与固定分类提取少量、可核对的知识素材（Pro）。"
            "浏览、筛选和搜索已经存在的知识保持免费。"
        ),
        shipped=True,
        requires_license=True,
        availability=CapabilityAvailability.AVAILABLE,
        preview_visible=True,
        enabled=True,
        entry_visible=True,
        estimated_cost_class=CostClass.LOW,
        offline_allowed=True,
    ),
    CapabilityKey.BOOK_SKILL_GENERATION: CapabilityMetadata(
        key=CapabilityKey.BOOK_SKILL_GENERATION,
        display_name="生成作品 Skill",
        description=(
            "把一部已完成全文拆文的小说整理为可下载的创作机制 Skill（Pro）。"
            "只迁移结构与机制，不复制原文和专有设定。"
        ),
        shipped=True,
        requires_license=True,
        availability=CapabilityAvailability.AVAILABLE,
        preview_visible=True,
        enabled=True,
        entry_visible=True,
        estimated_cost_class=CostClass.LOW,
        offline_allowed=True,
    ),
    CapabilityKey.PRO_WHOLE_BOOK_INSIGHTS: CapabilityMetadata(
        key=CapabilityKey.PRO_WHOLE_BOOK_INSIGHTS,
        display_name="章节精细分析覆盖（Legacy key）",
        description=(
            "Legacy key for chapter-aggregate insights. Canonical product id is "
            "chapter_aggregate_insights. This is NOT native whole-book analysis."
        ),
        shipped=True,
        requires_license=True,
        availability=CapabilityAvailability.AVAILABLE,
        preview_visible=False,
        enabled=False,
        entry_visible=False,
        product_reason_code=_NOT_RELEASED,
        minimum_version="1.1.0",
        estimated_cost_class=CostClass.MEDIUM,
        offline_allowed=True,
    ),
    CapabilityKey.WHOLE_BOOK_NATIVE: CapabilityMetadata(
        key=CapabilityKey.WHOLE_BOOK_NATIVE,
        display_name="原生全书分析",
        description=(
            "直接以完整 Book Snapshot 为唯一事实源进行全书分析。"
            "不得与章节聚合洞察混用。"
        ),
        shipped=False,
        requires_license=False,
        availability=CapabilityAvailability.UNAVAILABLE,
        preview_visible=False,
        enabled=False,
        entry_visible=False,
        product_reason_code=_NOT_RELEASED,
        minimum_version="1.2.0",
        supported_modes=(WholeBookAnalysisMode.NATIVE,),
        estimated_cost_class=CostClass.HIGH,
        offline_allowed=False,
    ),
    CapabilityKey.WHOLE_BOOK_ENHANCED: CapabilityMetadata(
        key=CapabilityKey.WHOLE_BOOK_ENHANCED,
        display_name="精细增强分析",
        description=(
            "以完整 Book Snapshot 为事实源，同时允许使用已有单章资产和已确认全书资产增强。"
            "增强不得替代完整原文 Snapshot。"
        ),
        shipped=False,
        requires_license=True,
        availability=CapabilityAvailability.UNAVAILABLE,
        preview_visible=False,
        enabled=False,
        entry_visible=False,
        product_reason_code=_NOT_RELEASED,
        minimum_version="1.2.0",
        supported_modes=(WholeBookAnalysisMode.ENHANCED,),
        estimated_cost_class=CostClass.HIGH,
        offline_allowed=False,
    ),
    CapabilityKey.CHAPTER_AGGREGATE_INSIGHTS: CapabilityMetadata(
        key=CapabilityKey.CHAPTER_AGGREGATE_INSIGHTS,
        display_name="章节精细分析覆盖",
        description=(
            "汇总已完成的单章分析结果，不属于原生全书分析。"
            "正式入口保持隐藏。"
        ),
        shipped=True,
        requires_license=True,
        availability=CapabilityAvailability.AVAILABLE,
        preview_visible=False,
        enabled=False,
        entry_visible=False,
        product_reason_code=_NOT_RELEASED,
        minimum_version="1.1.0",
        estimated_cost_class=CostClass.MEDIUM,
        offline_allowed=True,
    ),
}


def get_capability_metadata(key: CapabilityKey | str) -> CapabilityMetadata:
    resolved = CapabilityKey(key) if isinstance(key, str) else key
    return CAPABILITY_REGISTRY[resolved]


def list_capability_metadata() -> list[CapabilityMetadata]:
    return list(CAPABILITY_REGISTRY.values())
