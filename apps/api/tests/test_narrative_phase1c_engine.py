"""Phase 1C Agent G: WholeBook Engine Registry / Mock / Stage Orchestrator tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Book, Chapter, NarrativeAssetVersion, Paragraph
from app.narrative_core.capability_registry import get_capability_metadata
from app.narrative_core.contracts.capability import CapabilityDecision
from app.narrative_core.contracts.stage import WholeBookStageDefinition
from app.narrative_core.contracts.whole_book_dto import WholeBookAnalysisRequest
from app.narrative_core.enums import (
    AnalysisScopeType,
    AnalysisType,
    CapabilityAvailability,
    CapabilityKey,
    CapabilityReasonCode,
    CostClass,
    OriginType,
    ReviewStatus,
    SnapshotStatus,
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
    WholeBookStageKey,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.migrations.runner import (
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)
from app.narrative_core.services.mock_whole_book_engine import (
    MOCK_ENGINE_ID,
    MockWholeBookAnalysisEngine,
)
from app.narrative_core.services.run_stage_service import RunStageService
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_engine_adapters import (
    AnalysisConflictSinkAdapter,
    ArtifactWriterAdapter,
    BudgetGuardAdapter,
    CancellationTokenImpl,
    MOCK_SOURCE_MARKER,
    NarrativeAssetWriterAdapter,
    NarrativeRelationWriterAdapter,
    RunBindingResolver,
    SnapshotReaderAdapter,
)
from app.narrative_core.services.whole_book_engine_registry import (
    DefaultWholeBookEngineFactory,
    InMemoryWholeBookEngineRegistry,
    PRODUCTION_DEFAULT_ENGINE_ID,
)
from app.narrative_core.services.whole_book_stage_orchestrator import WholeBookStageOrchestrator
from app.narrative_core.services.whole_book_stage_plan import (
    build_whole_book_stage_plan,
    detect_dependency_cycle,
)
from app.narrative_core.whole_book_stages import ORDERED_STAGE_KEYS, WHOLE_BOOK_STAGE_CATALOG

REPO_ROOT = Path(__file__).resolve().parents[3]


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _allowed_capability() -> CapabilityDecision:
    meta = get_capability_metadata(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    return CapabilityDecision(
        capability_key=CapabilityKey.WHOLE_BOOK_ANALYSIS,
        allowed=True,
        reason_code=CapabilityReasonCode.CAPABILITY_AVAILABLE,
        availability=CapabilityAvailability.AVAILABLE,
        display_message="test override allowed",
        metadata=meta,
    )


def _denied_capability() -> CapabilityDecision:
    meta = get_capability_metadata(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    return CapabilityDecision(
        capability_key=CapabilityKey.WHOLE_BOOK_ANALYSIS,
        allowed=False,
        reason_code=CapabilityReasonCode.CAPABILITY_NOT_SHIPPED,
        availability=CapabilityAvailability.UNAVAILABLE,
        display_message="not shipped",
        metadata=meta,
    )


def _seed_book(session: Session) -> Book:
    book = Book(
        title="Mock Engine Book",
        source_file_name="mock.txt",
        source_file_hash="m" * 64,
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title="第一章",
        display_title="第一章",
        chapter_title="第一章",
        source_title_line="第一章",
        word_count=4,
    )
    session.add(chapter)
    session.flush()
    session.add(
        Paragraph(
            id=f"B{book.id:04d}-C0001-P0001",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=1,
            raw_text="合成样本",
            normalized_text="合成样本",
            char_start=0,
            char_end=4,
        )
    )
    session.commit()
    return book


@pytest.fixture
def engine_env(tmp_path):
    db = _fk_engine(f"sqlite:///{tmp_path / 'phase1c-engine.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    session = factory()
    book = _seed_book(session)
    snapshot = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    assert snapshot.snapshot_status == SnapshotStatus.COMPLETED.value

    stage_service = RunStageService(session)
    run = stage_service.create_scoped_run(
        scope_type=AnalysisScopeType.BOOK,
        analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
        book_id=book.id,
        book_snapshot_id=snapshot.id,
        configuration_fingerprint="cfg-mock-1",
        provider="local",
        model="mock",
    )
    session.commit()

    snapshot_reader = SnapshotReaderAdapter(session)
    binding = RunBindingResolver(session)
    asset_writer = NarrativeAssetWriterAdapter(session)
    relation_writer = NarrativeRelationWriterAdapter(session)
    artifact_writer = ArtifactWriterAdapter(session)
    conflict_sink = AnalysisConflictSinkAdapter(session)
    budget = BudgetGuardAdapter()
    cancel = CancellationTokenImpl()

    mock = MockWholeBookAnalysisEngine(
        snapshot_reader=snapshot_reader,
        binding_resolver=binding,
    )
    orch = WholeBookStageOrchestrator(
        engine=mock,
        run_stage_service=stage_service,
        snapshot_reader=snapshot_reader,
        asset_writer=asset_writer,
        relation_writer=relation_writer,
        artifact_writer=artifact_writer,
        conflict_sink=conflict_sink,
        budget_guard=budget,
        cancellation_token=cancel,
    )
    yield {
        "session": session,
        "book": book,
        "snapshot": snapshot,
        "run": run,
        "stage_service": stage_service,
        "mock": mock,
        "orch": orch,
        "asset_writer": asset_writer,
        "relation_writer": relation_writer,
        "artifact_writer": artifact_writer,
        "conflict_sink": conflict_sink,
        "budget": budget,
        "cancel": cancel,
        "snapshot_reader": snapshot_reader,
        "binding": binding,
        "db": db,
    }
    session.close()
    db.dispose()


def _request(env, **overrides) -> WholeBookAnalysisRequest:
    base = {
        "run_id": env["run"].id,
        "book_id": env["book"].id,
        "book_snapshot_id": env["snapshot"].id,
        "analysis_mode": WholeBookAnalysisMode.NATIVE,
        "capability_context": _allowed_capability(),
        "configuration_fingerprint": "cfg-mock-1",
        "snapshot_status": SnapshotStatus.COMPLETED,
        "extra": {
            "bound_book_id": env["book"].id,
            "bound_snapshot_id": env["snapshot"].id,
        },
    }
    base.update(overrides)
    return WholeBookAnalysisRequest(**base)  # type: ignore[arg-type]


# ----- Registry / Factory -----


def test_registry_register_and_list() -> None:
    registry = InMemoryWholeBookEngineRegistry()
    engine = MockWholeBookAnalysisEngine()
    registry.register(engine)
    assert registry.list_engines() == (MOCK_ENGINE_ID,)
    assert registry.get(MOCK_ENGINE_ID) is engine
    assert PRODUCTION_DEFAULT_ENGINE_ID is None


def test_registry_duplicate_engine_id_fails() -> None:
    registry = InMemoryWholeBookEngineRegistry()
    a = MockWholeBookAnalysisEngine()
    b = MockWholeBookAnalysisEngine()
    registry.register(a)
    registry.register(a)  # idempotent same instance
    with pytest.raises(NarrativeCoreError) as exc:
        registry.register(b)
    assert "duplicate" in str(exc.value).lower() or exc.value.code == (
        NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID
    )


def test_registry_engine_not_found() -> None:
    registry = InMemoryWholeBookEngineRegistry()
    with pytest.raises(NarrativeCoreError) as exc:
        registry.get("missing_engine")
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_ENGINE_NOT_FOUND


def test_resolve_for_mode_native_enhanced() -> None:
    registry = InMemoryWholeBookEngineRegistry()
    registry.register(MockWholeBookAnalysisEngine())
    assert registry.resolve_for_mode(WholeBookAnalysisMode.NATIVE).engine_id == MOCK_ENGINE_ID
    assert registry.resolve_for_mode(WholeBookAnalysisMode.ENHANCED).engine_id == MOCK_ENGINE_ID


def test_factory_creates_mock_not_in_production() -> None:
    factory = DefaultWholeBookEngineFactory(allow_mock=True, production_mode=False)
    engine = factory.create_engine(MOCK_ENGINE_ID)
    assert engine.engine_id == MOCK_ENGINE_ID
    prod = DefaultWholeBookEngineFactory(production_mode=True)
    with pytest.raises(NarrativeCoreError) as exc:
        prod.create_engine(MOCK_ENGINE_ID)
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_ENGINE_UNAVAILABLE


# ----- Modes / request validation -----


def test_native_and_enhanced_supported(engine_env) -> None:
    mock: MockWholeBookAnalysisEngine = engine_env["mock"]
    for mode in (WholeBookAnalysisMode.NATIVE, WholeBookAnalysisMode.ENHANCED):
        req = _request(engine_env, analysis_mode=mode)
        plan = mock.build_stage_plan(req)
        assert plan.mode == mode


def test_unsupported_mode(engine_env) -> None:
    mock: MockWholeBookAnalysisEngine = engine_env["mock"]
    req = _request(engine_env)
    # Bypass enum by monkeypatching analysis_mode after construction is not possible
    # on frozen dataclass; call validate path via a thin subclass check.
    object.__setattr__(req, "analysis_mode", "whole_book_unknown")  # type: ignore[misc]
    with pytest.raises(NarrativeCoreError) as exc:
        mock.validate_request(req)
    assert exc.value.code in {
        NarrativeCoreErrorCode.WHOLE_BOOK_MODE_NOT_SUPPORTED,
        NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
    }


def test_request_requires_snapshot_completed(engine_env) -> None:
    mock: MockWholeBookAnalysisEngine = engine_env["mock"]
    with pytest.raises(NarrativeCoreError) as exc:
        mock.validate_request(
            _request(engine_env, snapshot_status=SnapshotStatus.BUILDING)
        )
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_SNAPSHOT_REQUIRED


def test_request_run_snapshot_mismatch(engine_env) -> None:
    mock: MockWholeBookAnalysisEngine = engine_env["mock"]
    with pytest.raises(NarrativeCoreError) as exc:
        mock.validate_request(
            _request(
                engine_env,
                book_snapshot_id=engine_env["snapshot"].id + 999,
                extra={
                    "bound_book_id": engine_env["book"].id,
                    "bound_snapshot_id": engine_env["snapshot"].id,
                },
            )
        )
    assert exc.value.code in {
        NarrativeCoreErrorCode.WHOLE_BOOK_RUN_SNAPSHOT_MISMATCH,
        NarrativeCoreErrorCode.SNAPSHOT_NOT_FOUND,
        NarrativeCoreErrorCode.WHOLE_BOOK_SNAPSHOT_REQUIRED,
    }


def test_capability_denied(engine_env) -> None:
    mock: MockWholeBookAnalysisEngine = engine_env["mock"]
    with pytest.raises(NarrativeCoreError) as exc:
        mock.validate_request(
            _request(engine_env, capability_context=_denied_capability())
        )
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED


def test_requested_module_unsupported(engine_env) -> None:
    mock: MockWholeBookAnalysisEngine = engine_env["mock"]
    with pytest.raises(NarrativeCoreError) as exc:
        mock.validate_request(
            _request(engine_env, requested_modules=("not_a_real_module",))
        )
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_MODULE_NOT_SUPPORTED


def test_request_rejects_full_body(engine_env) -> None:
    mock: MockWholeBookAnalysisEngine = engine_env["mock"]
    with pytest.raises(NarrativeCoreError) as exc:
        mock.validate_request(
            _request(engine_env, extra={"full_text": "整本小说正文"})
        )
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID


def test_enhanced_missing_chapter_assets_degrades(engine_env) -> None:
    mock: MockWholeBookAnalysisEngine = engine_env["mock"]
    req = _request(
        engine_env,
        analysis_mode=WholeBookAnalysisMode.ENHANCED,
        extra={
            "bound_book_id": engine_env["book"].id,
            "bound_snapshot_id": engine_env["snapshot"].id,
            "has_chapter_analysis_assets": False,
        },
    )
    mock.validate_request(req)
    assert req.extra.get("enhanced_degraded") is True


# ----- Stage plan -----


def test_stage_plan_stable_order() -> None:
    plan_a = build_whole_book_stage_plan(mode=WholeBookAnalysisMode.NATIVE)
    plan_b = build_whole_book_stage_plan(mode=WholeBookAnalysisMode.NATIVE)
    keys_a = [s.stage_key for s in plan_a.stages]
    keys_b = [s.stage_key for s in plan_b.stages]
    assert keys_a == keys_b == list(ORDERED_STAGE_KEYS)


def test_stage_plan_dependency_autocomplete() -> None:
    plan = build_whole_book_stage_plan(
        mode=WholeBookAnalysisMode.NATIVE,
        requested_modules=(WholeBookModuleKey.DIAGNOSTICS,),
    )
    keys = {s.stage_key for s in plan.stages}
    assert WholeBookStageKey.GENERATE_DIAGNOSTICS in keys
    assert WholeBookStageKey.ANALYZE_CAUSALITY_TIMELINE in keys
    assert WholeBookStageKey.BUILD_FULLTEXT_INDEX in keys
    assert WholeBookStageKey.PERSIST_NARRATIVE_ASSETS in keys


def test_stage_plan_cycle_detection() -> None:
    cyclic = (
        WholeBookStageDefinition(
            stage_key=WholeBookStageKey.ANALYZE_STRUCTURE,
            display_name="A",
            order=1,
            depends_on=(WholeBookStageKey.ANALYZE_STORYLINES,),
            estimated_cost_class=CostClass.LOW,
        ),
        WholeBookStageDefinition(
            stage_key=WholeBookStageKey.ANALYZE_STORYLINES,
            display_name="B",
            order=2,
            depends_on=(WholeBookStageKey.ANALYZE_STRUCTURE,),
            estimated_cost_class=CostClass.LOW,
        ),
    )
    cycle = detect_dependency_cycle(cyclic)
    assert cycle


# ----- Orchestrator lifecycle -----


def test_initialize_run_stages(engine_env) -> None:
    orch: WholeBookStageOrchestrator = engine_env["orch"]
    rows = orch.initialize_stages(_request(engine_env))
    assert [r.stage_key for r in rows] == [k.value for k in ORDERED_STAGE_KEYS]


def test_stage_execute_checkpoint_token_cost(engine_env) -> None:
    orch: WholeBookStageOrchestrator = engine_env["orch"]
    req = _request(engine_env)
    orch.initialize_stages(req)
    result = orch.execute_current_stage(req, WholeBookStageKey.BUILD_FULLTEXT_INDEX.value)
    assert result.status == StageStatus.COMPLETED
    assert result.stage_key == WholeBookStageKey.BUILD_FULLTEXT_INDEX
    assert result.token_usage > 0
    assert "schema" in result.checkpoint and "version" in result.checkpoint
    row = engine_env["stage_service"]._stages.get_stage(  # noqa: SLF001
        req.run_id, WholeBookStageKey.BUILD_FULLTEXT_INDEX.value
    )
    assert StageStatus(row.status) == StageStatus.COMPLETED
    assert row.token_input >= result.token_usage
    checkpoint = json.loads(row.checkpoint_json)
    assert checkpoint.get("schema")
    assert checkpoint.get("version")
    assert checkpoint.get("mock") is True


def test_pause_resume(engine_env) -> None:
    orch: WholeBookStageOrchestrator = engine_env["orch"]
    req = _request(engine_env)
    orch.initialize_stages(req)
    key = WholeBookStageKey.RESOLVE_ENTITIES.value
    engine_env["stage_service"].transition_stage(req.run_id, key, StageStatus.RUNNING)
    run = orch.pause(req, key)
    assert run.status == "paused"
    row = engine_env["stage_service"]._stages.get_stage(req.run_id, key)  # noqa: SLF001
    assert StageStatus(row.status) == StageStatus.PAUSED
    assert StageStatus(row.status) != StageStatus.FAILED
    result = orch.resume(req, key)
    assert result.status == StageStatus.COMPLETED


def test_interrupted_retry(engine_env) -> None:
    orch: WholeBookStageOrchestrator = engine_env["orch"]
    req = _request(engine_env)
    orch.initialize_stages(req)
    key = WholeBookStageKey.ANALYZE_STRUCTURE.value
    engine_env["stage_service"].transition_stage(req.run_id, key, StageStatus.RUNNING)
    orch.interrupt(req)
    row = engine_env["stage_service"]._stages.get_stage(req.run_id, key)  # noqa: SLF001
    assert StageStatus(row.status) == StageStatus.INTERRUPTED
    # resume_stage path via orchestrator resume
    result = orch.resume(req, key)
    assert result.status == StageStatus.COMPLETED

    # failed → retry
    key2 = WholeBookStageKey.ANALYZE_STORYLINES.value
    engine_env["stage_service"].transition_stage(req.run_id, key2, StageStatus.RUNNING)
    engine_env["stage_service"].transition_stage(
        req.run_id,
        key2,
        StageStatus.FAILED,
        error_code="MOCK_FAIL",
        error_message="forced",
    )
    retried = orch.retry(req, key2)
    assert retried.status == StageStatus.COMPLETED


def test_cancel_stops_execution(engine_env) -> None:
    orch: WholeBookStageOrchestrator = engine_env["orch"]
    req = _request(engine_env)
    orch.initialize_stages(req)
    key = WholeBookStageKey.ANALYZE_CHARACTERS.value
    orch.cancel(req, key)
    with pytest.raises(NarrativeCoreError) as exc:
        orch.execute_current_stage(req, WholeBookStageKey.ANALYZE_HOOKS.value)
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_STAGE_CANCELLED


def test_completed_stage_not_rerun(engine_env) -> None:
    orch: WholeBookStageOrchestrator = engine_env["orch"]
    req = _request(engine_env)
    orch.initialize_stages(req)
    key = WholeBookStageKey.BUILD_FULLTEXT_INDEX.value
    first = orch.execute_current_stage(req, key)
    second = orch.execute_current_stage(req, key)
    assert first.status == StageStatus.COMPLETED
    assert second.metrics.get("skipped_rerun") is True


def test_budget_guard_denies_without_asset_write(engine_env) -> None:
    orch: WholeBookStageOrchestrator = engine_env["orch"]
    budget: BudgetGuardAdapter = engine_env["budget"]
    budget.deny()
    req = _request(engine_env, extra={**_request(engine_env).extra, "emit_mock_conflict": True})
    orch.initialize_stages(req)
    before = len(engine_env["asset_writer"].created_version_ids)
    with pytest.raises(NarrativeCoreError) as exc:
        orch.execute_current_stage(req, WholeBookStageKey.PERSIST_NARRATIVE_ASSETS.value)
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_BUDGET_DENIED
    assert len(engine_env["asset_writer"].created_version_ids) == before


def test_mock_candidate_asset_relation_not_canonical(engine_env) -> None:
    orch: WholeBookStageOrchestrator = engine_env["orch"]
    req = _request(
        engine_env,
        extra={
            "bound_book_id": engine_env["book"].id,
            "bound_snapshot_id": engine_env["snapshot"].id,
            "emit_mock_conflict": True,
        },
    )
    orch.initialize_stages(req)
    # Run prior stages without writers side effects, then persist.
    for key in ORDERED_STAGE_KEYS:
        if key == WholeBookStageKey.PERSIST_NARRATIVE_ASSETS:
            break
        orch.execute_current_stage(req, key.value)
    result = orch.execute_current_stage(req, WholeBookStageKey.PERSIST_NARRATIVE_ASSETS.value)
    assert result.status == StageStatus.COMPLETED
    assert len(result.created_asset_version_ids) >= 3
    assert len(result.created_relation_version_ids) >= 1
    assert len(result.conflict_ids) >= 1

    session: Session = engine_env["session"]
    versions = session.scalars(select(NarrativeAssetVersion)).all()
    assert versions
    for version in versions:
        assert version.is_canonical is False
        assert version.review_status == ReviewStatus.CANDIDATE.value
        assert version.origin_type == OriginType.SYSTEM.value
        assert MOCK_SOURCE_MARKER in (version.source_fingerprint or "")


def test_health_check_fields() -> None:
    health = MockWholeBookAnalysisEngine().health_check()
    for key in (
        "engine_id",
        "engine_version",
        "available",
        "supported_modes",
        "supported_modules",
        "mock",
        "detail",
        "checked_at",
    ):
        assert key in health
    assert health["available"] is True
    assert health["mock"] is True
    assert health["production_ready"] is False


def test_registry_health_check_all() -> None:
    registry = InMemoryWholeBookEngineRegistry()
    registry.register(MockWholeBookAnalysisEngine())
    results = registry.health_check_all()
    assert len(results) == 1
    assert results[0]["engine_id"] == MOCK_ENGINE_ID


def test_phase1cp_contract_compat_health_healthy() -> None:
    """Phase 1C-P contract tests expect health['healthy']."""
    health = MockWholeBookAnalysisEngine().health_check()
    assert health["healthy"] is True


# ----- Gates -----


def test_version_manager_check() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "version_manager.py"), "check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_change_registry_check() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "change_registry.py"), "check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_git_diff_check() -> None:
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
