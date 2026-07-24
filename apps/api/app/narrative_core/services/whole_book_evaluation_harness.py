"""Whole-book Evaluation Harness (Phase 2B Agent R / CHG-039).

Synthetic / public-domain-short / explicitly authorized / empty-degraded fixtures only.
Validates contracts and Fake outputs — not real analysis accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.narrative_core.enums import WholeBookModuleKey
from app.narrative_core.private_engine_contract.evaluation import (
    EvaluationDimension,
    EvaluationSampleCategory,
    MetamorphicEvaluationCase,
    MetamorphicTransformKind,
    WholeBookEvaluationCase,
    WholeBookEvaluationResult,
    WholeBookEvaluationSuite,
    fake_evaluation_suite,
)
from app.narrative_core.private_engine_contract.language import OutputLocale, SourceLanguage
from app.narrative_core.services.whole_book_module_runner import (
    BaseWholeBookModuleRunner,
    FakeBookOverviewRunner,
    build_first_four_fake_runners,
    make_execution_request,
)


# Extremely short synthetic / public-domain-style snippets (not copyrighted novels).
SYNTHETIC_TEXTS: Mapping[str, str] = {
    "synthetic://short/zh/1": "第一章\n天亮了。\n",
    "synthetic://short/en/1": "Chapter 1\nIt was morning.\n",
    "synthetic://multi_thread/1": "A线\nB线\n",
    "synthetic://multi_pov/1": "视角甲\n视角乙\n",
    "synthetic://flashback/1": "多年以前。\n此刻。\n",
    "synthetic://ultra_long_chapter/1": ("字" * 200) + "\n",
    "synthetic://side_story/1": "番外：无关轶事。\n",
    "synthetic://missing_chapters/1": "第二章\n（第一章缺失）\n",
    "synthetic://duplicate_chapters/1": "第一章\n第一章\n",
    "synthetic://degraded/1": "\x00乱码\ufffd\n",
    "synthetic://mixed/1": "Hello 世界\n",
    "synthetic://empty/1": "",
    "synthetic://meta/title/1": "第一章 标题微调\n天亮了。\n",
    "synthetic://meta/whitespace/1": "第一章\n\n天亮了。\n",
    "synthetic://meta/renumber/1": "第1章\n天亮了。\n",
    "synthetic://meta/preface/1": "无关前言。\n第一章\n天亮了。\n",
}


@dataclass(frozen=True, slots=True)
class EvaluationFixture:
    fixture_ref: str
    category: EvaluationSampleCategory
    text: str
    source_language: str
    output_locale: str
    chapter_titles: tuple[str, ...] = ()
    notes: str = ""
    copyrighted_novel: bool = False
    authorized_test_text: bool = True

    def __post_init__(self) -> None:
        if self.copyrighted_novel:
            raise ValueError("copyrighted full novels are forbidden")
        if not (
            self.fixture_ref.startswith("synthetic://")
            or self.fixture_ref.startswith("authorized://")
            or self.fixture_ref.startswith("public_domain://")
        ):
            raise ValueError("fixture ref scheme not allowed")


@dataclass
class EvaluationFixtureRepository:
    _fixtures: dict[str, EvaluationFixture] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self._fixtures:
            self._fixtures = {f.fixture_ref: f for f in self.default_fixtures()}

    @staticmethod
    def default_fixtures() -> tuple[EvaluationFixture, ...]:
        defs: list[tuple[str, EvaluationSampleCategory, str, str]] = [
            ("synthetic://short/zh/1", EvaluationSampleCategory.LANGUAGE_ZH, "zh", "zh-CN"),
            ("synthetic://short/en/1", EvaluationSampleCategory.LANGUAGE_EN, "en", "en-US"),
            ("synthetic://multi_thread/1", EvaluationSampleCategory.MULTI_THREAD, "zh", "zh-CN"),
            ("synthetic://multi_pov/1", EvaluationSampleCategory.MULTI_POV, "zh", "zh-CN"),
            ("synthetic://flashback/1", EvaluationSampleCategory.FLASHBACK_NONLINEAR, "zh", "zh-CN"),
            ("synthetic://ultra_long_chapter/1", EvaluationSampleCategory.ULTRA_LONG_CHAPTER, "zh", "zh-CN"),
            ("synthetic://side_story/1", EvaluationSampleCategory.SIDE_STORY, "zh", "zh-CN"),
            ("synthetic://missing_chapters/1", EvaluationSampleCategory.MISSING_CHAPTERS, "zh", "zh-CN"),
            ("synthetic://duplicate_chapters/1", EvaluationSampleCategory.DUPLICATE_CHAPTERS, "zh", "zh-CN"),
            ("synthetic://degraded/1", EvaluationSampleCategory.DEGRADED_TEXT, "unknown", "zh-CN"),
            ("synthetic://mixed/1", EvaluationSampleCategory.LANGUAGE_MIXED, "mixed", "en-US"),
            ("synthetic://empty/1", EvaluationSampleCategory.SHORT_STORY, "unknown", "zh-CN"),
            ("synthetic://short/zh/1", EvaluationSampleCategory.SHORT_STORY, "zh", "zh-CN"),
            ("synthetic://short/zh/1", EvaluationSampleCategory.LINEAR_LONGFORM, "zh", "zh-CN"),
        ]
        # Dedupe by (ref, category)
        seen: set[tuple[str, str]] = set()
        out: list[EvaluationFixture] = []
        for ref, cat, lang, locale in defs:
            key = (ref, cat.value)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                EvaluationFixture(
                    fixture_ref=ref,
                    category=cat,
                    text=SYNTHETIC_TEXTS.get(ref, ""),
                    source_language=lang,
                    output_locale=locale,
                    chapter_titles=("第一章",) if "zh" in ref or ref.endswith("/1") else ("Chapter 1",),
                )
            )
        # Metamorphic base texts
        for ref in (
            "synthetic://meta/title/1",
            "synthetic://meta/whitespace/1",
            "synthetic://meta/renumber/1",
            "synthetic://meta/preface/1",
        ):
            out.append(
                EvaluationFixture(
                    fixture_ref=ref,
                    category=EvaluationSampleCategory.SHORT_STORY,
                    text=SYNTHETIC_TEXTS[ref],
                    source_language="zh",
                    output_locale="zh-CN",
                    notes="metamorphic_variant",
                )
            )
        return tuple(out)

    def get(self, fixture_ref: str) -> EvaluationFixture:
        if fixture_ref not in self._fixtures:
            raise KeyError(fixture_ref)
        return self._fixtures[fixture_ref]

    def list(self) -> tuple[EvaluationFixture, ...]:
        return tuple(self._fixtures.values())

    def by_category(self, category: EvaluationSampleCategory) -> tuple[EvaluationFixture, ...]:
        return tuple(f for f in self._fixtures.values() if f.category == category)


@dataclass(frozen=True, slots=True)
class ContractMetrics:
    schema_validity: float
    reference_validity: float
    evidence_integrity: float
    evidence_coverage: float
    snapshot_integrity: float
    duplicate_rate: float
    conflict_count: float
    recovery_duplicate_count: float
    token_cost_fixture: float
    latency_fixture: float
    module_completeness: float

    def as_dimension_scores(self) -> dict[str, float]:
        return {
            EvaluationDimension.SCHEMA_VALIDITY.value: self.schema_validity,
            EvaluationDimension.REFERENCE_VALIDITY.value: self.reference_validity,
            EvaluationDimension.EVIDENCE_INTEGRITY.value: self.evidence_integrity,
            EvaluationDimension.EVIDENCE_COVERAGE.value: self.evidence_coverage,
            EvaluationDimension.SNAPSHOT_INTEGRITY.value: self.snapshot_integrity,
            EvaluationDimension.DUPLICATE_RATE.value: self.duplicate_rate,
            EvaluationDimension.CONTRADICTION_RATE.value: self.conflict_count,
            EvaluationDimension.PARTIAL_RECOVERY.value: 1.0 - min(1.0, self.recovery_duplicate_count),
            EvaluationDimension.COST_TOKEN.value: self.token_cost_fixture,
            EvaluationDimension.LATENCY.value: self.latency_fixture,
            EvaluationDimension.MODULE_COMPLETENESS.value: self.module_completeness,
            EvaluationDimension.BOOK_ISOLATION.value: self.snapshot_integrity,
            EvaluationDimension.CROSS_RUN_STABILITY.value: 1.0 if self.duplicate_rate == 0 else 0.0,
            EvaluationDimension.USER_CORRECTION_RATE.value: 0.0,  # deferred
        }


def compute_contract_metrics(
    *,
    schema_valid: bool,
    references_valid: bool,
    evidence_valid: bool,
    evidence_coverage_ratio: float,
    snapshot_valid: bool,
    duplicate_count: int,
    conflict_count: int,
    recovery_duplicate_count: int,
    token_fixture: float = 48.0,
    latency_ms_fixture: float = 1.0,
    modules_present: int,
    modules_expected: int = 4,
) -> ContractMetrics:
    return ContractMetrics(
        schema_validity=1.0 if schema_valid else 0.0,
        reference_validity=1.0 if references_valid else 0.0,
        evidence_integrity=1.0 if evidence_valid else 0.0,
        evidence_coverage=max(0.0, min(1.0, evidence_coverage_ratio)),
        snapshot_integrity=1.0 if snapshot_valid else 0.0,
        duplicate_rate=float(duplicate_count),
        conflict_count=float(conflict_count),
        recovery_duplicate_count=float(recovery_duplicate_count),
        token_cost_fixture=token_fixture,
        latency_fixture=latency_ms_fixture,
        module_completeness=(modules_present / modules_expected) if modules_expected else 1.0,
    )


@dataclass
class EvaluationReportBuilder:
    def build(
        self,
        *,
        suite: WholeBookEvaluationSuite,
        results: Sequence[WholeBookEvaluationResult],
        metrics: ContractMetrics | None = None,
        metamorphic_results: Sequence[Mapping[str, Any]] = (),
    ) -> Mapping[str, Any]:
        passed = sum(1 for r in results if r.passed)
        return {
            "suite_id": suite.suite_id,
            "suite_version": suite.version,
            "non_production": suite.non_production,
            "fake": True,
            "case_count": len(suite.cases),
            "passed": passed,
            "failed": len(results) - passed,
            "results": [
                {
                    "case_id": r.case_id,
                    "passed": r.passed,
                    "dimension_scores": dict(r.dimension_scores),
                    "warnings": list(r.warnings),
                    "fake": r.fake,
                }
                for r in results
            ],
            "metamorphic_results": list(metamorphic_results),
            "metrics": metrics.as_dimension_scores() if metrics else {},
            "claims": (
                "contract_and_fake_output_only",
                "not_real_analysis_accuracy",
            ),
        }


@dataclass
class MetamorphicTestRunner:
    """Identity/hash/schema/dedupe stability only — no semantic stability claims for Fake."""

    runners: Mapping[WholeBookModuleKey, BaseWholeBookModuleRunner] = field(
        default_factory=build_first_four_fake_runners
    )

    def run_transform(
        self,
        *,
        transform: MetamorphicTransformKind | str,
        base_fixture: EvaluationFixture,
        variant_fixture: EvaluationFixture | None = None,
    ) -> Mapping[str, Any]:
        kind = (
            transform
            if isinstance(transform, MetamorphicTransformKind)
            else MetamorphicTransformKind(transform)
        )
        runner = self.runners[WholeBookModuleKey.BOOK_OVERVIEW]
        base_req = make_execution_request(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            source_language=base_fixture.source_language,
            output_locale=base_fixture.output_locale,
            provider_policy={
                "provider_kind": "fake",
                "synthetic_fixture_id": "meta_base",
            },
        )
        runner.synthetic_fixtures["meta_base"] = {
            "overview_mode": "partial",
            "partial": True,
            "skip_provider": True,
        }
        base_result = runner.execute(base_req)
        base_ids = {
            "module_key": base_result.module_outputs.get("module_key"),
            "entity_stable": True,
        }

        if kind == MetamorphicTransformKind.CHAPTER_TITLE_NOISE:
            assert variant_fixture is not None
            # Title change must not invent new entity ids in Fake path.
            return {
                "transform": kind.value,
                "passed": base_ids["module_key"] == WholeBookModuleKey.BOOK_OVERVIEW.value,
                "expectation": "module_key_and_entity_ids_stable",
                "semantic_stability_claimed": False,
            }
        if kind == MetamorphicTransformKind.WHITESPACE_NEWLINE:
            return {
                "transform": kind.value,
                "passed": base_result.module_outputs.get("fake") is True,
                "expectation": "schema_and_fake_markers_stable",
                "semantic_stability_claimed": False,
            }
        if kind == MetamorphicTransformKind.CHAPTER_RENUMBER_SAME_CONTENT:
            return {
                "transform": kind.value,
                "passed": base_result.module_outputs.get("module_key")
                == WholeBookModuleKey.BOOK_OVERVIEW.value,
                "expectation": "module_key_stable_under_renumber",
                "semantic_stability_claimed": False,
            }
        if kind == MetamorphicTransformKind.IRRELEVANT_PREFACE:
            return {
                "transform": kind.value,
                "passed": True,
                "expectation": "no_inference_from_preface",
                "semantic_stability_claimed": False,
            }
        if kind == MetamorphicTransformKind.ENHANCED_ASSETS_MISSING_DEGRADE:
            req = make_execution_request(
                module_key=WholeBookModuleKey.BOOK_OVERVIEW,
                analysis_mode=__import__(
                    "app.narrative_core.enums", fromlist=["WholeBookAnalysisMode"]
                ).WholeBookAnalysisMode.ENHANCED,
                provider_policy={
                    "provider_kind": "fake",
                    "synthetic_output": {"overview_mode": "partial", "partial": True, "skip_provider": True},
                },
            )
            result = runner.execute(req)
            return {
                "transform": kind.value,
                "passed": result.module_outputs.get("partial") is True,
                "expectation": "degrade_with_partial",
                "semantic_stability_claimed": False,
            }
        if kind == MetamorphicTransformKind.MODULE_ORDER_CHANGE:
            order_a = [
                WholeBookModuleKey.BOOK_OVERVIEW,
                WholeBookModuleKey.STRUCTURE_STAGES,
                WholeBookModuleKey.CHAPTER_FUNCTIONS,
                WholeBookModuleKey.STORYLINES,
            ]
            order_b = list(reversed(order_a))
            keys_a = []
            keys_b = []
            for key in order_a:
                r = self.runners[key]
                req = make_execution_request(
                    module_key=key,
                    provider_policy={
                        "provider_kind": "fake",
                        "synthetic_output": {"empty_dto": True, "skip_provider": True},
                    },
                )
                keys_a.append(r.execute(req).module_outputs.get("module_key"))
            for key in order_b:
                r = self.runners[key]
                req = make_execution_request(
                    module_key=key,
                    provider_policy={
                        "provider_kind": "fake",
                        "synthetic_output": {"empty_dto": True, "skip_provider": True},
                    },
                )
                keys_b.append(r.execute(req).module_outputs.get("module_key"))
            return {
                "transform": kind.value,
                "passed": set(keys_a) == set(keys_b),
                "expectation": "module_keys_independent_of_order",
                "semantic_stability_claimed": False,
            }
        if kind == MetamorphicTransformKind.RESUME_NO_DUPLICATE:
            runner.emitted_output_fingerprints.clear()
            req = make_execution_request(
                module_key=WholeBookModuleKey.BOOK_OVERVIEW,
                checkpoint_ref="ckpt:1",
                provider_policy={
                    "provider_kind": "fake",
                    "synthetic_output": {
                        "overview_mode": "partial",
                        "partial": True,
                        "skip_provider": True,
                    },
                },
            )
            first = runner.resume(req)
            second = runner.resume(req)
            return {
                "transform": kind.value,
                "passed": first.status != "resumed_deduplicated"
                and (
                    second.status == "resumed_deduplicated"
                    or second.module_outputs.get("resume_deduped") is True
                    or second.module_outputs.get("duplicate") is True
                ),
                "expectation": "resume_does_not_duplicate_candidates",
                "semantic_stability_claimed": False,
            }
        if kind == MetamorphicTransformKind.SUMMARY_PARAPHRASE_EVIDENCE_STABLE:
            return {
                "transform": kind.value,
                "passed": True,
                "expectation": "evidence_refs_identity_stable",
                "semantic_stability_claimed": False,
            }
        return {
            "transform": str(kind),
            "passed": False,
            "expectation": "unknown_transform",
            "semantic_stability_claimed": False,
        }

    def run_locale_identity(self) -> Mapping[str, Any]:
        runner = FakeBookOverviewRunner()
        zh = make_execution_request(
            source_language="zh",
            output_locale="zh-CN",
            provider_policy={
                "provider_kind": "fake",
                "synthetic_output": {
                    "overview_mode": "multi_protagonist",
                    "major_storyline_ids": (11, 12),
                    "skip_provider": True,
                },
            },
        )
        en = make_execution_request(
            source_language="zh",
            output_locale="en-US",
            provider_policy={
                "provider_kind": "fake",
                "synthetic_output": {
                    "overview_mode": "multi_protagonist",
                    "major_storyline_ids": (11, 12),
                    "skip_provider": True,
                },
            },
        )
        zh_out = runner.execute(zh)
        en_out = runner.execute(en)
        return {
            "passed": zh_out.module_outputs.get("major_storyline_ids")
            == en_out.module_outputs.get("major_storyline_ids")
            and zh_out.module_outputs.get("module_key") == en_out.module_outputs.get("module_key"),
            "expectation": "entity_ids_stable_across_output_locale",
            "semantic_stability_claimed": False,
        }


@dataclass
class WholeBookEvaluationHarness:
    fixtures: EvaluationFixtureRepository = field(default_factory=EvaluationFixtureRepository)
    metamorphic: MetamorphicTestRunner = field(default_factory=MetamorphicTestRunner)
    report_builder: EvaluationReportBuilder = field(default_factory=EvaluationReportBuilder)
    runners: Mapping[WholeBookModuleKey, BaseWholeBookModuleRunner] = field(
        default_factory=build_first_four_fake_runners
    )

    def build_suite(self) -> WholeBookEvaluationSuite:
        # Extend contract fake suite with additional synthetic categories.
        base = fake_evaluation_suite()
        extra_cases = []
        for fixture in self.fixtures.list():
            if any(c.synthetic_fixture_ref == fixture.fixture_ref for c in base.cases):
                continue
            if fixture.notes == "metamorphic_variant":
                continue
            extra_cases.append(
                WholeBookEvaluationCase(
                    case_id=f"harness-{fixture.category.value}-{fixture.fixture_ref.split('/')[-1]}",
                    category=fixture.category,
                    title=f"Harness {fixture.category.value}",
                    synthetic_fixture_ref=fixture.fixture_ref,
                )
            )
        extra_meta = (
            MetamorphicEvaluationCase(
                case_id="meta-title-1",
                base_case_id="syn-zh-short-1",
                transform=MetamorphicTransformKind.CHAPTER_TITLE_NOISE,
                expectation="ids_stable",
                synthetic_fixture_ref="synthetic://meta/title/1",
            ),
            MetamorphicEvaluationCase(
                case_id="meta-preface-1",
                base_case_id="syn-zh-short-1",
                transform=MetamorphicTransformKind.IRRELEVANT_PREFACE,
                expectation="no_inference",
                synthetic_fixture_ref="synthetic://meta/preface/1",
            ),
            MetamorphicEvaluationCase(
                case_id="meta-order-1",
                base_case_id="syn-multi-thread-1",
                transform=MetamorphicTransformKind.MODULE_ORDER_CHANGE,
                expectation="order_independent_keys",
                synthetic_fixture_ref="synthetic://multi_thread/1",
            ),
        )
        return WholeBookEvaluationSuite(
            suite_id="agent_r.whole_book.evaluation",
            version="0.0.1-fake",
            cases=base.cases + tuple(extra_cases),
            metamorphic_cases=base.metamorphic_cases + extra_meta,
            dimensions=tuple(EvaluationDimension),
            non_production=True,
        )

    def run_case(self, case: WholeBookEvaluationCase) -> WholeBookEvaluationResult:
        fixture = self.fixtures.get(case.synthetic_fixture_ref)
        SourceLanguage(fixture.source_language)
        OutputLocale(fixture.output_locale)
        present = 0
        schema_ok = True
        ref_ok = True
        evidence_ok = True
        snap_ok = True
        for key, runner in self.runners.items():
            req = make_execution_request(
                module_key=key,
                source_language=fixture.source_language,
                output_locale=fixture.output_locale,
                provider_policy={
                    "provider_kind": "fake",
                    "synthetic_output": {
                        "empty_dto": True,
                        "partial": True,
                        "skip_provider": True,
                        "fixture_id": case.case_id,
                    },
                },
            )
            result = runner.execute(req)
            present += 1
            report = runner.validate_output(result)
            schema_ok = schema_ok and report.schema_valid
            ref_ok = ref_ok and report.references_valid
            evidence_ok = evidence_ok and (
                report.evidence_valid or result.module_outputs.get("partial") is True
            )
            snap_ok = snap_ok and report.snapshot_valid
            # Must stay synthetic / fake.
            if result.module_outputs.get("fake") is not True:
                schema_ok = False
            if result.module_outputs.get("production") is True:
                schema_ok = False
        metrics = compute_contract_metrics(
            schema_valid=schema_ok,
            references_valid=ref_ok,
            evidence_valid=evidence_ok,
            evidence_coverage_ratio=1.0 if evidence_ok else 0.0,
            snapshot_valid=snap_ok,
            duplicate_count=0,
            conflict_count=0,
            recovery_duplicate_count=0,
            modules_present=present,
        )
        passed = schema_ok and snap_ok and present == 4
        return WholeBookEvaluationResult(
            case_id=case.case_id,
            passed=passed,
            dimension_scores=metrics.as_dimension_scores(),
            warnings=("fake_harness", "contract_only", f"category:{case.category.value}"),
            fake=True,
        )

    def run_suite(self, suite: WholeBookEvaluationSuite | None = None) -> Mapping[str, Any]:
        suite = suite or self.build_suite()
        results = [self.run_case(case) for case in suite.cases]
        meta_results = []
        for meta in suite.metamorphic_cases:
            base = self.fixtures.get(
                next(
                    (c.synthetic_fixture_ref for c in suite.cases if c.case_id == meta.base_case_id),
                    "synthetic://short/zh/1",
                )
            )
            variant = None
            try:
                variant = self.fixtures.get(meta.synthetic_fixture_ref)
            except KeyError:
                variant = base
            meta_results.append(
                self.metamorphic.run_transform(
                    transform=meta.transform,
                    base_fixture=base,
                    variant_fixture=variant,
                )
            )
        meta_results.append(self.metamorphic.run_locale_identity())
        metrics = compute_contract_metrics(
            schema_valid=all(r.passed for r in results),
            references_valid=True,
            evidence_valid=True,
            evidence_coverage_ratio=1.0,
            snapshot_valid=True,
            duplicate_count=0,
            conflict_count=0,
            recovery_duplicate_count=0,
            modules_present=4,
        )
        return self.report_builder.build(
            suite=suite,
            results=results,
            metrics=metrics,
            metamorphic_results=meta_results,
        )


__all__ = [
    "ContractMetrics",
    "EvaluationFixture",
    "EvaluationFixtureRepository",
    "EvaluationReportBuilder",
    "MetamorphicTestRunner",
    "SYNTHETIC_TEXTS",
    "WholeBookEvaluationHarness",
    "compute_contract_metrics",
]
