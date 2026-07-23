"""Evaluation suite / metamorphic fixtures (Phase 2B-P).

Synthetic short fixtures only — no copyrighted novels.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class EvaluationSampleCategory(StrEnum):
    LINEAR_LONGFORM = "linear_longform"
    MULTI_THREAD = "multi_thread"
    MULTI_POV = "multi_pov"
    FLASHBACK_NONLINEAR = "flashback_nonlinear"
    SHORT_STORY = "short_story"
    ULTRA_LONG_CHAPTER = "ultra_long_chapter"
    SIDE_STORY = "side_story"
    MISSING_CHAPTERS = "missing_chapters"
    DUPLICATE_CHAPTERS = "duplicate_chapters"
    DEGRADED_TEXT = "degraded_text"
    LANGUAGE_ZH = "language_zh"
    LANGUAGE_EN = "language_en"
    LANGUAGE_MIXED = "language_mixed"


class EvaluationDimension(StrEnum):
    SCHEMA_VALIDITY = "schema_validity"
    SNAPSHOT_INTEGRITY = "snapshot_integrity"
    EVIDENCE_INTEGRITY = "evidence_integrity"
    EVIDENCE_COVERAGE = "evidence_coverage"
    REFERENCE_VALIDITY = "reference_validity"
    BOOK_ISOLATION = "book_isolation"
    MODULE_COMPLETENESS = "module_completeness"
    CONTRADICTION_RATE = "contradiction_rate"
    DUPLICATE_RATE = "duplicate_rate"
    CROSS_RUN_STABILITY = "cross_run_stability"
    PARTIAL_RECOVERY = "partial_recovery"
    COST_TOKEN = "cost_token"
    LATENCY = "latency"
    USER_CORRECTION_RATE = "user_correction_rate"


class MetamorphicTransformKind(StrEnum):
    CHAPTER_TITLE_NOISE = "chapter_title_noise"
    WHITESPACE_NEWLINE = "whitespace_newline"
    CHAPTER_RENUMBER_SAME_CONTENT = "chapter_renumber_same_content"
    IRRELEVANT_PREFACE = "irrelevant_preface"
    SUMMARY_PARAPHRASE_EVIDENCE_STABLE = "summary_paraphrase_evidence_stable"
    ENHANCED_ASSETS_MISSING_DEGRADE = "enhanced_assets_missing_degrade"
    MODULE_ORDER_CHANGE = "module_order_change"
    RESUME_NO_DUPLICATE = "resume_no_duplicate"


@dataclass(frozen=True, slots=True)
class WholeBookEvaluationCase:
    case_id: str
    category: EvaluationSampleCategory
    title: str
    synthetic_fixture_ref: str
    copyrighted_novel: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if self.copyrighted_novel:
            raise ValueError("copyrighted novels are forbidden in Phase 2B-P fixtures")
        if not self.synthetic_fixture_ref.startswith("synthetic://"):
            raise ValueError("evaluation fixtures must use synthetic:// refs")


@dataclass(frozen=True, slots=True)
class MetamorphicEvaluationCase:
    case_id: str
    base_case_id: str
    transform: MetamorphicTransformKind
    expectation: str
    synthetic_fixture_ref: str


@dataclass(frozen=True, slots=True)
class WholeBookEvaluationResult:
    case_id: str
    passed: bool
    dimension_scores: Mapping[str, float]
    warnings: tuple[str, ...] = ()
    fake: bool = True


@dataclass(frozen=True, slots=True)
class WholeBookEvaluationSuite:
    suite_id: str
    version: str
    cases: tuple[WholeBookEvaluationCase, ...]
    metamorphic_cases: tuple[MetamorphicEvaluationCase, ...]
    dimensions: tuple[EvaluationDimension, ...]
    non_production: bool = True

    def __post_init__(self) -> None:
        if not self.non_production:
            raise ValueError("evaluation suite fixtures are non_production in Phase 2B-P")


SAMPLE_CATEGORIES: frozenset[str] = frozenset(c.value for c in EvaluationSampleCategory)
EVALUATION_DIMENSIONS: frozenset[str] = frozenset(d.value for d in EvaluationDimension)


def fake_evaluation_suite() -> WholeBookEvaluationSuite:
    cases = (
        WholeBookEvaluationCase(
            case_id="syn-zh-short-1",
            category=EvaluationSampleCategory.SHORT_STORY,
            title="Synthetic Short ZH",
            synthetic_fixture_ref="synthetic://short/zh/1",
        ),
        WholeBookEvaluationCase(
            case_id="syn-en-short-1",
            category=EvaluationSampleCategory.LANGUAGE_EN,
            title="Synthetic Short EN",
            synthetic_fixture_ref="synthetic://short/en/1",
        ),
        WholeBookEvaluationCase(
            case_id="syn-multi-thread-1",
            category=EvaluationSampleCategory.MULTI_THREAD,
            title="Synthetic Multi Thread",
            synthetic_fixture_ref="synthetic://multi_thread/1",
        ),
        WholeBookEvaluationCase(
            case_id="syn-long-chapter-1",
            category=EvaluationSampleCategory.ULTRA_LONG_CHAPTER,
            title="Synthetic Ultra Long Chapter",
            synthetic_fixture_ref="synthetic://ultra_long_chapter/1",
        ),
        WholeBookEvaluationCase(
            case_id="syn-degraded-1",
            category=EvaluationSampleCategory.DEGRADED_TEXT,
            title="Synthetic Degraded Text",
            synthetic_fixture_ref="synthetic://degraded/1",
        ),
    )
    metamorphic = (
        MetamorphicEvaluationCase(
            case_id="meta-whitespace-1",
            base_case_id="syn-zh-short-1",
            transform=MetamorphicTransformKind.WHITESPACE_NEWLINE,
            expectation="evidence_hashes_stable",
            synthetic_fixture_ref="synthetic://meta/whitespace/1",
        ),
        MetamorphicEvaluationCase(
            case_id="meta-renumber-1",
            base_case_id="syn-zh-short-1",
            transform=MetamorphicTransformKind.CHAPTER_RENUMBER_SAME_CONTENT,
            expectation="paragraph_stable_ids_hold",
            synthetic_fixture_ref="synthetic://meta/renumber/1",
        ),
        MetamorphicEvaluationCase(
            case_id="meta-enhanced-degrade-1",
            base_case_id="syn-multi-thread-1",
            transform=MetamorphicTransformKind.ENHANCED_ASSETS_MISSING_DEGRADE,
            expectation="degrade_with_warnings",
            synthetic_fixture_ref="synthetic://meta/enhanced_degrade/1",
        ),
        MetamorphicEvaluationCase(
            case_id="meta-resume-1",
            base_case_id="syn-en-short-1",
            transform=MetamorphicTransformKind.RESUME_NO_DUPLICATE,
            expectation="no_duplicate_candidates",
            synthetic_fixture_ref="synthetic://meta/resume/1",
        ),
    )
    return WholeBookEvaluationSuite(
        suite_id="fake.whole_book.evaluation",
        version="0.0.1-fake",
        cases=cases,
        metamorphic_cases=metamorphic,
        dimensions=tuple(EvaluationDimension),
        non_production=True,
    )


def fake_evaluation_results(suite: WholeBookEvaluationSuite | None = None) -> tuple[WholeBookEvaluationResult, ...]:
    suite = suite or fake_evaluation_suite()
    return tuple(
        WholeBookEvaluationResult(
            case_id=case.case_id,
            passed=True,
            dimension_scores={EvaluationDimension.SCHEMA_VALIDITY.value: 1.0},
            warnings=("fake",),
            fake=True,
        )
        for case in suite.cases
    )
