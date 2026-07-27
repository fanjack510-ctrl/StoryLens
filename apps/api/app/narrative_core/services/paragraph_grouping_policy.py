"""Versioned Paragraph Grouping Policy (Phase 2B Integration / CHG-040).

Defaults (max=40, overlap=2) are generic initial values only — not locked by
multi-work evaluation. Never keyed by book title, character, or plot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Mapping

from app.narrative_core.private_engine_contract.context import GENERIC_LONG_CHAPTER_GROUPING
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineErrorCode,
    private_engine_error,
)

PARAGRAPH_GROUPING_POLICY_SCHEMA = "storylens.paragraph_grouping_policy"
PARAGRAPH_GROUPING_POLICY_VERSION = "1.0.0"

# Centralized defaults — mirrors GENERIC_LONG_CHAPTER_GROUPING initial values.
DEFAULT_MAX_PARAGRAPHS_PER_GROUP = int(
    GENERIC_LONG_CHAPTER_GROUPING["max_paragraphs_per_group"]
)
DEFAULT_OVERLAP_PARAGRAPHS = int(GENERIC_LONG_CHAPTER_GROUPING["overlap_paragraphs"])
DEFAULT_MAX_CHARACTERS_PER_GROUP = 12_000
DEFAULT_MAX_TOKENS_ESTIMATED = 3_000
DEFAULT_QUALITY_PROFILE_KEY = "balanced"


@dataclass(frozen=True, slots=True)
class ParagraphGroupingPolicy:
    """Configurable paragraph-window grouping for long chapters."""

    policy_schema: str = PARAGRAPH_GROUPING_POLICY_SCHEMA
    policy_version: str = PARAGRAPH_GROUPING_POLICY_VERSION
    max_paragraphs_per_group: int = DEFAULT_MAX_PARAGRAPHS_PER_GROUP
    overlap_paragraphs: int = DEFAULT_OVERLAP_PARAGRAPHS
    max_characters_per_group: int = DEFAULT_MAX_CHARACTERS_PER_GROUP
    max_tokens_estimated: int = DEFAULT_MAX_TOKENS_ESTIMATED
    preserve_scene_boundaries: bool = True
    preserve_chapter_boundaries: bool = True
    provider_context_limit: int | None = None
    quality_profile_key: str = DEFAULT_QUALITY_PROFILE_KEY

    def __post_init__(self) -> None:
        if self.policy_schema != PARAGRAPH_GROUPING_POLICY_SCHEMA:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="grouping_policy_schema_mismatch",
            )
        if self.max_paragraphs_per_group < 1:
            raise ValueError("max_paragraphs_per_group must be >= 1")
        if self.overlap_paragraphs < 0:
            raise ValueError("overlap_paragraphs must be >= 0")
        if self.overlap_paragraphs >= self.max_paragraphs_per_group:
            raise ValueError("overlap_paragraphs must be < max_paragraphs_per_group")
        if self.max_characters_per_group < 1:
            raise ValueError("max_characters_per_group must be >= 1")
        if self.max_tokens_estimated < 1:
            raise ValueError("max_tokens_estimated must be >= 1")

    def to_grouping_dict(self) -> dict[str, Any]:
        """Dict consumed by ContextUnitBuilder / configuration fingerprint."""

        effective_max = self.max_paragraphs_per_group
        if self.provider_context_limit is not None and self.provider_context_limit > 0:
            # Provider context limit may shrink groups (never expand).
            if self.provider_context_limit < self.max_tokens_estimated:
                ratio = self.provider_context_limit / max(1, self.max_tokens_estimated)
                effective_max = max(1, int(self.max_paragraphs_per_group * ratio))
            if self.overlap_paragraphs >= effective_max:
                effective_max = self.overlap_paragraphs + 1
        overlap = min(self.overlap_paragraphs, max(0, effective_max - 1))
        return {
            "strategy": "paragraph_window",
            "policy_schema": self.policy_schema,
            "policy_version": self.policy_version,
            "max_paragraphs_per_group": effective_max,
            "overlap_paragraphs": overlap,
            "max_characters_per_group": self.max_characters_per_group,
            "max_tokens_estimated": self.max_tokens_estimated,
            "preserve_scene_boundaries": self.preserve_scene_boundaries,
            "preserve_chapter_boundaries": self.preserve_chapter_boundaries,
            "provider_context_limit": self.provider_context_limit,
            "quality_profile_key": self.quality_profile_key,
            "book_specific_branches_forbidden": True,
            "defaults_are_initial_only": True,
        }

    def fingerprint_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def default(cls) -> ParagraphGroupingPolicy:
        return cls()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> ParagraphGroupingPolicy:
        if not data:
            return cls.default()
        allowed = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in allowed}
        return cls(**kwargs)

    def with_overrides(self, **overrides: Any) -> ParagraphGroupingPolicy:
        base = asdict(self)
        base.update(overrides)
        return ParagraphGroupingPolicy.from_mapping(base)


def default_paragraph_grouping_policy() -> ParagraphGroupingPolicy:
    return ParagraphGroupingPolicy.default()


__all__ = [
    "DEFAULT_MAX_PARAGRAPHS_PER_GROUP",
    "DEFAULT_OVERLAP_PARAGRAPHS",
    "PARAGRAPH_GROUPING_POLICY_SCHEMA",
    "PARAGRAPH_GROUPING_POLICY_VERSION",
    "ParagraphGroupingPolicy",
    "default_paragraph_grouping_policy",
]
