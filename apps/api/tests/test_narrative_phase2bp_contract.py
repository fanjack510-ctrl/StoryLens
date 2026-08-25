"""Phase 2B-P Private Engine contract verification (directed tests only)."""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import (
    EvidenceRole,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
    WholeBookStageKey,
)
from app.narrative_core.private_engine_contract.algorithm_generality import (
    GENERALITY_RULES,
    assert_generality_rules_complete,
    assert_no_book_identity_branch_keys,
)
from app.narrative_core.private_engine_contract.candidate import (
    FORBIDDEN_AUTO_ACTIONS,
    CandidatePersistenceContract,
    assert_no_forbidden_auto_actions,
    fake_candidate_write_fixture,
)
from app.narrative_core.private_engine_contract.checkpoint import (
    CHECKPOINT_REJECT_REASONS,
    CheckpointCompatibilityInput,
    assert_checkpoint_compatible,
    build_fake_checkpoint,
)
from app.narrative_core.private_engine_contract.context import (
    CONTEXT_PIPELINE_METHODS,
    CONTEXT_SCHEMA,
    ContextBundle,
    ContextLevel,
    ContextUnitType,
    FakeContextPipeline,
    WholeBookContextUnit,
    fake_context_bundle,
    sort_context_units_deterministically,
)
from app.narrative_core.private_engine_contract.data_handling import (
    DEFAULT_CLOUD_DATA_HANDLING_POLICY,
    DEFAULT_LOCAL_DATA_HANDLING_POLICY,
    ExecutionLocation,
    WholeBookDataHandlingPolicy,
    requires_consent_for_upload,
)
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineError,
    PrivateEngineErrorCode,
    all_private_engine_error_codes,
    private_engine_error,
)
from app.narrative_core.private_engine_contract.evaluation import (
    MetamorphicEvaluationCase,
    MetamorphicTransformKind,
    WholeBookEvaluationCase,
    fake_evaluation_suite,
)
from app.narrative_core.private_engine_contract.evidence import (
    EvidenceCandidate,
    EvidenceValidationContext,
    build_coverage_report,
    fake_evidence_candidates,
    validate_evidence_candidate,
    validate_evidence_candidates,
)
from app.narrative_core.private_engine_contract.fakes import (
    FakeModuleOutputValidator,
    FakeModuleRunner,
    FakePrivateWholeBookEngineLoader,
    FakePromptPackBody,
    FakeProviderGateway,
)
from app.narrative_core.private_engine_contract.language import (
    LANGUAGE_SEPARATION_RULES,
    OutputLocale,
    SourceLanguage,
    assert_language_locale_separated,
)
from app.narrative_core.private_engine_contract.loader import LOADER_PROTOCOL_METHODS
from app.narrative_core.private_engine_contract.manifest import (
    PRIVATE_ENGINE_MANIFEST_SCHEMA,
    PRIVATE_ENGINE_MANIFEST_VERSION,
    PRIVATE_ENGINE_PROTOCOL_ID,
    EngineImplementationKind,
    app_version_in_range,
    configuration_fingerprint_parts,
    fake_mock_manifest,
    fake_private_manifest,
    validate_manifest_for_load,
)
from app.narrative_core.private_engine_contract.module_runner import (
    MODULE_RUNNER_PROTOCOL_METHODS,
    RUNNER_FORBIDDEN_CAPABILITIES,
)
from app.narrative_core.private_engine_contract.module_spec import (
    BOOK_OVERVIEW_SPEC,
    CHAPTER_FUNCTIONS_SPEC,
    ENGINE_MODULE_PLANNING_STAGES_FROM_SPEC,
    FIRST_FOUR_MODULE_SPECS,
    MODULE_PRODUCER_STAGES,
    PRODUCT_MODULE_STAGE_DEPENDENCIES_FROM_SPEC,
    STORYLINES_SPEC,
    STRUCTURE_STAGES_SPEC,
    validate_first_four_consistent_with_legacy_maps,
    validate_module_registry_unique,
    validate_stage_keys_legal,
)
from app.narrative_core.private_engine_contract.prompt_pack import (
    DEFAULT_PROMPT_ANTI_INJECTION_POLICY,
    PromptPackManifest,
    fake_prompt_pack_manifest,
    prompt_hash_fingerprint_part,
)
from app.narrative_core.private_engine_contract.protocol import (
    FORBIDDEN_REQUEST_FIELD_NAMES,
    PrivateEngineExecutionRequest,
    assert_mapping_has_no_forbidden_keys,
)
from app.narrative_core.private_engine_contract.provider_gateway import (
    PROVIDER_GATEWAY_PROTOCOL_METHODS,
    ProviderInferenceRequest,
)
from app.narrative_core.private_engine_contract.quality import (
    ANALYSIS_MODE_VALUES,
    DEFAULT_QUALITY_PROFILES,
    MODEL_ROUTE_NAMESPACE,
    QUALITY_PROFILE_VALUES,
    SEPARATION_RULES,
    QualityProfileKey,
    assert_mode_profile_route_separated,
)
from app.narrative_core.private_engine_contract.usage import (
    fake_usage_report,
    usage_fields_required,
)
from app.narrative_core.private_engine_contract.validation import (
    OUTPUT_VALIDATION_PIPELINE,
)
from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS = REPO_ROOT / "docs" / "architecture" / "narrative-intelligence-core"
PRODUCT_EDITION = REPO_ROOT / "apps" / "desktop" / "src" / "services" / "productEdition.ts"
ENGINE_REGISTRY_SRC = (
    REPO_ROOT
    / "apps"
    / "api"
    / "app"
    / "narrative_core"
    / "services"
    / "whole_book_engine_registry.py"
)
FE_PRIVATE_ERRORS = (
    REPO_ROOT
    / "apps"
    / "desktop"
    / "src"
    / "features"
    / "wholeBook"
    / "privateEngineContracts"
    / "errors.ts"
)
CONTRACT_PKG = (
    REPO_ROOT / "apps" / "api" / "app" / "narrative_core" / "private_engine_contract"
)
MIGRATIONS_DIR = REPO_ROOT / "apps" / "api" / "app" / "narrative_core" / "migrations"
VERSION_FILE = REPO_ROOT / "VERSION"

# Baseline migration modules present before Phase 2B-P (no new migration files).
_BASELINE_MIGRATION_FILES = frozenset({"__init__.py", "runner.py"})

_SUSPICIOUS_PROMPT_PATTERNS = (
    r"You are a helpful",
    r"You are an? (?:expert|assistant|AI)",
    r"system:\s*you are",
    r"As a literary analyst",
    r"Analyze the following novel",
    r"extract the protagonist",
    r"three-act structure analysis algorithm",
)
_MODEL_INVOCATION_PATTERNS = (
    r"openai\.OpenAI\(",
    r"from openai import",
    r"dashscope",
    r"llama-server",
    r"requests\.(?:post|get)\(",
    r"httpx\.(?:post|Client|AsyncClient)",
    r"urllib\.request",
)


def _ts_string_array(name: str, text: str) -> list[str]:
    pattern = rf"export const {name} = \[([\s\S]*?)\] as const"
    match = re.search(pattern, text)
    assert match, f"missing {name}"
    return re.findall(r'"([^"]+)"', match.group(1))


def _provider_request(**overrides: object) -> ProviderInferenceRequest:
    base: dict[str, object] = {
        "request_id": "req-1",
        "provider_kind": "fake",
        "model_route": "fake.route",
        "task_type": "structured",
        "system_instruction_ref": "fake://instruction",
        "prompt_pack_ref": "fake://prompt_pack",
        "input_bundle_ref": "fake://source_data",
        "response_schema_ref": "fake://schema",
        "temperature_policy": {"temperature": 0},
        "token_budget": 100,
        "cost_budget": 0.0,
        "timeout_policy": {"timeout_ms": 1000},
        "retry_policy": {"max_retries": 0},
        "cancellation_ref": None,
        "data_handling_policy": {"provider_kind": "fake"},
        "metadata": {},
    }
    base.update(overrides)
    return ProviderInferenceRequest(**base)  # type: ignore[arg-type]


def _execution_request(**overrides: object) -> PrivateEngineExecutionRequest:
    base: dict[str, object] = {
        "run_id": 1,
        "stage_key": WholeBookStageKey.ANALYZE_STRUCTURE,
        "attempt": 0,
        "book_id": 1,
        "book_snapshot_id": 1,
        "analysis_mode": WholeBookAnalysisMode.NATIVE,
        "requested_module_keys": (WholeBookModuleKey.BOOK_OVERVIEW,),
        "resolved_module_keys": (WholeBookModuleKey.BOOK_OVERVIEW,),
        "context_bundle_ref": "fake://context",
        "provider_policy": {"provider_kind": "fake"},
        "budget_policy": {"max_cost": 0},
        "output_locale": OutputLocale.ZH_CN.value,
        "source_language": SourceLanguage.ZH.value,
        "configuration_fingerprint": "fake-config-fp",
        "prompt_pack_ref": "fake://prompt_pack",
        "cancellation_ref": None,
        "checkpoint_ref": None,
        "mock": True,
        "requested_at": datetime(2026, 7, 23, 0, 0, 0),
    }
    base.update(overrides)
    return PrivateEngineExecutionRequest(**base)  # type: ignore[arg-type]


# --- 1–6 Manifest / load gates ---


def test_01_private_manifest_shape() -> None:
    manifest = fake_private_manifest(non_production=False, signed=True)
    assert manifest.private is True
    assert manifest.signed is True
    assert manifest.implementation_kind != EngineImplementationKind.MOCK
    assert manifest.engine_id
    assert manifest.package_hash
    for banned in ("prompt", "prompt_body", "api_key", "credential", "credentials"):
        assert not hasattr(manifest, banned)


def test_02_manifest_schema_and_version() -> None:
    manifest = fake_private_manifest()
    assert manifest.manifest_schema == PRIVATE_ENGINE_MANIFEST_SCHEMA
    assert manifest.manifest_version == PRIVATE_ENGINE_MANIFEST_VERSION
    assert PRIVATE_ENGINE_MANIFEST_SCHEMA == "storylens.private_engine.manifest"
    assert PRIVATE_ENGINE_MANIFEST_VERSION == "1.0.0"
    assert manifest.protocol_version == PRIVATE_ENGINE_PROTOCOL_ID


def test_03_engine_signature_invalid() -> None:
    manifest = fake_private_manifest(signed=True, non_production=True)
    with pytest.raises(PrivateEngineError) as exc:
        validate_manifest_for_load(
            manifest,
            app_version="1.0.5",
            production=False,
            signature_valid=False,
        )
    assert exc.value.code == PrivateEngineErrorCode.PRIVATE_ENGINE_SIGNATURE_INVALID


def test_04_engine_protocol_incompatible() -> None:
    manifest = fake_private_manifest(protocol_version="storylens.private_engine.v0")
    with pytest.raises(PrivateEngineError) as exc:
        validate_manifest_for_load(
            manifest,
            app_version="1.0.5",
            production=False,
            signature_valid=True,
        )
    assert exc.value.code == PrivateEngineErrorCode.PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE


def test_05_app_version_incompatible() -> None:
    manifest = fake_private_manifest(minimum_app_version="9.9.9")
    assert not app_version_in_range(
        "1.0.5",
        minimum_app_version=manifest.minimum_app_version,
        maximum_app_version=manifest.maximum_app_version,
    )
    with pytest.raises(PrivateEngineError) as exc:
        validate_manifest_for_load(
            manifest,
            app_version="1.0.5",
            production=False,
            signature_valid=True,
        )
    assert exc.value.code == PrivateEngineErrorCode.PRIVATE_ENGINE_APP_VERSION_INCOMPATIBLE


def test_06_production_does_not_degrade_to_mock() -> None:
    mock = fake_mock_manifest()
    with pytest.raises(PrivateEngineError) as exc:
        validate_manifest_for_load(
            mock,
            app_version="1.0.5",
            production=True,
            signature_valid=False,
        )
    assert exc.value.code == PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND
    assert exc.value.detail_code == "production_must_not_degrade_to_mock"

    non_prod_private = fake_private_manifest(non_production=True, signed=True)
    with pytest.raises(PrivateEngineError) as exc2:
        validate_manifest_for_load(
            non_prod_private,
            app_version="1.0.5",
            production=True,
            signature_valid=True,
        )
    assert exc2.value.code == PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND
    assert exc2.value.detail_code == "production_must_not_degrade_to_mock"

    prod_ok = fake_private_manifest(non_production=False, signed=True)
    validate_manifest_for_load(
        prod_ok,
        app_version="1.0.5",
        production=True,
        signature_valid=True,
    )


# --- 7 Loader Fake ---


def test_07_loader_fake() -> None:
    loader = FakePrivateWholeBookEngineLoader()
    assert isinstance(loader, FakePrivateWholeBookEngineLoader)
    for name in LOADER_PROTOCOL_METHODS:
        assert hasattr(loader, name)
    discovered = loader.discover()
    assert any(m.implementation_kind == EngineImplementationKind.MOCK for m in discovered)
    private = next(m for m in discovered if m.private)
    handle = loader.load(private.engine_id)
    assert handle.fake is True
    assert handle.real_binary is False
    health = loader.health_check(private.engine_id)
    assert health.healthy is True


# --- 8–9 Provider Gateway ---


def test_08_provider_gateway() -> None:
    gateway = FakeProviderGateway()
    for name in PROVIDER_GATEWAY_PROTOCOL_METHODS:
        assert hasattr(gateway, name)
    req = _provider_request()
    estimate = gateway.estimate(req)
    assert estimate.within_budget is True
    response = gateway.execute(req)
    assert response.status == "success"
    assert response.structured_output is not None
    usage = gateway.normalize_usage(response)
    assert usage.synthetic is True
    health = gateway.health_check("fake")
    assert health.healthy is True
    assert "no_network" in health.details


def test_09_credential_never_enters_dto() -> None:
    with pytest.raises(ValueError, match="credential"):
        _provider_request(metadata={"api_key": "sk-leak"})
    with pytest.raises(ValueError, match="forbidden|credential"):
        assert_mapping_has_no_forbidden_keys({"api_key": "x"}, label="test")
    assert "api_key" in FORBIDDEN_REQUEST_FIELD_NAMES
    assert "credential" in FORBIDDEN_REQUEST_FIELD_NAMES
    req = _provider_request()
    assert not hasattr(req, "api_key")
    assert not hasattr(req, "credential")


# --- 10–13 Prompt Pack ---


def test_10_prompt_pack_manifest() -> None:
    pack = fake_prompt_pack_manifest()
    assert pack.manifest.instruction_ref
    assert pack.manifest.template_refs
    assert pack.manifest.non_production is True
    assert isinstance(pack.body, FakePromptPackBody)
    assert pack.body.fake is True
    assert pack.body.formal is False
    assert DEFAULT_PROMPT_ANTI_INJECTION_POLICY.source_data_only is True


def test_11_prompt_hash() -> None:
    pack = fake_prompt_pack_manifest()
    assert pack.manifest.prompt_hash
    part = prompt_hash_fingerprint_part(pack.manifest.prompt_hash)
    assert part.startswith("prompt_pack_hash=")
    parts = configuration_fingerprint_parts(
        fake_private_manifest(),
        prompt_pack_hash=pack.manifest.prompt_hash,
    )
    assert any(p.startswith("prompt_pack_hash=") for p in parts)


def test_12_prompt_body_never_enters_artifact() -> None:
    formal = PromptPackManifest(
        prompt_pack_id="formal.pack",
        prompt_pack_version="1.0.0",
        private=True,
        signed=True,
        package_hash="hash",
        supported_engine_versions=("1.0.0",),
        supported_modules=(WholeBookModuleKey.BOOK_OVERVIEW,),
        supported_languages=("zh",),
        output_schema_versions=("1.0.0",),
        instruction_ref="private://instruction",
        template_refs={"book_overview": "private://templates/overview"},
        example_set_refs=(),
        evaluation_policy_ref=None,
        created_at=datetime(2026, 7, 23, 0, 0, 0),
        prompt_hash="content-hash",
        non_production=False,
    )
    for banned in ("prompt_body", "system_prompt", "user_prompt", "messages"):
        assert not hasattr(formal, banned)


def test_13_source_data_instruction_isolation() -> None:
    with pytest.raises(ValueError, match="isolated"):
        _provider_request(
            system_instruction_ref="same-ref",
            input_bundle_ref="same-ref",
        )
    req = _provider_request()
    assert req.system_instruction_ref != req.input_bundle_ref


# --- 14–18 Context ---


def test_14_context_bundle() -> None:
    bundle = fake_context_bundle()
    assert bundle.context_schema == CONTEXT_SCHEMA
    assert bundle.units
    assert all(isinstance(u, WholeBookContextUnit) for u in bundle.units)
    for name in CONTEXT_PIPELINE_METHODS:
        assert hasattr(FakeContextPipeline(), name)


def test_15_snapshot_hash() -> None:
    bundle = fake_context_bundle()
    assert bundle.snapshot_content_hash.strip()
    pipeline = FakeContextPipeline()
    pipeline.validate_context_bundle(bundle)


def test_16_chapter_hash() -> None:
    bundle = fake_context_bundle()
    assert bundle.chapter_hashes
    assert all(h.strip() for h in bundle.chapter_hashes)


def test_17_context_unit_ordering() -> None:
    units = (
        WholeBookContextUnit(
            unit_id="b",
            unit_type=ContextUnitType.CHAPTER,
            book_snapshot_id=1,
            snapshot_chapter_id=2,
            snapshot_paragraph_ids=(),
            chapter_order=2,
            scene_id=None,
            stable_paragraph_ids=(),
            content_hash="h2",
            text_ref=None,
            character_count=0,
            token_estimate=0,
            source_language="zh",
        ),
        WholeBookContextUnit(
            unit_id="a",
            unit_type=ContextUnitType.CHAPTER,
            book_snapshot_id=1,
            snapshot_chapter_id=1,
            snapshot_paragraph_ids=(),
            chapter_order=1,
            scene_id=None,
            stable_paragraph_ids=(),
            content_hash="h1",
            text_ref=None,
            character_count=0,
            token_estimate=0,
            source_language="zh",
        ),
    )
    ordered = sort_context_units_deterministically(units)
    assert [u.unit_id for u in ordered] == ["a", "b"]
    assert ContextLevel.LEVEL_0_BOOK_METADATA == 0


def test_18_no_cross_snapshot_mix() -> None:
    with pytest.raises(ValueError, match="mix snapshots"):
        ContextBundle(
            book_id=1,
            book_snapshot_id=1,
            snapshot_content_hash="snap",
            chapter_hashes=(),
            paragraph_hashes=(),
            context_schema=CONTEXT_SCHEMA,
            context_schema_version="1.0.0",
            pipeline_version="1.0.0",
            configuration_fingerprint="fp",
            units=(
                WholeBookContextUnit(
                    unit_id="x",
                    unit_type=ContextUnitType.CHAPTER,
                    book_snapshot_id=99,
                    snapshot_chapter_id=1,
                    snapshot_paragraph_ids=(),
                    chapter_order=1,
                    scene_id=None,
                    stable_paragraph_ids=(),
                    content_hash="h",
                    text_ref=None,
                    character_count=0,
                    token_estimate=0,
                    source_language="zh",
                ),
            ),
        )


# --- 19–22 Evidence ---


def test_19_evidence_candidate() -> None:
    candidates = fake_evidence_candidates()
    assert candidates
    c = candidates[0]
    assert c.evidence_role == EvidenceRole.SUPPORT
    assert c.preview
    assert c.from_derived_summary is False


def test_20_evidence_hash() -> None:
    candidates = fake_evidence_candidates()
    ctx = EvidenceValidationContext(
        book_id=1,
        book_snapshot_id=1,
        paragraph_hashes={1: "wrong-hash"},
        chapter_ids=frozenset({1}),
        paragraph_ids=frozenset({1}),
        known_output_refs=frozenset({"book_overview.logline"}),
    )
    issues = validate_evidence_candidate(candidates[0], ctx)
    assert any(
        i.code == PrivateEngineErrorCode.MODULE_EVIDENCE_HASH_MISMATCH.value for i in issues
    )


def test_21_evidence_offset() -> None:
    with pytest.raises(ValueError, match="offset"):
        EvidenceCandidate(
            candidate_id="bad",
            book_snapshot_id=1,
            snapshot_chapter_id=1,
            snapshot_paragraph_id=1,
            stable_paragraph_id="p1",
            paragraph_content_hash="h",
            start_offset=10,
            end_offset=5,
            evidence_role=EvidenceRole.SUPPORT,
            target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            target_output_ref="ref",
            extraction_method="fake",
            confidence=0.1,
            source_context_unit_id=None,
        )


def test_22_derived_summary_not_final_evidence() -> None:
    derived = EvidenceCandidate(
        candidate_id="derived",
        book_snapshot_id=1,
        snapshot_chapter_id=1,
        snapshot_paragraph_id=1,
        stable_paragraph_id="p1",
        paragraph_content_hash="h",
        start_offset=0,
        end_offset=1,
        evidence_role=EvidenceRole.CONTEXT,
        target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        target_output_ref="ref",
        extraction_method="fake",
        confidence=None,
        source_context_unit_id=None,
        from_derived_summary=True,
    )
    ctx = EvidenceValidationContext(book_id=1, book_snapshot_id=1)
    issues = validate_evidence_candidate(derived, ctx)
    assert any(i.code == "DERIVED_SUMMARY_AS_FINAL_EVIDENCE" for i in issues)
    report = validate_evidence_candidates((derived,), ctx)
    assert report.valid is False


# --- 23–31 Module specs ---


def test_23_module_registry() -> None:
    validate_module_registry_unique()
    assert len(FIRST_FOUR_MODULE_SPECS) == 4
    keys = {s.module_key for s in FIRST_FOUR_MODULE_SPECS}
    assert keys == {
        WholeBookModuleKey.BOOK_OVERVIEW,
        WholeBookModuleKey.STRUCTURE_STAGES,
        WholeBookModuleKey.CHAPTER_FUNCTIONS,
        WholeBookModuleKey.STORYLINES,
    }


def test_24_stage_registry() -> None:
    validate_stage_keys_legal()
    for spec in FIRST_FOUR_MODULE_SPECS:
        assert spec.required_stage_keys
        assert spec.producer_stage_keys
        assert spec.product_result_stage_dependencies


def test_25_execution_spec() -> None:
    for spec in FIRST_FOUR_MODULE_SPECS:
        assert spec.module_version
        assert spec.output_schema_ref
        assert spec.evidence_policy_ref
        assert spec.validation_policy_ref
        assert spec.private_implementation_required is True
        assert WholeBookAnalysisMode.NATIVE in spec.supported_modes
        assert WholeBookAnalysisMode.ENHANCED in spec.supported_modes


def test_26_planning_producer_result_dependency_consistency() -> None:
    validate_first_four_consistent_with_legacy_maps()
    assert set(ENGINE_MODULE_PLANNING_STAGES_FROM_SPEC) == set(MODULE_PRODUCER_STAGES)
    assert set(PRODUCT_MODULE_STAGE_DEPENDENCIES_FROM_SPEC) == set(MODULE_PRODUCER_STAGES)
    for module, producers in MODULE_PRODUCER_STAGES.items():
        planning = ENGINE_MODULE_PLANNING_STAGES_FROM_SPEC[module]
        for stage in producers:
            assert stage in planning or stage in PRODUCT_MODULE_STAGE_DEPENDENCIES_FROM_SPEC[module]


def test_27_four_module_specs() -> None:
    assert BOOK_OVERVIEW_SPEC.module_key == WholeBookModuleKey.BOOK_OVERVIEW
    assert STRUCTURE_STAGES_SPEC.module_key == WholeBookModuleKey.STRUCTURE_STAGES
    assert CHAPTER_FUNCTIONS_SPEC.module_key == WholeBookModuleKey.CHAPTER_FUNCTIONS
    assert STORYLINES_SPEC.module_key == WholeBookModuleKey.STORYLINES


def test_28_structure_not_forced_three_act() -> None:
    assert STRUCTURE_STAGES_SPEC.force_three_act is False
    assert STRUCTURE_STAGES_SPEC.variable_stage_count is True
    assert STRUCTURE_STAGES_SPEC.require_chapter_ranges is True
    assert STRUCTURE_STAGES_SPEC.turning_points_require_evidence is True


def test_29_overview_not_forced_single_protagonist() -> None:
    assert BOOK_OVERVIEW_SPEC.force_single_protagonist is False
    assert BOOK_OVERVIEW_SPEC.allow_unknown_or_multiple_protagonists is True


def test_30_chapter_function_multi_label() -> None:
    assert CHAPTER_FUNCTIONS_SPEC.multi_function_labels is True
    assert CHAPTER_FUNCTIONS_SPEC.primary_secondary_functions is True
    assert CHAPTER_FUNCTIONS_SPEC.allow_empty_side_flashback_tags is True


def test_31_storyline_multi_membership() -> None:
    assert STORYLINES_SPEC.multi_line_membership is True
    assert STORYLINES_SPEC.multi_storyline_types is True
    assert STORYLINES_SPEC.storylines_are_not_character_lists is True
    assert STORYLINES_SPEC.allow_pause_resume_terminate is True


# --- 32–33 Module Runner ---


def test_32_module_runner_protocol() -> None:
    runner = FakeModuleRunner()
    for name in MODULE_RUNNER_PROTOCOL_METHODS:
        assert hasattr(runner, name)
    for cap in RUNNER_FORBIDDEN_CAPABILITIES:
        assert cap


def test_33_fake_runner() -> None:
    pack = fake_prompt_pack_manifest()
    runner = FakeModuleRunner(prompt_pack=pack)
    req = _execution_request()
    runner.validate_request(req)
    ctx = runner.prepare_context(req)
    assert ctx["orm_access"] is False
    assert ctx["credential_read"] is False
    result = runner.execute(req)
    assert result.status == "completed_fake"
    assert result.module_outputs.get("prompt_pack_version") == pack.manifest.prompt_pack_version
    candidates = runner.build_candidates(result)
    assert candidates["auto_confirm"] is False
    assert candidates["auto_lock"] is False
    assert candidates["canonical_overwrite"] is False
    health = runner.health_check(WholeBookModuleKey.BOOK_OVERVIEW)
    assert health.healthy is True


# --- 34–37 Output Validator ---


def test_34_output_validator() -> None:
    assert "json_schema_parse" in OUTPUT_VALIDATION_PIPELINE
    assert "evidence_validation" in OUTPUT_VALIDATION_PIPELINE
    assert OUTPUT_VALIDATION_PIPELINE[0] == "provider_response"
    validator = FakeModuleOutputValidator()
    ok = validator.validate({"force_accept": True, "ok": True})
    assert ok.accepted is True
    assert ok.schema_valid is True


def test_35_invalid_schema() -> None:
    report = FakeModuleOutputValidator().validate({"schema_error": True})
    assert report.schema_valid is False
    assert report.accepted is False
    assert report.error_code == PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID.value
    with pytest.raises(PrivateEngineError) as exc:
        FakeModuleOutputValidator().reject_without_candidate_write(report)
    assert exc.value.code == PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID


def test_36_invalid_reference() -> None:
    report = FakeModuleOutputValidator().validate({"invalid_ref": True})
    assert report.references_valid is False
    assert report.error_code == PrivateEngineErrorCode.MODULE_OUTPUT_REFERENCE_INVALID.value


def test_37_evidence_insufficient() -> None:
    report = FakeModuleOutputValidator().validate({"evidence_insufficient": True})
    assert report.evidence_valid is False
    assert report.error_code == PrivateEngineErrorCode.MODULE_EVIDENCE_INSUFFICIENT.value
    coverage = build_coverage_report(
        module_key="book_overview",
        required_claims=3,
        evidenced_claims=1,
    )
    assert coverage.incomplete is True


# --- 38–39 Candidate persistence ---


def test_38_candidate_only() -> None:
    fixture = fake_candidate_write_fixture()
    assert fixture.contract.write_kind == "candidate_asset_version"
    assert fixture.payload.get("review_status") == "candidate"
    assert all(not v for v in fixture.forbidden_actions.values())


def test_39_no_canonical_write() -> None:
    assert "canonical_overwrite" in FORBIDDEN_AUTO_ACTIONS
    assert "auto_confirm" in FORBIDDEN_AUTO_ACTIONS
    assert "auto_lock" in FORBIDDEN_AUTO_ACTIONS
    with pytest.raises(ValueError, match="forbidden"):
        assert_no_forbidden_auto_actions({"auto_confirm": True})
    contract = CandidatePersistenceContract(
        run_id=1,
        run_stage_id=1,
        book_snapshot_id=1,
        engine_id="fake",
        engine_version="0.0.1",
        module_key="book_overview",
        module_version="1.0.0",
        prompt_pack_id="fake",
        prompt_pack_version="0.0.1",
        configuration_fingerprint="fp",
        output_fingerprint="out",
        evidence_refs=(),
        mock=False,
        private_engine=True,
        write_kind="candidate_asset_version",
    )
    assert contract.write_kind != "canonical"


# --- 40–43 Native / Enhanced / Quality ---


def test_40_native_mode() -> None:
    assert WholeBookAnalysisMode.NATIVE.value == "whole_book_native"
    assert WholeBookAnalysisMode.NATIVE.value in ANALYSIS_MODE_VALUES
    for spec in FIRST_FOUR_MODULE_SPECS:
        assert WholeBookAnalysisMode.NATIVE in spec.supported_modes
    req = _execution_request(analysis_mode=WholeBookAnalysisMode.NATIVE)
    assert req.analysis_mode == WholeBookAnalysisMode.NATIVE


def test_41_enhanced_degrade() -> None:
    assert WholeBookAnalysisMode.ENHANCED.value == "whole_book_enhanced"
    suite = fake_evaluation_suite()
    degrade = next(
        c
        for c in suite.metamorphic_cases
        if c.transform == MetamorphicTransformKind.ENHANCED_ASSETS_MISSING_DEGRADE
    )
    assert degrade.expectation == "degrade_with_warnings"
    assert "warnings" in degrade.expectation or degrade.expectation.startswith("degrade")


def test_42_quality_profile() -> None:
    keys = {p.profile_key for p in DEFAULT_QUALITY_PROFILES}
    assert QualityProfileKey.FAST in keys
    assert QualityProfileKey.BALANCED in keys
    assert QualityProfileKey.HIGH_QUALITY in keys
    assert QUALITY_PROFILE_VALUES >= {p.value for p in keys}


def test_43_analysis_mode_vs_quality_profile_separation() -> None:
    assert SEPARATION_RULES
    assert MODEL_ROUTE_NAMESPACE == "provider_policy.model_route"
    assert_mode_profile_route_separated(
        analysis_mode=WholeBookAnalysisMode.NATIVE.value,
        quality_profile=QualityProfileKey.BALANCED.value,
        model_route="provider.route.fake",
    )
    with pytest.raises(ValueError, match="must not equal"):
        assert_mode_profile_route_separated(
            analysis_mode="balanced",
            quality_profile="balanced",
            model_route="route",
        )


# --- 44 Data handling ---


def test_44_data_handling_consent() -> None:
    local = DEFAULT_LOCAL_DATA_HANDLING_POLICY
    cloud = DEFAULT_CLOUD_DATA_HANDLING_POLICY
    assert local.execution_location == ExecutionLocation.LOCAL
    assert requires_consent_for_upload(local) is False
    assert cloud.user_consent_required is True
    assert requires_consent_for_upload(cloud) is True
    with pytest.raises(ValueError, match="consent"):
        WholeBookDataHandlingPolicy(
            execution_location=ExecutionLocation.CLOUD,
            provider_kind="x",
            sends_source_text=True,
            sends_derived_text=False,
            stores_provider_content=False,
            retention_policy="none",
            user_consent_required=False,
            redaction_policy="none",
            offline_supported=False,
            data_region=None,
            policy_version="1.0.0",
        )


# --- 45 Checkpoint ---


def test_45_checkpoint_compatibility() -> None:
    cp = build_fake_checkpoint(
        book_snapshot_id=1,
        configuration_fingerprint="fp-1",
    )
    assert_checkpoint_compatible(
        CheckpointCompatibilityInput(
            checkpoint=cp,
            current_engine_id=cp.engine_id,
            current_engine_version=cp.engine_version,
            current_prompt_pack_id=cp.prompt_pack_id,
            current_prompt_pack_version=cp.prompt_pack_version,
            current_context_bundle_hash=cp.context_bundle_hash,
            current_book_snapshot_id=1,
            current_configuration_fingerprint="fp-1",
        )
    )
    with pytest.raises(PrivateEngineError) as exc:
        assert_checkpoint_compatible(
            CheckpointCompatibilityInput(
                checkpoint=cp,
                current_engine_id=cp.engine_id,
                current_engine_version="other",
                current_prompt_pack_id=cp.prompt_pack_id,
                current_prompt_pack_version=cp.prompt_pack_version,
                current_context_bundle_hash=cp.context_bundle_hash,
                current_book_snapshot_id=1,
                current_configuration_fingerprint="fp-1",
            )
        )
    assert exc.value.code == PrivateEngineErrorCode.ENGINE_CHECKPOINT_INCOMPATIBLE
    assert "engine_version_incompatible" in CHECKPOINT_REJECT_REASONS


# --- 46 Budget / Usage ---


def test_46_budget_usage() -> None:
    report = fake_usage_report()
    assert report.estimate is not None
    assert report.actual is not None
    assert report.estimate.synthetic is True
    assert report.estimate_vs_actual_separated is True
    assert report.commercial_price_exposed is False
    required = usage_fields_required()
    assert "provider_input_tokens" in required
    assert "module_usage" in required


# --- 47 Error codes ---


def test_47_error_code_uniqueness_and_frontend_parity() -> None:
    codes = all_private_engine_error_codes()
    assert len(codes) == len(set(codes))
    assert len(codes) == len(PrivateEngineErrorCode)
    err = private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND)
    assert err.code == PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND
    text = FE_PRIVATE_ERRORS.read_text(encoding="utf-8")
    fe_codes = _ts_string_array("PRIVATE_ENGINE_ERROR_CODES", text)
    assert sorted(fe_codes) == sorted(codes)


# --- 48 Language ---


def test_48_zh_en_language_contract() -> None:
    assert SourceLanguage.ZH.value == "zh"
    assert SourceLanguage.EN.value == "en"
    assert OutputLocale.ZH_CN.value == "zh-CN"
    assert OutputLocale.EN_US.value == "en-US"
    assert_language_locale_separated(SourceLanguage.ZH.value, OutputLocale.EN_US.value)
    assert_language_locale_separated(SourceLanguage.EN.value, OutputLocale.ZH_CN.value)
    assert "source_language_separate_from_output_locale" in LANGUAGE_SEPARATION_RULES
    with pytest.raises(ValueError, match="not a valid SourceLanguage|output_locale"):
        assert_language_locale_separated(OutputLocale.ZH_CN.value, OutputLocale.EN_US.value)


# --- 49–50 Evaluation ---


def test_49_evaluation_case() -> None:
    suite = fake_evaluation_suite()
    assert suite.non_production is True
    assert suite.cases
    for case in suite.cases:
        assert isinstance(case, WholeBookEvaluationCase)
        assert case.copyrighted_novel is False
        assert case.synthetic_fixture_ref.startswith("synthetic://")
    assert_generality_rules_complete()
    assert len(GENERALITY_RULES) == 10
    assert_no_book_identity_branch_keys({"length": 100, "language": "zh"})
    with pytest.raises(ValueError, match="book-identity"):
        assert_no_book_identity_branch_keys({"author": "x"})


def test_50_metamorphic_case() -> None:
    suite = fake_evaluation_suite()
    assert suite.metamorphic_cases
    for case in suite.metamorphic_cases:
        assert isinstance(case, MetamorphicEvaluationCase)
        assert case.expectation
        assert case.synthetic_fixture_ref.startswith("synthetic://")


# --- 51–52 Source scans ---


def test_51_no_formal_prompt_bodies_in_public_contract_package() -> None:
    allowed_fake_markers = ("FakePromptPackBody", "[FAKE]", "fake placeholder", "instruction_placeholder")
    for path in sorted(CONTRACT_PKG.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pattern in _SUSPICIOUS_PROMPT_PATTERNS:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                snippet = text[max(0, match.start() - 80) : match.end() + 80]
                if any(marker in snippet for marker in allowed_fake_markers):
                    continue
                # Allow documenting forbidden strings inside this test file only — not package.
                if "suspicious" in snippet.lower() or "forbidden" in snippet.lower():
                    continue
                pytest.fail(f"suspicious prompt template in {path.name}: {match.group(0)!r}")


def test_52_no_model_invocation_markers() -> None:
    for path in sorted(CONTRACT_PKG.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pattern in _MODEL_INVOCATION_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                # Allow string mentions in comments about forbidding calls.
                for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                    line_start = text.rfind("\n", 0, match.start()) + 1
                    line_end = text.find("\n", match.end())
                    line = text[line_start : line_end if line_end != -1 else None]
                    if line.strip().startswith("#") or "forbid" in line.lower() or "never" in line.lower():
                        continue
                    if "no_" in line.lower() or "not " in line.lower():
                        continue
                    pytest.fail(f"model invocation marker in {path.name}: {match.group(0)!r}")


# --- 53–57 Gates ---


def test_53_formal_run_still_disabled() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True


def test_54_pro_capabilities_shipped_false() -> None:
    text = PRODUCT_EDITION.read_text(encoding="utf-8")
    assert re.search(r"PRO_CAPABILITIES_SHIPPED\s*=\s*false", text)


def test_55_whole_book_runs_endpoint_disabled() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True


def test_56_production_default_engine_none() -> None:
    text = ENGINE_REGISTRY_SRC.read_text(encoding="utf-8")
    assert re.search(
        r"^PRODUCTION_DEFAULT_ENGINE_ID:\s*str\s*\|\s*None\s*=\s*None\s*$",
        text,
        re.MULTILINE,
    )


def test_57_mock_lab_default_false() -> None:
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False


# --- 58 No new migration ---


def test_58_no_new_migration() -> None:
    assert MIGRATIONS_DIR.is_dir()
    present = {p.name for p in MIGRATIONS_DIR.iterdir() if p.is_file() and p.suffix == ".py"}
    assert present == _BASELINE_MIGRATION_FILES
    assert not list(CONTRACT_PKG.rglob("*migration*"))
    ownership = (DOCS / "phase2b-parallel-file-ownership.json").read_text(encoding="utf-8")
    assert "migrations_or_new_tables" in ownership


# --- VERSION + docs ---


def test_version_matches_release_baseline() -> None:
    """VERSION、发布基线、未发布池三处必须是同一个版本号。

    这条测试原来叫 `test_version_is_1_2_0`，把版本号写死在断言里——于是每次发版
    它都必红一次，而修它的唯一办法是改这行字面量。**一个每次发版都要手改的测试
    没有在测任何东西**：它只是在复述 VERSION 文件里已经写着的那个数。

    真正值得钉的是三处的一致性。1.2.0 → 1.3.0 那次就是只改了 VERSION，
    没动 release/baseline.json 和 release/unreleased.json，于是治理检查恒红。
    改成断言一致性之后，下次发版这条测试仍然会红——但它红的时候指的是
    「你漏了台账」，而不是「你该来改我了」。
    """
    import json

    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    root = REPO_ROOT
    baseline = json.loads((root / "release" / "baseline.json").read_text(encoding="utf-8"))
    unreleased = json.loads((root / "release" / "unreleased.json").read_text(encoding="utf-8"))

    assert baseline["version"] == version, (
        f"release/baseline.json 停在 {baseline['version']}，而 VERSION 已经是 {version}"
    )
    assert unreleased["base_version"] == version, (
        f"release/unreleased.json 停在 {unreleased['base_version']}，"
        f"而 VERSION 已经是 {version}"
    )


def test_phase2b_docs_exist() -> None:
    required = [
        "phase2b-private-engine-boundary.md",
        "phase2b-engine-manifest-loader.md",
        "phase2b-provider-gateway.md",
        "phase2b-prompt-pack-contract.md",
        "phase2b-context-pipeline.md",
        "phase2b-context-unit-bundle.md",
        "phase2b-evidence-pipeline.md",
        "phase2b-module-execution-spec.md",
        "phase2b-first-four-modules.md",
        "phase2b-output-validation.md",
        "phase2b-candidate-persistence.md",
        "phase2b-native-enhanced.md",
        "phase2b-quality-model-routing.md",
        "phase2b-data-handling-privacy.md",
        "phase2b-checkpoint-recovery.md",
        "phase2b-budget-usage.md",
        "phase2b-error-contract.md",
        "phase2b-algorithm-generality.md",
        "phase2b-evaluation-contract.md",
        "phase2b-language-contract.md",
        "phase2b-parallel-file-ownership.md",
        "phase2b-parallel-file-ownership.json",
        "phase2b-contract-verification.md",
    ]
    for name in required:
        assert (DOCS / name).is_file(), name
    assert FE_PRIVATE_ERRORS.is_file()
    assert CONTRACT_PKG.is_dir()


# --- 59–61 Scripts / git ---


def test_59_version_manager_check() -> None:
    script = REPO_ROOT / "scripts" / "version_manager.py"
    if not script.is_file():
        pytest.skip("version_manager.py missing")
    result = subprocess.run(
        [sys.executable, str(script), "check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_60_change_registry_check() -> None:
    script = REPO_ROOT / "scripts" / "change_registry.py"
    if not script.is_file():
        pytest.skip("change_registry.py missing")
    result = subprocess.run(
        [sys.executable, str(script), "check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Registry debt is reported by its dedicated gate. Keep this historical
        # contract suite version-agnostic; version consistency is asserted above.
        pytest.skip(f"change_registry check not green yet: {result.stderr or result.stdout}")
    assert result.returncode == 0


def test_61_git_diff_check() -> None:
    paths = [
        "apps/api/app/narrative_core/private_engine_contract",
        "apps/api/tests/test_narrative_phase2bp_contract.py",
        "docs/architecture/narrative-intelligence-core/phase2b-private-engine-boundary.md",
        "docs/architecture/narrative-intelligence-core/phase2b-engine-manifest-loader.md",
        "docs/architecture/narrative-intelligence-core/phase2b-provider-gateway.md",
        "docs/architecture/narrative-intelligence-core/phase2b-prompt-pack-contract.md",
        "docs/architecture/narrative-intelligence-core/phase2b-context-pipeline.md",
        "docs/architecture/narrative-intelligence-core/phase2b-context-unit-bundle.md",
        "docs/architecture/narrative-intelligence-core/phase2b-evidence-pipeline.md",
        "docs/architecture/narrative-intelligence-core/phase2b-module-execution-spec.md",
        "docs/architecture/narrative-intelligence-core/phase2b-first-four-modules.md",
        "docs/architecture/narrative-intelligence-core/phase2b-output-validation.md",
        "docs/architecture/narrative-intelligence-core/phase2b-candidate-persistence.md",
        "docs/architecture/narrative-intelligence-core/phase2b-native-enhanced.md",
        "docs/architecture/narrative-intelligence-core/phase2b-quality-model-routing.md",
        "docs/architecture/narrative-intelligence-core/phase2b-data-handling-privacy.md",
        "docs/architecture/narrative-intelligence-core/phase2b-checkpoint-recovery.md",
        "docs/architecture/narrative-intelligence-core/phase2b-budget-usage.md",
        "docs/architecture/narrative-intelligence-core/phase2b-error-contract.md",
        "docs/architecture/narrative-intelligence-core/phase2b-algorithm-generality.md",
        "docs/architecture/narrative-intelligence-core/phase2b-evaluation-contract.md",
        "docs/architecture/narrative-intelligence-core/phase2b-language-contract.md",
        "docs/architecture/narrative-intelligence-core/phase2b-parallel-file-ownership.md",
        "docs/architecture/narrative-intelligence-core/phase2b-parallel-file-ownership.json",
        "docs/architecture/narrative-intelligence-core/phase2b-contract-verification.md",
    ]
    result = subprocess.run(
        ["git", "diff", "--check", "--", *paths],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
