"""Phase 2B Agent R — first-four module foundations (CHG-20260723-039).

Directed tests only — no full pytest suite.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from app.narrative_core.enums import WholeBookModuleKey
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineError,
    PrivateEngineErrorCode,
)
from app.narrative_core.private_engine_contract.evidence import EvidenceCandidate
from app.narrative_core.private_engine_contract.module_runner import MODULE_RUNNER_PROTOCOL_METHODS
from app.narrative_core.private_engine_contract.module_spec import FIRST_FOUR_MODULE_SPECS
from app.narrative_core.private_engine_contract.provider_gateway import FakeProviderGateway
from app.narrative_core.private_engine_contract.protocol import PrivateEngineCheckpoint
import re

from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED
from app.narrative_core.services.whole_book_engine_registry import PRODUCTION_DEFAULT_ENGINE_ID
from app.narrative_core.services.fake_prompt_pack import (
    assert_no_formal_prompt_bodies,
    build_fake_prompt_pack,
    compute_fake_prompt_pack_hash,
    reject_fake_prompt_pack_in_production,
)
from app.narrative_core.services.whole_book_candidate_builder import (
    ModuleCandidateBuilder,
    compute_output_fingerprint,
)
from app.narrative_core.services.whole_book_evaluation_harness import (
    EvaluationFixtureRepository,
    MetamorphicTestRunner,
    WholeBookEvaluationHarness,
    compute_contract_metrics,
)
from app.narrative_core.services.whole_book_module_output_validator import (
    DefaultModuleOutputValidator,
    ModuleOutputValidationInput,
    ReferenceResolver,
)
from app.narrative_core.services.whole_book_module_runner import (
    DEFAULT_MODULE_SPEC_REGISTRY,
    GENERAL_CHAPTER_FUNCTION_LABELS,
    BaseWholeBookModuleRunner,
    FakeBookOverviewRunner,
    FakeChapterFunctionsRunner,
    FakeStorylinesRunner,
    FakeStructureStagesRunner,
    ModuleCheckpointBuilder,
    ModuleCheckpointValidator,
    ModuleProviderExecutionAdapter,
    WholeBookModuleSpecRegistry,
    build_default_module_spec_registry,
    build_first_four_fake_runners,
    make_execution_request,
)
from app.narrative_core.private_engine_contract.evaluation import MetamorphicTransformKind
from app.narrative_core.enums import EvidenceRole

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICES = REPO_ROOT / "apps" / "api" / "app" / "narrative_core" / "services"
PRODUCT_EDITION = REPO_ROOT / "apps" / "desktop" / "src" / "services" / "productEdition.ts"
ENGINE_REGISTRY_SRC = SERVICES / "whole_book_engine_registry.py"


# --- 1–4 Registry ---


def test_01_registry() -> None:
    reg = build_default_module_spec_registry()
    assert len(reg.list()) == 4
    assert reg.get(WholeBookModuleKey.BOOK_OVERVIEW).module_version == "1.0.0"
    reg.validate()
    assert WholeBookModuleKey.BOOK_OVERVIEW in reg.supported_modules()


def test_02_duplicate_module() -> None:
    reg = WholeBookModuleSpecRegistry()
    reg.register(FIRST_FOUR_MODULE_SPECS[0])
    with pytest.raises(ValueError, match="duplicate"):
        reg.register(FIRST_FOUR_MODULE_SPECS[0])


def test_03_stage_consistency() -> None:
    reg = DEFAULT_MODULE_SPEC_REGISTRY
    planning = reg.planning_stages()
    producer = reg.producer_stages()
    for module, stages in producer.items():
        for stage in stages:
            assert stage in planning[module]


def test_04_compatibility_views() -> None:
    views = DEFAULT_MODULE_SPEC_REGISTRY.export_legacy_compatibility_views()
    assert "ENGINE_MODULE_PLANNING_STAGES_FROM_SPEC" in views
    assert "PRODUCT_MODULE_STAGE_DEPENDENCIES_FROM_SPEC" in views
    assert "MODULE_PRODUCER_STAGES" in views
    assert WholeBookModuleKey.BOOK_OVERVIEW in views["ENGINE_MODULE_PLANNING_STAGES"]


# --- 5–6 Base Runner / Context ---


def test_05_base_runner_protocol() -> None:
    runner = FakeBookOverviewRunner()
    for name in MODULE_RUNNER_PROTOCOL_METHODS:
        assert hasattr(runner, name)
    assert runner._orm_access is False
    assert runner._credential_read is False
    assert runner._license_parse is False


def test_06_context_validation() -> None:
    runner = FakeBookOverviewRunner()
    req = make_execution_request()
    ctx = runner.prepare_context(req)
    assert ctx["orm_access"] is False
    assert ctx["context_bundle_hash"]
    with pytest.raises(ValueError, match="prompt_pack"):
        bad = make_execution_request(prompt_pack_ref="   ")
        # PrivateEngineExecutionRequest may allow blank then runner rejects
        object.__setattr__(bad, "prompt_pack_ref", "") if False else None
        from dataclasses import replace

        bad = replace(req, prompt_pack_ref="")
        runner.validate_request(bad)


# --- 7–12 Fake runners / synthetic / no inference ---


def test_07_fake_overview() -> None:
    runner = FakeBookOverviewRunner()
    runner.synthetic_fixtures["multi"] = {
        "overview_mode": "multi_protagonist",
        "major_storyline_ids": (1, 2, 3),
        "skip_provider": True,
    }
    req = make_execution_request(
        provider_policy={"provider_kind": "fake", "synthetic_fixture_id": "multi"}
    )
    result = runner.execute(req)
    assert result.module_outputs["fake"] is True
    assert result.module_outputs["protagonist_asset_id"] is None
    assert result.module_outputs["major_storyline_ids"] == [1, 2, 3] or result.module_outputs[
        "major_storyline_ids"
    ] == (1, 2, 3)


def test_08_fake_structure() -> None:
    runner = FakeStructureStagesRunner()
    req = make_execution_request(
        module_key=WholeBookModuleKey.STRUCTURE_STAGES,
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {"structure_mode": "five_stages", "skip_provider": True},
        },
    )
    result = runner.execute(req)
    assert len(result.module_outputs["stages"]) == 5
    assert result.module_outputs["fake"] is True


def test_09_fake_chapter_functions() -> None:
    runner = FakeChapterFunctionsRunner()
    req = make_execution_request(
        module_key=WholeBookModuleKey.CHAPTER_FUNCTIONS,
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {"chapter_mode": "multi_label", "skip_provider": True},
        },
    )
    result = runner.execute(req)
    labels = result.module_outputs["function_labels"]
    assert "primary" in labels and "secondary" in labels
    assert set(labels) <= GENERAL_CHAPTER_FUNCTION_LABELS


def test_10_fake_storylines() -> None:
    runner = FakeStorylinesRunner()
    req = make_execution_request(
        module_key=WholeBookModuleKey.STORYLINES,
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {
                "storyline_type": "quest",
                "status": "paused",
                "skip_provider": True,
            },
        },
    )
    result = runner.execute(req)
    assert result.module_outputs["storyline_type"] == "quest"
    assert result.module_outputs["status"] == "paused"


def test_11_outputs_synthetic() -> None:
    for runner in build_first_four_fake_runners().values():
        req = make_execution_request(
            module_key=runner.module_key,
            provider_policy={
                "provider_kind": "fake",
                "synthetic_output": {"empty_dto": True, "skip_provider": True},
            },
        )
        out = runner.execute(req).module_outputs
        assert out["synthetic"] is True
        assert out["non_production"] is True
        assert out["fake"] is True


def test_12_no_text_inference() -> None:
    runner = FakeBookOverviewRunner()
    # Title/author-like strings in policy must not trigger real analysis branches.
    req = make_execution_request(
        provider_policy={
            "provider_kind": "fake",
            "book_title": "独孤求败传奇",
            "author": "某作者",
            "synthetic_output": {"empty_dto": True, "skip_provider": True},
        }
    )
    result = runner.execute(req)
    assert result.module_outputs["logline"] == ""
    assert result.module_outputs["protagonist_asset_id"] is None
    src = inspect.getsource(FakeBookOverviewRunner._default_synthetic_dto)
    assert "独孤" not in src
    # Only explicit overview_mode fixtures — no title/author branching.
    assert "book_title" not in src
    assert "author" not in src
    assert "overview_mode" in src


# --- 13–15 Fake Prompt Pack ---


def test_13_fake_prompt_pack() -> None:
    pack = build_fake_prompt_pack()
    pack.assert_compatible_with_first_four()
    assert pack.instruction_refs.get(WholeBookModuleKey.BOOK_OVERVIEW).startswith("fake://")
    assert_no_formal_prompt_bodies(pack)


def test_14_prompt_hash() -> None:
    pack = build_fake_prompt_pack()
    assert len(pack.prompt_hash) == 64
    assert pack.fingerprint_part().startswith("prompt_pack_hash=")
    h1 = compute_fake_prompt_pack_hash(
        prompt_pack_id=pack.manifest.prompt_pack_id,
        prompt_pack_version=pack.manifest.prompt_pack_version,
        instruction_refs=dict(pack.instruction_refs.by_module),
        schema_refs=dict(pack.response_schema_refs.by_module),
    )
    assert h1 == pack.package_hash


def test_15_production_fake_pack_reject() -> None:
    pack = build_fake_prompt_pack()
    with pytest.raises(RuntimeError, match="production"):
        reject_fake_prompt_pack_in_production(pack, production=True)
    reject_fake_prompt_pack_in_production(pack, production=False)


# --- 16–17 Provider adapter / no credential ---


def test_16_provider_adapter() -> None:
    adapter = ModuleProviderExecutionAdapter(gateway=FakeProviderGateway())
    pack = build_fake_prompt_pack()
    resp = adapter.execute(
        request_id="r1",
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        instruction_ref=pack.instruction_refs.get(WholeBookModuleKey.BOOK_OVERVIEW),
        input_bundle_ref="synthetic://bundle/1/1",
        response_schema_ref=pack.response_schema_refs.get(WholeBookModuleKey.BOOK_OVERVIEW),
        prompt_pack_ref="fake.prompt_pack.first_four@0.0.1-fake",
        provider_policy={"provider_kind": "fake", "model_route": "fake"},
        cancellation_ref=None,
    )
    assert resp.status == "success"
    assert resp.structured_output is not None


def test_17_no_credential() -> None:
    adapter = ModuleProviderExecutionAdapter(gateway=FakeProviderGateway())
    pack = build_fake_prompt_pack()
    with pytest.raises(ValueError):
        adapter.execute(
            request_id="r2",
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            instruction_ref=pack.instruction_refs.get(WholeBookModuleKey.BOOK_OVERVIEW),
            input_bundle_ref="synthetic://bundle/1/1",
            response_schema_ref=pack.response_schema_refs.get(WholeBookModuleKey.BOOK_OVERVIEW),
            prompt_pack_ref="fake.pack",
            provider_policy={"provider_kind": "fake", "api_key": "secret"},
            cancellation_ref=None,
        )


# --- 18–24 Validator ---


def test_18_invalid_schema() -> None:
    report = DefaultModuleOutputValidator().validate(
        ModuleOutputValidationInput(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            module_outputs={"schema_error": True, "fake": True},
            require_evidence_for_acceptance=False,
        )
    )
    assert report.schema_valid is False
    assert report.accepted is False


def test_19_invalid_ref() -> None:
    report = DefaultModuleOutputValidator().validate(
        ModuleOutputValidationInput(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            module_outputs={
                "logline": "",
                "premise": "",
                "central_question": "",
                "primary_conflict": "",
                "protagonist_asset_id": 999,
                "major_storyline_ids": (),
                "structure_summary": "",
                "ending_state": "",
                "evidence_refs": (),
                "confidence": None,
                "fake": True,
                "force_accept": True,
            },
            resolver=ReferenceResolver(asset_ids=frozenset({1})),
            require_evidence_for_acceptance=False,
        )
    )
    assert report.references_valid is False


def test_20_insufficient_evidence() -> None:
    report = DefaultModuleOutputValidator().validate(
        ModuleOutputValidationInput(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            module_outputs={
                "logline": "x",
                "premise": "",
                "central_question": "",
                "primary_conflict": "",
                "protagonist_asset_id": None,
                "major_storyline_ids": (),
                "structure_summary": "",
                "ending_state": "",
                "evidence_refs": (),
                "confidence": None,
                "evidence_insufficient": True,
                "force_accept": True,
            },
            require_evidence_for_acceptance=True,
        )
    )
    assert report.evidence_valid is False
    assert report.accepted is False


def test_21_cross_book() -> None:
    report = DefaultModuleOutputValidator().validate(
        ModuleOutputValidationInput(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            module_outputs={
                "logline": "",
                "premise": "",
                "central_question": "",
                "primary_conflict": "",
                "protagonist_asset_id": None,
                "major_storyline_ids": (),
                "structure_summary": "",
                "ending_state": "",
                "evidence_refs": (),
                "cross_book": True,
                "force_accept": True,
            },
            book_id=1,
            expected_book_id=2,
            require_evidence_for_acceptance=False,
        )
    )
    assert report.snapshot_valid is False or report.references_valid is False
    assert report.accepted is False


def test_22_cross_snapshot() -> None:
    ev = EvidenceCandidate(
        candidate_id="e1",
        book_snapshot_id=2,
        snapshot_chapter_id=1,
        snapshot_paragraph_id=1,
        stable_paragraph_id="p1",
        paragraph_content_hash="h",
        start_offset=0,
        end_offset=1,
        evidence_role=EvidenceRole.SUPPORT,
        target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        target_output_ref="book_overview.logline",
        extraction_method="synthetic",
        confidence=0.1,
        source_context_unit_id="chapter:1",
        book_id=1,
        preview="x",
    )
    report = DefaultModuleOutputValidator().validate(
        ModuleOutputValidationInput(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            module_outputs={
                "logline": "",
                "premise": "",
                "central_question": "",
                "primary_conflict": "",
                "protagonist_asset_id": None,
                "major_storyline_ids": (),
                "structure_summary": "",
                "ending_state": "",
                "evidence_refs": (),
                "force_accept": True,
            },
            evidence_candidates=(ev,),
            book_snapshot_id=1,
            expected_book_snapshot_id=1,
            require_evidence_for_acceptance=False,
        )
    )
    assert report.snapshot_valid is False


def test_23_duplicate() -> None:
    report = DefaultModuleOutputValidator().validate(
        ModuleOutputValidationInput(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            module_outputs={
                "logline": "",
                "premise": "",
                "central_question": "",
                "primary_conflict": "",
                "protagonist_asset_id": None,
                "major_storyline_ids": (),
                "structure_summary": "",
                "ending_state": "",
                "evidence_refs": (),
                "duplicate": True,
                "force_accept": True,
            },
            current_output_fingerprint="abc",
            prior_output_fingerprints=frozenset({"abc"}),
            require_evidence_for_acceptance=False,
        )
    )
    assert report.duplicate_summary.get("count", 0) >= 1


def test_24_conflict() -> None:
    report = DefaultModuleOutputValidator().validate(
        ModuleOutputValidationInput(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            module_outputs={
                "logline": "",
                "premise": "",
                "central_question": "",
                "primary_conflict": "",
                "protagonist_asset_id": None,
                "major_storyline_ids": (),
                "structure_summary": "",
                "ending_state": "",
                "evidence_refs": (),
                "conflict": True,
                "force_accept": True,
            },
            require_evidence_for_acceptance=False,
        )
    )
    assert report.conflict_summary.get("count", 0) >= 1


# --- 25–27 Candidate builder ---


def test_25_candidate_command() -> None:
    from app.narrative_core.private_engine_contract.protocol import PrivateEngineExecutionResult
    from datetime import datetime

    result = PrivateEngineExecutionResult(
        schema="storylens.private_engine.result",
        version="1.0.0",
        engine_id="fake.signed.private_engine",
        engine_version="0.0.1-fake",
        stage_key="analyze_structure",
        attempt=0,
        status="completed_fake",
        module_outputs={
            "logline": "[FAKE]",
            "premise": "",
            "central_question": "",
            "primary_conflict": "",
            "protagonist_asset_id": None,
            "major_storyline_ids": (),
            "structure_summary": "",
            "ending_state": "",
            "evidence_refs": (),
            "confidence": None,
            "force_accept": True,
        },
        evidence_candidates=(),
        asset_candidates=({"asset_type": "storyline", "synthetic": True, "fake": True},),
        relation_candidates=(),
        conflict_candidates=(),
        checkpoint=None,
        usage={"synthetic": True},
        warnings=("fake",),
        validation_summary={},
        generated_at=datetime(2026, 7, 24, 0, 0, 0),
    )
    validation = DefaultModuleOutputValidator().validate(
        ModuleOutputValidationInput(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            module_outputs=result.module_outputs,
            require_evidence_for_acceptance=False,
        )
    )
    assert validation.accepted is True
    built = ModuleCandidateBuilder().build(
        result=result,
        validation=validation,
        run_id=1,
        run_stage_id=1,
        book_snapshot_id=1,
        module_key="book_overview",
        module_version="1.0.0",
        configuration_fingerprint="fake-config-fp",
        mock=True,
    )
    assert built.rejected is False
    assert built.stage_artifact is not None
    assert len(built.asset_commands) == 1
    assert built.orm_written is False
    assert built.auto_confirm is False


def test_26_no_orm() -> None:
    src = (SERVICES / "whole_book_candidate_builder.py").read_text(encoding="utf-8")
    assert "sqlalchemy" not in src.lower()
    assert "Session" not in src
    runner_src = (SERVICES / "whole_book_module_runner.py").read_text(encoding="utf-8")
    assert "from app.db" not in runner_src
    assert "sqlalchemy" not in runner_src.lower()


def test_27_no_canonical() -> None:
    runner = FakeBookOverviewRunner()
    req = make_execution_request(
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {"empty_dto": True, "skip_provider": True},
        }
    )
    candidates = runner.build_candidates(runner.execute(req))
    assert candidates["auto_confirm"] is False
    assert candidates["auto_lock"] is False
    assert candidates["canonical_overwrite"] is False
    assert candidates["orm_written"] is False


# --- 28–31 Four module contracts ---


def test_28_overview_multi_protagonist() -> None:
    runner = FakeBookOverviewRunner()
    req = make_execution_request(
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {
                "overview_mode": "multi_protagonist",
                "major_storyline_ids": (10, 20),
                "skip_provider": True,
            },
        }
    )
    out = runner.execute(req).module_outputs
    assert out["protagonist_asset_id"] is None
    assert len(out["major_storyline_ids"]) == 2


def test_29_structure_non_three_act() -> None:
    runner = FakeStructureStagesRunner()
    for mode, n in (("two_stages", 2), ("five_stages", 5), ("unstable", 0)):
        req = make_execution_request(
            module_key=WholeBookModuleKey.STRUCTURE_STAGES,
            provider_policy={
                "provider_kind": "fake",
                "synthetic_output": {"structure_mode": mode, "skip_provider": True},
            },
        )
        stages = runner.execute(req).module_outputs["stages"]
        assert len(stages) == n
    assert runner.spec.force_three_act is False


def test_30_chapter_multi_label() -> None:
    runner = FakeChapterFunctionsRunner()
    req = make_execution_request(
        module_key=WholeBookModuleKey.CHAPTER_FUNCTIONS,
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {
                "chapter_mode": "side_flashback",
                "skip_provider": True,
            },
        },
    )
    labels = set(runner.execute(req).module_outputs["function_labels"])
    assert "side_story" in labels and "flashback" in labels


def test_31_storyline_multi_membership() -> None:
    runner = FakeStorylinesRunner()
    req = make_execution_request(
        module_key=WholeBookModuleKey.STORYLINES,
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {
                "storyline_type": "relationship",
                "key_event_ids": (1, 2),
                "status": "incomplete",
                "skip_provider": True,
            },
        },
    )
    out = runner.execute(req).module_outputs
    assert out["key_event_ids"]
    with pytest.raises(ValueError, match="character lists"):
        runner._default_synthetic_dto({"character_list_as_storyline": True})


# --- 32–35 Checkpoint ---


def test_32_checkpoint() -> None:
    runner = FakeBookOverviewRunner()
    req = make_execution_request()
    cp = runner.build_checkpoint(req)
    assert cp.protocol_version.startswith("storylens.private_engine")
    assert cp.integrity_hash
    assert cp.prompt_pack_version
    assert cp.context_bundle_hash


def test_33_prompt_mismatch() -> None:
    runner = FakeBookOverviewRunner()
    req = make_execution_request(checkpoint_ref="ckpt")
    cp = runner.build_checkpoint(req)
    validator = ModuleCheckpointValidator()
    with pytest.raises(PrivateEngineError) as exc:
        validator.validate_resume(
            checkpoint=cp,
            current_engine_id=cp.engine_id,
            current_engine_version=cp.engine_version,
            current_prompt_pack_id="other.pack",
            current_prompt_pack_version="9.9.9",
            current_context_bundle_hash=cp.context_bundle_hash,
            current_book_snapshot_id=cp.book_snapshot_id,
            current_configuration_fingerprint=cp.configuration_fingerprint,
        )
    assert exc.value.code == PrivateEngineErrorCode.PROMPT_PACK_INCOMPATIBLE


def test_34_context_mismatch() -> None:
    runner = FakeBookOverviewRunner()
    req = make_execution_request(checkpoint_ref="ckpt")
    cp = runner.build_checkpoint(req)
    with pytest.raises(PrivateEngineError):
        ModuleCheckpointValidator().validate_resume(
            checkpoint=cp,
            current_engine_id=cp.engine_id,
            current_engine_version=cp.engine_version,
            current_prompt_pack_id=cp.prompt_pack_id,
            current_prompt_pack_version=cp.prompt_pack_version,
            current_context_bundle_hash="changed-bundle-hash",
            current_book_snapshot_id=cp.book_snapshot_id,
            current_configuration_fingerprint=cp.configuration_fingerprint,
        )


def test_35_resume_dedupe() -> None:
    runner = FakeBookOverviewRunner()
    runner.emitted_output_fingerprints.clear()
    req = make_execution_request(
        checkpoint_ref="ckpt:1",
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {"overview_mode": "partial", "partial": True, "skip_provider": True},
        },
    )
    first = runner.resume(req)
    second = runner.resume(req)
    assert first.status != "resumed_deduplicated"
    assert second.status == "resumed_deduplicated" or second.module_outputs.get("resume_deduped")


# --- 36–40 Evaluation / languages / degraded ---


def test_36_evaluation_cases() -> None:
    harness = WholeBookEvaluationHarness()
    report = harness.run_suite()
    assert report["fake"] is True
    assert report["case_count"] >= 5
    assert report["passed"] >= 1
    assert "contract_and_fake_output_only" in report["claims"]


def test_37_chinese() -> None:
    fixtures = EvaluationFixtureRepository()
    zh = fixtures.get("synthetic://short/zh/1")
    assert zh.source_language == "zh"
    runner = FakeBookOverviewRunner()
    req = make_execution_request(
        source_language="zh",
        output_locale="zh-CN",
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {"empty_dto": True, "skip_provider": True},
        },
    )
    assert runner.execute(req).module_outputs["source_language"] == "zh"


def test_38_english() -> None:
    runner = FakeBookOverviewRunner()
    req = make_execution_request(
        source_language="en",
        output_locale="en-US",
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {"empty_dto": True, "skip_provider": True},
        },
    )
    out = runner.execute(req).module_outputs
    assert out["source_language"] == "en"
    assert out["output_locale"] == "en-US"


def test_39_mixed() -> None:
    runner = FakeBookOverviewRunner()
    req = make_execution_request(
        source_language="mixed",
        output_locale="en-US",
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {"empty_dto": True, "skip_provider": True},
        },
    )
    assert runner.execute(req).module_outputs["source_language"] == "mixed"


def test_40_degraded_text() -> None:
    fix = EvaluationFixtureRepository().get("synthetic://degraded/1")
    assert "\ufffd" in fix.text or "\x00" in fix.text
    harness = WholeBookEvaluationHarness()
    case = next(c for c in harness.build_suite().cases if "degraded" in c.synthetic_fixture_ref)
    result = harness.run_case(case)
    assert result.fake is True


# --- 41–47 Metamorphic ---


def test_41_metamorphic_title() -> None:
    repo = EvaluationFixtureRepository()
    out = MetamorphicTestRunner().run_transform(
        transform=MetamorphicTransformKind.CHAPTER_TITLE_NOISE,
        base_fixture=repo.get("synthetic://short/zh/1"),
        variant_fixture=repo.get("synthetic://meta/title/1"),
    )
    assert out["passed"] is True
    assert out["semantic_stability_claimed"] is False


def test_42_whitespace() -> None:
    repo = EvaluationFixtureRepository()
    out = MetamorphicTestRunner().run_transform(
        transform=MetamorphicTransformKind.WHITESPACE_NEWLINE,
        base_fixture=repo.get("synthetic://short/zh/1"),
        variant_fixture=repo.get("synthetic://meta/whitespace/1"),
    )
    assert out["passed"] is True


def test_43_numbering() -> None:
    repo = EvaluationFixtureRepository()
    out = MetamorphicTestRunner().run_transform(
        transform=MetamorphicTransformKind.CHAPTER_RENUMBER_SAME_CONTENT,
        base_fixture=repo.get("synthetic://short/zh/1"),
        variant_fixture=repo.get("synthetic://meta/renumber/1"),
    )
    assert out["passed"] is True


def test_44_preface() -> None:
    repo = EvaluationFixtureRepository()
    out = MetamorphicTestRunner().run_transform(
        transform=MetamorphicTransformKind.IRRELEVANT_PREFACE,
        base_fixture=repo.get("synthetic://short/zh/1"),
        variant_fixture=repo.get("synthetic://meta/preface/1"),
    )
    assert out["passed"] is True


def test_45_enhanced_missing() -> None:
    repo = EvaluationFixtureRepository()
    out = MetamorphicTestRunner().run_transform(
        transform=MetamorphicTransformKind.ENHANCED_ASSETS_MISSING_DEGRADE,
        base_fixture=repo.get("synthetic://multi_thread/1"),
    )
    assert out["passed"] is True


def test_46_module_order() -> None:
    repo = EvaluationFixtureRepository()
    out = MetamorphicTestRunner().run_transform(
        transform=MetamorphicTransformKind.MODULE_ORDER_CHANGE,
        base_fixture=repo.get("synthetic://short/zh/1"),
    )
    assert out["passed"] is True


def test_47_locale_identity() -> None:
    out = MetamorphicTestRunner().run_locale_identity()
    assert out["passed"] is True


# --- 48 Metrics ---


def test_48_metrics() -> None:
    m = compute_contract_metrics(
        schema_valid=True,
        references_valid=True,
        evidence_valid=True,
        evidence_coverage_ratio=0.5,
        snapshot_valid=True,
        duplicate_count=0,
        conflict_count=1,
        recovery_duplicate_count=0,
        modules_present=4,
    )
    scores = m.as_dimension_scores()
    assert scores["schema_validity"] == 1.0
    assert scores["evidence_coverage"] == 0.5
    assert scores["module_completeness"] == 1.0


# --- 49–51 Source / gates ---


def test_49_no_real_prompt() -> None:
    for path in SERVICES.glob("*.py"):
        if path.name.startswith(
            (
                "whole_book_module_",
                "fake_prompt_pack",
                "whole_book_candidate",
                "whole_book_evaluation",
            )
        ):
            text = path.read_text(encoding="utf-8")
            for banned in ("你是一名资深小说分析师", "Identify the protagonist from the novel"):
                assert banned not in text


def test_50_no_model() -> None:
    for name in (
        "whole_book_module_runner.py",
        "whole_book_module_output_validator.py",
        "whole_book_candidate_builder.py",
        "fake_prompt_pack.py",
        "whole_book_evaluation_harness.py",
    ):
        tree = ast.parse((SERVICES / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "openai" not in alias.name
                    assert "anthropic" not in alias.name
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "openai" not in node.module
                assert "anthropic" not in node.module


def test_51_formal_run_disabled() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    text = PRODUCT_EDITION.read_text(encoding="utf-8")
    assert re.search(r"PRO_CAPABILITIES_SHIPPED\s*=\s*false", text)
    assert PRODUCTION_DEFAULT_ENGINE_ID is None
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False
    reg_text = ENGINE_REGISTRY_SRC.read_text(encoding="utf-8")
    assert re.search(
        r"^PRODUCTION_DEFAULT_ENGINE_ID:\s*str\s*\|\s*None\s*=\s*None\s*$",
        reg_text,
        re.MULTILINE,
    )


def test_52_version_manager_check() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "version_manager.py"), "check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_53_change_registry_check() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "change_registry.py"), "check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_54_git_diff_check() -> None:
    proc = subprocess.run(
        ["git", "diff", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_budget_denied_no_candidate() -> None:
    adapter = ModuleProviderExecutionAdapter(gateway=FakeProviderGateway(), budget_remaining=False)
    pack = build_fake_prompt_pack()
    with pytest.raises(PrivateEngineError) as exc:
        adapter.execute(
            request_id="b1",
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            instruction_ref=pack.instruction_refs.get(WholeBookModuleKey.BOOK_OVERVIEW),
            input_bundle_ref="synthetic://bundle/1/1",
            response_schema_ref=pack.response_schema_refs.get(WholeBookModuleKey.BOOK_OVERVIEW),
            prompt_pack_ref="fake.pack",
            provider_policy={"provider_kind": "fake"},
            cancellation_ref=None,
        )
    assert exc.value.code == PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED


def test_rejected_input_no_candidate_build() -> None:
    runner = FakeBookOverviewRunner()
    req = make_execution_request(
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {"empty_dto": True, "skip_provider": True},
        }
    )
    result = runner.execute(req)
    built = ModuleCandidateBuilder().build(
        result=result,
        validation=runner.validate_output(result),
        run_id=1,
        run_stage_id=1,
        book_snapshot_id=1,
        module_key="book_overview",
        module_version="1.0.0",
        configuration_fingerprint="fp",
        mock=True,
    )
    assert built.rejected is True
    assert built.asset_commands == ()


def test_fingerprint_stable() -> None:
    a = compute_output_fingerprint({"a": 1, "b": [2, 3]})
    b = compute_output_fingerprint({"b": [2, 3], "a": 1})
    assert a == b


def test_checkpoint_builder_fields() -> None:
    req = make_execution_request()
    cp = ModuleCheckpointBuilder().build(
        request=req,
        module_key="book_overview",
        module_version="1.0.0",
        prompt_pack_id="fake.prompt_pack.first_four",
        prompt_pack_version="0.0.1-fake",
        context_bundle_hash="bundle",
        completed_units=("u1",),
        pending_units=("u2",),
        output_fingerprints=("fp1",),
    )
    assert isinstance(cp, PrivateEngineCheckpoint)
    assert cp.completed_units == ("u1",)
    assert cp.quality_profile == "balanced"


def test_isinstance_base_runner() -> None:
    assert isinstance(FakeBookOverviewRunner(), BaseWholeBookModuleRunner)
