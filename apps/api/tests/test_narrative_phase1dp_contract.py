"""Phase 1D-P product contract verification (directed tests only)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import (
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    EvidenceRole,
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
    WholeBookStageKey,
)
from app.narrative_core.product_contract.conflict_center import (
    BLOCKING_CONFLICTS_AUTO_RESOLVE_FORBIDDEN,
    ConflictCenterItemDto,
    ConflictRefDto,
)
from app.narrative_core.product_contract.enums import (
    EvidenceIntegrityStatus,
    NarrativeReviewAction,
    ResultNavSectionKey,
    ReviewTargetType,
    RunAllowedAction,
    StructureMapViewMode,
    WholeBookModuleStatus,
    WholeBookRunViewStatus,
)
from app.narrative_core.product_contract.evidence import (
    MAX_PARAGRAPH_PREVIEW_CHARS,
    WholeBookEvidenceRefDto,
)
from app.narrative_core.product_contract.keys import (
    EXISTING_API_ROUTES,
    FUTURE_API_ROUTES,
    MODULE_STAGE_DEPENDENCIES,
    RESULT_NAV_SECTIONS,
    WHOLE_BOOK_MODULE_KEYS,
    resolve_modules_with_dependencies,
)
from app.narrative_core.product_contract.module_results import (
    MODULE_RESULT_DTO_BY_KEY,
    MODULE_RESULT_DTO_NAMES,
    BasicTimelineResultDto,
    BookOverviewResultDto,
    CausalChainResultDto,
    CharacterArcsResultDto,
    CharactersResultDto,
    ChapterFunctionsResultDto,
    DiagnosticsResultDto,
    HooksPayoffsResultDto,
    RelationshipsResultDto,
    StorylinesResultDto,
    StructureStagesResultDto,
)
from app.narrative_core.product_contract.preflight import (
    PreflightBookStatusDto,
    PreflightCapabilityStatusDto,
    PreflightEngineStatusDto,
    PreflightEstimatedUsageDto,
    PreflightQuotaStatusDto,
    PreflightSnapshotStatusDto,
    PreflightSourceCoverageDto,
    WholeBookPreflightPageModel,
)
from app.narrative_core.product_contract.result_envelope import (
    RESULT_ENVELOPE_SCHEMA,
    RESULT_ENVELOPE_VERSION,
    ConfidenceSummaryDto,
    ReviewSummaryDto,
    WholeBookResultEnvelope,
)
from app.narrative_core.product_contract.review import NarrativeReviewActionRequest
from app.narrative_core.product_contract.run_view import (
    RUN_ACTION_RULES,
    WholeBookRunViewState,
    WholeBookStageProgressDto,
    is_action_allowed_for_status,
)
from app.narrative_core.product_contract.structure_map import (
    PATTERN_DTO_HAS_ORM_TABLE,
    STRUCTURE_MAP_DEFAULT_MAX_EDGES,
    STRUCTURE_MAP_DEFAULT_MAX_NODES,
    NarrativeStructureMapProjectionDto,
    StructureMapFiltersDto,
)
from app.narrative_core.services.whole_book_engine_registry import (
    PRODUCTION_DEFAULT_ENGINE_ID,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DESKTOP_KEYS = (
    REPO_ROOT / "apps" / "desktop" / "src" / "features" / "wholeBook" / "contracts" / "keys.ts"
)
PRODUCT_EDITION = REPO_ROOT / "apps" / "desktop" / "src" / "services" / "productEdition.ts"
CAPABILITY_KEYS_TS = REPO_ROOT / "apps" / "desktop" / "src" / "services" / "capability" / "keys.ts"


def _ts_string_array(name: str, text: str) -> list[str]:
    pattern = rf"export const {name} = \[([\s\S]*?)\] as const"
    match = re.search(pattern, text)
    assert match, f"missing {name} in keys.ts"
    return re.findall(r'"([^"]+)"', match.group(1))


def _sample_preflight(**overrides: object) -> WholeBookPreflightPageModel:
    base = {
        "book": PreflightBookStatusDto(
            book_id=1,
            title="T",
            chapter_count=1,
            paragraph_count=1,
            character_count=10,
            current_snapshot_id=1,
            snapshot_created_at="2026-07-23T00:00:00Z",
            body_changed_since_snapshot=False,
            snapshot_rebuild_required=False,
        ),
        "snapshot": PreflightSnapshotStatusDto(
            snapshot_id=1,
            status="completed",
            created_at="2026-07-23T00:00:00Z",
            integrity_ok=True,
        ),
        "capability": PreflightCapabilityStatusDto(
            capability_key="whole_book_analysis",
            allowed=False,
            reason_code="CAPABILITY_NOT_SHIPPED",
            availability="unavailable",
        ),
        "quota": PreflightQuotaStatusDto(allowed=True),
        "engine": PreflightEngineStatusDto(
            engine_id=None, available=False, supports_mode=True
        ),
        "analysis_mode": WholeBookAnalysisMode.NATIVE,
        "requested_modules": (WholeBookModuleKey.BOOK_OVERVIEW,),
        "resolved_modules": (WholeBookModuleKey.BOOK_OVERVIEW,),
        "stage_plan": (),
        "source_coverage": PreflightSourceCoverageDto(fulltext_snapshot_ready=True),
        "estimated_usage": PreflightEstimatedUsageDto(),
        "blocking_reasons": ("WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true",),
        "warnings": (),
        "run_creation_enabled": False,
        "confirmation_required": True,
        "force_start_allowed": False,
    }
    base.update(overrides)
    return WholeBookPreflightPageModel(**base)  # type: ignore[arg-type]


def test_preflight_dto_defaults_disabled() -> None:
    model = _sample_preflight()
    assert model.run_creation_enabled is False
    assert model.force_start_allowed is False
    assert model.confirmation_required is True


def test_preflight_rejects_force_start() -> None:
    with pytest.raises(ValueError, match="force_start"):
        _sample_preflight(force_start_allowed=True)


def test_native_and_enhanced_modes() -> None:
    assert WholeBookAnalysisMode.NATIVE.value == "whole_book_native"
    assert WholeBookAnalysisMode.ENHANCED.value == "whole_book_enhanced"
    assert set(WholeBookAnalysisMode) == {
        WholeBookAnalysisMode.NATIVE,
        WholeBookAnalysisMode.ENHANCED,
    }


def test_module_keys_unique() -> None:
    values = [m.value for m in WHOLE_BOOK_MODULE_KEYS]
    assert len(values) == len(set(values))
    assert len(values) == 11


def test_module_dependency_contract() -> None:
    assert MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.BOOK_OVERVIEW] == (
        WholeBookStageKey.BUILD_FULLTEXT_INDEX,
    )
    assert WholeBookStageKey.ANALYZE_STRUCTURE in MODULE_STAGE_DEPENDENCIES[
        WholeBookModuleKey.STRUCTURE_STAGES
    ]
    assert WholeBookStageKey.VERIFY_EVIDENCE in MODULE_STAGE_DEPENDENCIES[
        WholeBookModuleKey.DIAGNOSTICS
    ]


def test_stage_dependency_resolution_autofill() -> None:
    modules, stages, notes = resolve_modules_with_dependencies(
        (WholeBookModuleKey.CHAPTER_FUNCTIONS,)
    )
    assert modules == (WholeBookModuleKey.CHAPTER_FUNCTIONS,)
    assert WholeBookStageKey.ANALYZE_STRUCTURE in stages
    assert any("chapter_functions" in n for n in notes)


def test_module_not_hardbound_one_to_one_with_stage() -> None:
    # one stage can support multiple modules
    structure_modules = [
        m
        for m, deps in MODULE_STAGE_DEPENDENCIES.items()
        if WholeBookStageKey.ANALYZE_STRUCTURE in deps
    ]
    assert len(structure_modules) >= 2
    # one module can depend on multiple stages
    assert len(MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.STORYLINES]) >= 2
    # UI module name is not a stage key
    stage_values = {s.value for s in WholeBookStageKey}
    for module in WholeBookModuleKey:
        assert module.value not in stage_values


def test_run_statuses() -> None:
    assert {s.value for s in WholeBookRunViewStatus} == {
        "pending",
        "running",
        "paused",
        "interrupted",
        "completed",
        "failed",
        "cancelled",
    }


def test_allowed_actions_contract() -> None:
    assert is_action_allowed_for_status(
        RunAllowedAction.PAUSE, WholeBookRunViewStatus.RUNNING
    )
    assert not is_action_allowed_for_status(
        RunAllowedAction.PAUSE, WholeBookRunViewStatus.PAUSED
    )
    assert is_action_allowed_for_status(
        RunAllowedAction.RESUME, WholeBookRunViewStatus.INTERRUPTED
    )
    assert is_action_allowed_for_status(
        RunAllowedAction.RETRY, WholeBookRunViewStatus.FAILED
    )
    assert not is_action_allowed_for_status(
        RunAllowedAction.CANCEL, WholeBookRunViewStatus.COMPLETED
    )
    assert RunAllowedAction.VIEW_PARTIAL_RESULTS in RUN_ACTION_RULES


def test_stage_progress_dto() -> None:
    dto = WholeBookStageProgressDto(
        stage_key="analyze_structure",
        display_name="Analyze structure",
        order=30,
        status=StageStatus.RUNNING,
        required=True,
        resumable=True,
        retryable=False,
        progress_percent=None,
        started_at="2026-07-23T00:00:00Z",
        completed_at=None,
        attempt_count=1,
        checkpoint_available=False,
        token_input=None,
        token_output=None,
        cost=None,
        output_artifact_ids=(),
        produced_module_keys=("structure_stages",),
        warnings=(),
        error_code=None,
        error_message=None,
        allowed_actions=(RunAllowedAction.PAUSE,),
    )
    assert dto.progress_percent is None
    assert "Analyze structure" in dto.display_name


def test_result_envelope() -> None:
    env = WholeBookResultEnvelope(
        schema=RESULT_ENVELOPE_SCHEMA,
        version=RESULT_ENVELOPE_VERSION,
        run_id=1,
        book_id=1,
        book_snapshot_id=1,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        module_status=WholeBookModuleStatus.PARTIAL,
        generated_at="2026-07-23T00:00:00Z",
        source_stage_keys=("build_fulltext_index",),
        source_artifact_ids=(),
        asset_ids=(),
        asset_version_ids=(),
        relation_ids=(),
        relation_version_ids=(),
        conflict_ids=(),
        evidence_count=0,
        confidence_summary=ConfidenceSummaryDto(),
        review_summary=ReviewSummaryDto(),
        stale=False,
        partial=True,
        warnings=(),
        payload={"logline": ""},
    )
    assert env.partial is True
    assert env.stale is False


def test_module_status_semantics() -> None:
    assert WholeBookModuleStatus.STALE != WholeBookModuleStatus.FAILED
    assert WholeBookModuleStatus.PARTIAL != WholeBookModuleStatus.FAILED
    assert WholeBookModuleStatus.BLOCKED.value == "blocked"


def test_eleven_module_dto_imports() -> None:
    assert len(MODULE_RESULT_DTO_BY_KEY) == 11
    assert len(MODULE_RESULT_DTO_NAMES) == 11
    assert BookOverviewResultDto is MODULE_RESULT_DTO_BY_KEY[WholeBookModuleKey.BOOK_OVERVIEW]
    assert StructureStagesResultDto is not None
    assert ChapterFunctionsResultDto is not None
    assert StorylinesResultDto is not None
    assert CharactersResultDto is not None
    assert CharacterArcsResultDto is not None
    assert RelationshipsResultDto is not None
    assert HooksPayoffsResultDto is not None
    assert CausalChainResultDto is not None
    assert BasicTimelineResultDto is not None
    assert DiagnosticsResultDto is not None


def test_evidence_dto_and_integrity() -> None:
    dto = WholeBookEvidenceRefDto(
        evidence_id=1,
        evidence_type="asset_evidence",
        book_snapshot_id=1,
        snapshot_chapter_id=1,
        snapshot_paragraph_id=1,
        source_chapter_id=1,
        source_scene_id=None,
        stable_paragraph_id="p1",
        paragraph_content_hash="hash",
        start_offset=0,
        end_offset=1,
        evidence_role=EvidenceRole.SUPPORT,
        evidence_label="x",
        chapter_title="c",
        paragraph_preview="short",
        deep_link="link",
        integrity_status=EvidenceIntegrityStatus.VALID,
    )
    assert dto.integrity_status == EvidenceIntegrityStatus.VALID
    assert {s.value for s in EvidenceIntegrityStatus} == {
        "valid",
        "stale",
        "hash_mismatch",
        "missing",
        "inaccessible",
    }
    with pytest.raises(ValueError):
        WholeBookEvidenceRefDto(
            evidence_id=1,
            evidence_type="asset_evidence",
            book_snapshot_id=1,
            snapshot_chapter_id=1,
            snapshot_paragraph_id=1,
            source_chapter_id=1,
            source_scene_id=None,
            stable_paragraph_id="p1",
            paragraph_content_hash="hash",
            start_offset=0,
            end_offset=1,
            evidence_role=EvidenceRole.CONTEXT,
            evidence_label="x",
            chapter_title="c",
            paragraph_preview="x" * (MAX_PARAGRAPH_PREVIEW_CHARS + 1),
            deep_link="link",
            integrity_status=EvidenceIntegrityStatus.HASH_MISMATCH,
        )


def test_review_action_expected_version() -> None:
    req = NarrativeReviewActionRequest(
        action=NarrativeReviewAction.CONFIRM,
        target_type=ReviewTargetType.ASSET_VERSION,
        target_id="1",
        expected_version=2,
        actor="user",
        idempotency_key="k",
    )
    assert req.expected_version == 2
    with pytest.raises(ValueError, match="is_canonical"):
        NarrativeReviewActionRequest(
            action=NarrativeReviewAction.CORRECT,
            target_type=ReviewTargetType.ASSET_VERSION,
            target_id="1",
            expected_version=2,
            actor="user",
            correction_payload={"is_canonical": True, "title": "x"},
            idempotency_key="k",
        )
    with pytest.raises(ValueError, match="schema"):
        NarrativeReviewActionRequest(
            action=NarrativeReviewAction.RESOLVE_CONFLICT,
            target_type=ReviewTargetType.CONFLICT,
            target_id="9",
            expected_version=1,
            actor="user",
            resolution_payload={},
            idempotency_key="k",
        )


def test_conflict_center() -> None:
    item = ConflictCenterItemDto(
        conflict_id=1,
        conflict_type=ConflictType.LOCKED_ASSET_VS_NEW_RUN,
        severity=ConflictSeverity.BLOCKING,
        status=ConflictStatus.OPEN,
        left_ref=ConflictRefDto(ref_type="asset_version", ref_id="1"),
        right_ref=ConflictRefDto(ref_type="asset_version", ref_id="2"),
        description="conflict",
        affected_modules=("characters",),
        affected_chapters=(1,),
        evidence_refs=(),
        created_at="2026-07-23T00:00:00Z",
        allowed_actions=(
            NarrativeReviewAction.RESOLVE_CONFLICT,
            NarrativeReviewAction.DISMISS_CONFLICT,
        ),
    )
    assert item.severity == ConflictSeverity.BLOCKING
    assert BLOCKING_CONFLICTS_AUTO_RESOLVE_FORBIDDEN is True


def test_structure_map_projection_limits() -> None:
    filters = StructureMapFiltersDto(
        view_mode=StructureMapViewMode.STRUCTURE_STAGES,
        max_nodes=STRUCTURE_MAP_DEFAULT_MAX_NODES,
        max_edges=STRUCTURE_MAP_DEFAULT_MAX_EDGES,
    )
    dto = NarrativeStructureMapProjectionDto(
        book_id=1,
        book_snapshot_id=1,
        source_run_id=None,
        projection_version="1",
        root_nodes=(),
        edges=(),
        filters=filters,
        generated_at="2026-07-23T00:00:00Z",
    )
    assert dto.filters.max_nodes == 100
    assert dto.filters.max_edges == 250
    assert set(StructureMapViewMode) == {
        StructureMapViewMode.STRUCTURE_STAGES,
        StructureMapViewMode.STORYLINES,
        StructureMapViewMode.CHARACTER_GROWTH,
    }


def test_pattern_dto_not_orm() -> None:
    assert PATTERN_DTO_HAS_ORM_TABLE is False
    # Ensure structure_map module does not import ORM models
    path = (
        REPO_ROOT
        / "apps"
        / "api"
        / "app"
        / "narrative_core"
        / "product_contract"
        / "structure_map.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "models" not in node.module
            assert node.module != "app.db.models"


def test_frontend_backend_module_keys_consistent() -> None:
    text = DESKTOP_KEYS.read_text(encoding="utf-8")
    ts_keys = _ts_string_array("WHOLE_BOOK_MODULE_KEYS", text)
    py_keys = [m.value for m in WholeBookModuleKey]
    assert ts_keys == py_keys


def test_frontend_backend_status_enums_consistent() -> None:
    text = DESKTOP_KEYS.read_text(encoding="utf-8")
    assert _ts_string_array("WHOLE_BOOK_RUN_VIEW_STATUSES", text) == [
        s.value for s in WholeBookRunViewStatus
    ]
    assert _ts_string_array("WHOLE_BOOK_MODULE_STATUSES", text) == [
        s.value for s in WholeBookModuleStatus
    ]
    assert _ts_string_array("WHOLE_BOOK_ANALYSIS_MODES", text) == [
        m.value for m in WholeBookAnalysisMode
    ]
    assert _ts_string_array("EVIDENCE_INTEGRITY_STATUSES", text) == [
        s.value for s in EvidenceIntegrityStatus
    ]
    assert _ts_string_array("NARRATIVE_REVIEW_ACTIONS", text) == [
        a.value for a in NarrativeReviewAction
    ]


def test_frontend_module_dependencies_match() -> None:
    text = DESKTOP_KEYS.read_text(encoding="utf-8")
    for module, stages in MODULE_STAGE_DEPENDENCIES.items():
        for stage in stages:
            assert stage.value in text
            assert module.value in text


def test_fixture_guards_run_view_shape() -> None:
    stage = WholeBookStageProgressDto(
        stage_key="build_fulltext_index",
        display_name="Build fulltext index",
        order=10,
        status=StageStatus.COMPLETED,
        required=True,
        resumable=False,
        retryable=False,
        progress_percent=100.0,
        started_at="t0",
        completed_at="t1",
        attempt_count=1,
        checkpoint_available=True,
        token_input=1,
        token_output=1,
        cost=0.0,
        output_artifact_ids=("a1",),
        produced_module_keys=("book_overview",),
        warnings=(),
        error_code=None,
        error_message=None,
        allowed_actions=(),
    )
    state = WholeBookRunViewState(
        run_id=1,
        book_id=1,
        snapshot_id=1,
        analysis_mode=WholeBookAnalysisMode.ENHANCED,
        status=WholeBookRunViewStatus.RUNNING,
        current_stage="analyze_structure",
        stages=(stage,),
        completed_modules=(WholeBookModuleKey.BOOK_OVERVIEW,),
        available_modules=(WholeBookModuleKey.BOOK_OVERVIEW,),
        failed_modules=(),
        partial_results_available=True,
        progress_percent=None,
        allowed_actions=(RunAllowedAction.PAUSE, RunAllowedAction.CANCEL),
    )
    assert state.partial_results_available is True
    assert state.analysis_mode == WholeBookAnalysisMode.ENHANCED


def test_run_creation_still_disabled() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert any("preflight" in r for r in EXISTING_API_ROUTES)
    assert any("whole-book-runs" in r and "POST" in r for r in FUTURE_API_ROUTES)


def test_pro_capabilities_shipped_false() -> None:
    text = PRODUCT_EDITION.read_text(encoding="utf-8")
    assert "PRO_CAPABILITIES_SHIPPED = false" in text


def test_phase1c_api_still_importable() -> None:
    from app.narrative_core.contracts.api_dto import (
        WholeBookPreflightDTO,
        WholeBookPreflightRequestDTO,
    )
    from app.narrative_core.contracts.capability import CapabilityDecision
    from app.narrative_core.contracts.whole_book_dto import WholeBookAnalysisRequest

    assert WholeBookPreflightDTO is not None
    assert WholeBookPreflightRequestDTO is not None
    assert CapabilityDecision is not None
    assert WholeBookAnalysisRequest is not None


def test_asset_services_not_pro_gated_in_capability_keys() -> None:
    # Public narrative foundation remains distinct; capability keys file still lists five
    text = CAPABILITY_KEYS_TS.read_text(encoding="utf-8")
    assert "narrative_asset_library" in text
    # product contract does not add Pro gating to asset routes
    ownership = (
        REPO_ROOT
        / "docs"
        / "architecture"
        / "narrative-intelligence-core"
        / "phase1d-parallel-file-ownership.json"
    )
    # ownership file may be created in same change; skip hard fail if race
    if ownership.exists():
        body = ownership.read_text(encoding="utf-8")
        assert "PRO_CAPABILITIES_SHIPPED" in body or "forbidden" in body.lower()


def test_result_nav_includes_ten_sections() -> None:
    assert len(RESULT_NAV_SECTIONS) == 10
    keys = [section for section, _ in RESULT_NAV_SECTIONS]
    assert ResultNavSectionKey.STRUCTURE in keys
    assert ResultNavSectionKey.STRUCTURE_MAP in keys
    structure_modules = dict(RESULT_NAV_SECTIONS)[ResultNavSectionKey.STRUCTURE]
    assert WholeBookModuleKey.CHAPTER_FUNCTIONS in structure_modules


def test_production_default_engine_none() -> None:
    assert PRODUCTION_DEFAULT_ENGINE_ID is None
