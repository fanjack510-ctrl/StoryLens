"""Source language vs output locale contract (Phase 2B-P)."""

from __future__ import annotations

from enum import StrEnum


class SourceLanguage(StrEnum):
    AUTO = "auto"
    ZH = "zh"
    EN = "en"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class OutputLocale(StrEnum):
    ZH_CN = "zh-CN"
    EN_US = "en-US"


LANGUAGE_SEPARATION_RULES: frozenset[str] = frozenset(
    {
        "source_language_separate_from_output_locale",
        "zh_source_may_output_en_report",
        "en_source_may_output_zh_report",
        "entity_names_must_not_be_mistranslated_as_new_entities",
        "evidence_preview_keeps_original_text",
        "analysis_explanations_follow_output_locale",
        "module_keys_always_stable_english",
        "no_dual_language_fact_tables",
    }
)


def assert_language_locale_separated(source_language: str, output_locale: str) -> None:
    SourceLanguage(source_language)
    OutputLocale(output_locale)
    # Separation means they are independently chosen — equality is allowed but not required.
    if source_language in {o.value for o in OutputLocale}:
        raise ValueError("source_language must not use output_locale values")
