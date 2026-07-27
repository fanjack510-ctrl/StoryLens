"""Algorithm generality principles (Phase 2B-P contract documentation as code)."""

from __future__ import annotations

from typing import Mapping

GENERALITY_RULES: frozenset[str] = frozenset(
    {
        "no_book_specific_rules",
        "no_chapter_specific_special_branches",
        "no_single_work_weight_tuning",
        "no_single_work_threshold_tuning",
        "cross_genre_applicable",
        "single_instance_for_discovery_and_validation_only",
        "tuning_requires_multi_work_samples",
        "must_include_degraded_samples",
        "must_include_contrast_samples",
        "must_include_metamorphic_tests",
    }
)

ALLOWED_GENERIC_INPUT_DIFFERENCES: frozenset[str] = frozenset(
    {
        "length",
        "chapter_count",
        "language",
        "narrative_order",
        "viewpoint_count",
        "structure_complexity",
        "provider_context_limit",
    }
)

FORBIDDEN_BRANCH_KEY_TOKENS: frozenset[str] = frozenset(
    {
        "book_title",
        "title",
        "author",
        "author_name",
        "character_name",
        "protagonist_name",
        "plot_beat_name",
    }
)


def assert_no_book_identity_branch_keys(config: Mapping[str, object]) -> None:
    """Reject configuration maps that branch on book title/author/character names."""

    for key in config:
        lowered = str(key).lower()
        if lowered in FORBIDDEN_BRANCH_KEY_TOKENS:
            raise ValueError(f"book-identity branching key forbidden: {key}")
        if any(token in lowered for token in ("author:", "title:", "character:")):
            raise ValueError(f"book-identity branching key forbidden: {key}")


def assert_generality_rules_complete() -> None:
    if len(GENERALITY_RULES) != 10:
        raise ValueError("GENERALITY_RULES must document exactly 10 principles")
