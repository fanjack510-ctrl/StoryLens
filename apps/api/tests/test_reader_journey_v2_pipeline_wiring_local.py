"""Local tests: Reader Journey V2 default pipeline wiring (no live model calls)."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.reader_journey_v2 import (
    FORMULA_VERSION_V2,
    SCENE_CONTRACT_VERSION_V2,
    SCENE_PROMPT_VERSION_V2,
    ScoredLevelField,
    SceneReaderJourneyProfileItemV2,
)
from app.services.reader_journey_v2_finalize import finalize_v2_profiles
from app.services.reader_journey_v2_persist import (
    build_v2_deterministic_statistics,
    persist_finalized_v2_profiles,
    strip_model_mapped_scores,
)
from app.services.reader_journey_version import (
    DIAGNOSES_ORIGIN_PROGRAM,
    SCORES_ORIGIN_PROGRAM,
    SOURCE_MODE_V2_NATIVE,
    is_legacy_journey_run,
    is_v2_journey_run,
    new_journey_version_fields,
    resolve_versions_for_new_run,
)


def _level(level: int = 3, mapped: int | None = None) -> ScoredLevelField:
    return ScoredLevelField(
        level=level,
        mapped_score=mapped,
        evidence_paragraph_ids=["P0001"],
        rationale="r",
        confidence=0.8,
    )


def _minimal_v2_profile(ordinal: int = 1, scene_id: int = 10) -> SceneReaderJourneyProfileItemV2:
    fields = {
        key: _level(3)
        for key in (
            "goal_progress",
            "conflict_change",
            "state_change",
            "information_gain",
            "character_agency",
            "causal_coherence",
            "curiosity",
            "tension",
            "emotional_investment",
            "pacing_speed",
            "hook",
            "payoff",
            "setup_consistency",
            "question_lifecycle",
            "emotional_valence_start",
            "emotional_valence_end",
            "arousal_start",
            "arousal_end",
            "clarity",
            "cognitive_load",
            "redundancy",
        )
    }
    return SceneReaderJourneyProfileItemV2(
        scene_id=scene_id,
        scene_ordinal=ordinal,
        node_type="scene",
        scene_role="setup",
        scene_value_summary="最小匿名场景推进",
        evidence_paragraph_ids=["P0001"],
        confidence=0.8,
        **fields,
    )


def test_default_new_run_resolves_to_v2():
    versions = resolve_versions_for_new_run()
    assert versions.pipeline_id == "v2"
    assert versions.contract_version == SCENE_CONTRACT_VERSION_V2 == "2.0"
    # v2.2: the reader's question, what the scene answered, and where the first hook lands
    # become model output instead of being manufactured from hook.rationale by the compat
    # shim. The prompt moved; the contract did not, which is why only this line changes.
    assert versions.scene_prompt_version == SCENE_PROMPT_VERSION_V2 == "v2.3"
    assert versions.formula_version == FORMULA_VERSION_V2 == "2.0"
    assert versions.source_mode == SOURCE_MODE_V2_NATIVE
    assert versions.scores_origin == SCORES_ORIGIN_PROGRAM
    assert versions.diagnoses_origin == DIAGNOSES_ORIGIN_PROGRAM


def test_legacy_pipeline_resolver_keeps_v1():
    versions = resolve_versions_for_new_run(pipeline_id="legacy_v1")
    assert versions.pipeline_id == "legacy_v1"
    assert versions.contract_version == "1.3"
    assert versions.scene_prompt_version == "v1.6"
    assert versions.source_mode == "legacy_adapter"


def test_new_journey_version_fields_persist_provenance():
    fields = new_journey_version_fields()
    assert fields["scene_contract_version"] == "2.0"
    assert fields["scene_prompt_version"] == "v2.3"
    assert fields["formula_version"] == "2.0"
    details = json.loads(fields["failure_details_json"])
    assert details["source_mode"] == SOURCE_MODE_V2_NATIVE
    assert details["scores_origin"] == SCORES_ORIGIN_PROGRAM
    assert details["diagnoses_origin"] == DIAGNOSES_ORIGIN_PROGRAM


def test_is_v2_vs_legacy_run_detection():
    v2 = SimpleNamespace(scene_contract_version="2.0", failure_details_json="{}")
    legacy = SimpleNamespace(scene_contract_version="1.3", failure_details_json="{}")
    by_mode = SimpleNamespace(
        scene_contract_version="1.3",
        failure_details_json=json.dumps({"source_mode": SOURCE_MODE_V2_NATIVE}),
    )
    assert is_v2_journey_run(v2) is True
    assert is_legacy_journey_run(legacy) is True
    assert is_v2_journey_run(by_mode) is True


@pytest.mark.asyncio
async def test_execute_reader_journey_dispatches_v2():
    from app.db.models import AnalysisRun, ReaderJourneyRun
    from app.services import reader_journey_pipeline as pipeline

    journey = SimpleNamespace(
        id=7,
        status="queued",
        analysis_run_id=1,
        scene_contract_version="2.0",
        failure_details_json="{}",
        cancellation_requested_at=None,
        raw_output=None,
    )
    analysis_run = SimpleNamespace(
        id=1,
        status="running",
        cancellation_requested_at=None,
        raw_output="{}",
    )

    def _get(model, ident):  # noqa: ANN001
        if model is ReaderJourneyRun or getattr(model, "__name__", "") == "ReaderJourneyRun":
            return journey
        if model is AnalysisRun or getattr(model, "__name__", "") == "AnalysisRun":
            return analysis_run
        return None

    session = MagicMock()
    session.get.side_effect = _get
    session_cm = MagicMock()
    session_cm.__enter__.return_value = session
    session_cm.__exit__.return_value = False
    factory = MagicMock(return_value=session_cm)
    gateway = MagicMock()

    with (
        patch(
            "app.services.reader_journey_v2_execution.execute_reader_journey_v2",
            new_callable=AsyncMock,
        ) as mocked,
        patch(
            "app.services.reader_journey_recovery.claim_journey_worker",
            return_value=journey,
        ),
    ):
        await pipeline.execute_reader_journey(factory, gateway, 7)
        mocked.assert_awaited_once_with(factory, gateway, 7)


@pytest.mark.asyncio
async def test_execute_reader_journey_keeps_legacy_path():
    from app.db.models import AnalysisRun, ReaderJourneyRun
    from app.services import reader_journey_pipeline as pipeline

    journey = SimpleNamespace(
        id=8,
        status="queued",
        analysis_run_id=1,
        scene_contract_version="1.3",
        failure_details_json="{}",
        cancellation_requested_at=None,
        raw_output=None,
    )
    analysis_run = SimpleNamespace(
        id=1,
        status="running",
        cancellation_requested_at=None,
        raw_output="{}",
    )

    def _get(model, ident):  # noqa: ANN001
        if model is ReaderJourneyRun or getattr(model, "__name__", "") == "ReaderJourneyRun":
            return journey
        if model is AnalysisRun or getattr(model, "__name__", "") == "AnalysisRun":
            return analysis_run
        return None

    session = MagicMock()
    session.get.side_effect = _get
    session_cm = MagicMock()
    session_cm.__enter__.return_value = session
    session_cm.__exit__.return_value = False
    factory = MagicMock(return_value=session_cm)
    gateway = MagicMock()

    with (
        patch(
            "app.services.reader_journey_pipeline._execute_reader_journey_legacy",
            new_callable=AsyncMock,
        ) as mocked,
        patch(
            "app.services.reader_journey_recovery.claim_journey_worker",
            return_value=journey,
        ),
    ):
        await pipeline.execute_reader_journey(factory, gateway, 8)
        mocked.assert_awaited_once_with(factory, gateway, 8)


def test_strip_model_mapped_scores_clears_program_owned_fields():
    profile = _minimal_v2_profile()
    dirty = profile.model_copy(
        update={"curiosity": profile.curiosity.model_copy(update={"mapped_score": 99})}
    )
    cleaned = strip_model_mapped_scores(dirty)
    assert cleaned.curiosity.mapped_score is None
    assert cleaned.curiosity.level == 3


def test_levels_to_finalize_and_statistics_provenance():
    raw = [_minimal_v2_profile(1, 10), _minimal_v2_profile(2, 11)]
    derived, stats = finalize_v2_profiles(raw)
    assert len(derived) == 2
    assert all(p.reading_momentum is not None for p in derived)
    assert stats.get("scene_diagnoses") is not None
    deterministic = build_v2_deterministic_statistics(derived=derived, finalize_stats=stats)
    assert deterministic["contract_version"] == "2.0"
    assert deterministic["source_mode"] == SOURCE_MODE_V2_NATIVE
    assert deterministic["scores_origin"] == SCORES_ORIGIN_PROGRAM
    assert deterministic["diagnoses_origin"] == DIAGNOSES_ORIGIN_PROGRAM
    assert deterministic["prewritten_scores"] is False
    assert deterministic["prewritten_diagnoses"] is False


def test_persist_finalized_v2_writes_valid_rows(testing_session):
    from app.db.models import (
        AnalysisRun,
        Book,
        Chapter,
        ChapterReaderJourneySummary,
        Paragraph,
        ReaderJourneyRun,
        Scene,
        SceneReaderJourneyProfile,
    )

    book = Book(title="Anon", source_file_name="anon.txt", source_file_hash="b" * 64)
    testing_session.add(book)
    testing_session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title="最小匿名章节",
        display_title="最小匿名章节",
        word_count=12,
    )
    testing_session.add(chapter)
    testing_session.flush()
    para = Paragraph(
        book_id=book.id,
        chapter_id=chapter.id,
        paragraph_index=0,
        id="P0001",
        raw_text="甲乙丙",
        normalized_text="甲乙丙",
        char_start=0,
        char_end=3,
    )
    testing_session.add(para)
    testing_session.flush()
    run = AnalysisRun(
        subject_type="chapter",
        subject_id=str(chapter.id),
        status="succeeded",
        provider="mock",
        model="mock",
        prompt_version="v1",
        schema_version="1.0",
        input_hash="c" * 64,
    )
    testing_session.add(run)
    testing_session.flush()
    scene = Scene(
        book_id=book.id,
        chapter_id=chapter.id,
        ordinal=1,
        scene_key="s1",
        start_paragraph_id="P0001",
        end_paragraph_id="P0001",
        boundary_source="manual",
        boundary_confidence=1.0,
        content_hash="d" * 64,
        created_by_run_id=run.id,
    )
    testing_session.add(scene)
    testing_session.flush()
    fields = new_journey_version_fields()
    journey = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="scene_profiles_running",
        provider_name="mock",
        model_name="mock",
        scene_prompt_version=fields["scene_prompt_version"],
        chapter_prompt_version=fields["chapter_prompt_version"],
        scene_contract_version=fields["scene_contract_version"],
        chapter_contract_version=fields["chapter_contract_version"],
        formula_version=fields["formula_version"],
        genre=fields["genre"],
        planner_version="1.1",
        total_scene_count=1,
        completed_scene_count=0,
        remaining_scene_count=1,
        completed_scene_ids_json="[]",
        remaining_scene_ids_json=json.dumps([scene.id]),
        failure_details_json=fields["failure_details_json"],
        cloud_consent=True,
        client_request_id="anon-min-v2",
    )
    testing_session.add(journey)
    testing_session.flush()

    profile = _minimal_v2_profile(1, scene.id)
    derived, stats = finalize_v2_profiles([profile])
    deterministic = persist_finalized_v2_profiles(
        testing_session,
        journey_run=journey,
        derived=derived,
        finalize_stats=stats,
        paragraph_ids_by_scene={int(scene.id): ["P0001"]},
    )
    testing_session.commit()

    rows = list(
        testing_session.query(SceneReaderJourneyProfile).filter_by(
            reader_journey_run_id=journey.id
        )
    )
    summary = (
        testing_session.query(ChapterReaderJourneySummary)
        .filter_by(reader_journey_run_id=journey.id)
        .one()
    )
    assert len(rows) == 1
    assert rows[0].validation_status == "valid"
    assert journey.scene_contract_version == "2.0"
    stored = json.loads(summary.deterministic_statistics_json)
    assert stored["source_mode"] == SOURCE_MODE_V2_NATIVE
    assert stored["prewritten_scores"] is False
    assert stored["prewritten_diagnoses"] is False
    assert deterministic["scores_origin"] == SCORES_ORIGIN_PROGRAM


def test_harness_script_calls_official_service_only():
    path = Path("scripts/execute_reader_journey_v2_native_niujiaokao.py")
    text = path.read_text(encoding="utf-8")
    assert "execute_reader_journey_v2" in text
    assert "from app.services.reader_journey_v2_execution import execute_reader_journey_v2" in text
    tree = ast.parse(text)
    fn_names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert "finalize_v2_profiles" not in fn_names
    assert "_v1_compat_payload" not in fn_names


def test_config_default_pipeline_is_v2():
    cfg = json.loads(Path("config/reader_journey_pipeline_version.json").read_text(encoding="utf-8"))
    assert cfg["default_pipeline"] == "v2"
    assert cfg["pipelines"]["v2"]["contract_version"] == "2.0"
    assert cfg["pipelines"]["legacy_v1"]["contract_version"] == "1.3"


def test_preflight_schema_accepts_pipeline_fields():
    from app.schemas.reader_journey import ReaderJourneyPreflightResponse

    payload = {
        "analysis_run_id": 1,
        "total_scenes": 1,
        "remaining_scenes": 1,
        "scene_batch_count": 1,
        "expected_requests": 1,
        "worst_case_requests": 2,
        "estimated_tokens": 100,
        "worst_case_tokens": 200,
        "estimated_cost": 0.01,
        "worst_case_cost": 0.02,
        "within_budget": True,
        "exceeded_dimensions": [],
        "pricing_version": "1",
        "provider_state_version": "1",
        "provider_name": "mock",
        "eligible": True,
        "blockers": [],
        "requires_cloud_consent": False,
        "currency": "CNY",
        "estimated": True,
        "stage1_scene_profiles": {},
        "stage2_chapter_synthesis": {},
        "pipeline_id": "v2",
        "source_mode": SOURCE_MODE_V2_NATIVE,
        "scene_prompt_version": "v2.0",
        "scene_contract_version": "2.0",
    }
    model = ReaderJourneyPreflightResponse.model_validate(payload)
    assert model.pipeline_id == "v2"
