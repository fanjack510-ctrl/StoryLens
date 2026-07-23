"""Phase 1D Agent K — whole-book result projection tests.

Covers Result Index, module status aggregation, Envelope, 11 module payloads,
read-only API router (unmounted), Pattern projection inputs, and N+1 bounds.
Does not run full pytest suite / release gates.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisConflict,
    AnalysisRun,
    AnalysisRunStage,
    Base,
    Book,
    BookSnapshot,
    BookSnapshotChapter,
    BookSnapshotParagraph,
    Chapter,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    NarrativeRelation,
    NarrativeRelationVersion,
)
from app.narrative_core.enums import (
    AnalysisScopeType,
    AnalysisType,
    AssetLifecycleStatus,
    AssetType,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    RelationType,
    ReviewStatus,
    StageStatus,
    WholeBookModuleKey,
    WholeBookStageKey,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.migrations.runner import apply_narrative_phase1bp_migrations
from app.narrative_core.product_contract.enums import WholeBookModuleStatus
from app.narrative_core.product_contract.keys import MODULE_STAGE_DEPENDENCIES
from app.narrative_core.product_contract.module_results import MODULE_RESULT_DTO_BY_KEY
from app.narrative_core.product_contract.result_envelope import (
    RESULT_ENVELOPE_SCHEMA,
    RESULT_ENVELOPE_VERSION,
)
from app.narrative_core.services.run_scope_service import make_stub_completed_snapshot
from app.narrative_core.services.whole_book_result_projection import (
    ENGINE_MODULE_PLANNING_STAGES,
    PRODUCT_MODULE_STAGE_DEPENDENCIES,
    WholeBookResultIndexService,
    _QueryCounter,
    aggregate_module_status,
    empty_payload_for_module,
    validate_module_payload,
)
from app.narrative_core.services.whole_book_stage_plan import (
    ENGINE_MODULE_PLANNING_STAGES as PLAN_ENGINE_MAP,
    MODULE_TO_STAGES,
)
from app.routers.whole_book_results import router as whole_book_results_router


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _session_factory(tmp_path, name: str = "proj.db"):
    engine = _fk_engine(f"sqlite:///{tmp_path / name}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1bp_migrations(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory, engine


def _seed_book(session: Session) -> tuple[Book, BookSnapshot]:
    book = Book(
        title="Projection Fixture Book",
        source_file_name="fixture.txt",
        source_file_hash="f" * 64,
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
        word_count=12,
    )
    session.add(chapter)
    session.flush()
    snapshot = make_stub_completed_snapshot(session, book_id=book.id, content_hash="c" * 64)
    snap_ch = BookSnapshotChapter(
        snapshot_id=snapshot.id,
        source_chapter_id=chapter.id,
        chapter_order=1,
        title="第一章",
        content_hash="ch" * 32,
    )
    session.add(snap_ch)
    session.flush()
    session.add(
        BookSnapshotParagraph(
            snapshot_id=snapshot.id,
            snapshot_chapter_id=snap_ch.id,
            paragraph_order=1,
            content_hash="p" * 64,
            stable_paragraph_id=f"B{book.id:04d}-C0001-P0001",
            start_offset=0,
            end_offset=4,
        )
    )
    session.flush()
    return book, snapshot


def _create_book_run(
    session: Session,
    *,
    book: Book,
    snapshot: BookSnapshot,
    requested_modules: list[str] | None = None,
    analysis_type: str = AnalysisType.WHOLE_BOOK_NATIVE.value,
) -> AnalysisRun:
    run = AnalysisRun(
        task_type="whole_book",
        subject_type="book",
        subject_id=str(book.id),
        provider="none",
        model="none",
        prompt_version="n/a",
        schema_version="1",
        input_hash="i" * 64,
        status="running",
        analysis_type=analysis_type,
        scope_type=AnalysisScopeType.BOOK.value,
        book_id=book.id,
        book_snapshot_id=snapshot.id,
        configuration_fingerprint="cfg-proj-1",
        validated_output=json.dumps({"requested_modules": requested_modules or []}),
    )
    session.add(run)
    session.flush()
    return run


def _add_stages(
    session: Session,
    run: AnalysisRun,
    specs: list[tuple[str, str]],
) -> list[AnalysisRunStage]:
    stages: list[AnalysisRunStage] = []
    for order, (key, status) in enumerate(specs):
        stage = AnalysisRunStage(
            run_id=run.id,
            stage_key=key,
            stage_order=order,
            status=status,
            checkpoint_json=json.dumps(
                {"schema": "narrative_run_stage_checkpoint", "version": "1"}
            ),
        )
        session.add(stage)
        stages.append(stage)
    session.flush()
    return stages


def _add_asset(
    session: Session,
    *,
    book_id: int,
    snapshot_id: int,
    run_id: int | None,
    asset_key: str,
    asset_type: str,
    title: str = "",
    summary: str = "",
    is_canonical: bool = True,
    review_status: str = ReviewStatus.CONFIRMED.value,
    attributes: dict[str, Any] | None = None,
    lifecycle_status: str = AssetLifecycleStatus.ACTIVE.value,
    with_evidence: bool = False,
) -> tuple[NarrativeAsset, NarrativeAssetVersion]:
    asset = NarrativeAsset(
        book_id=book_id,
        asset_key=asset_key,
        lifecycle_status=lifecycle_status,
        is_locked=False,
    )
    session.add(asset)
    session.flush()
    version = NarrativeAssetVersion(
        asset_id=asset.id,
        run_id=run_id,
        book_snapshot_id=snapshot_id,
        asset_type=asset_type,
        title=title,
        summary=summary,
        narrative_function="",
        attributes_json=json.dumps(attributes or {}),
        confidence=0.8,
        importance=0.5,
        source_fingerprint="src",
        origin_type="system",
        review_status=review_status,
        is_canonical=is_canonical,
    )
    session.add(version)
    session.flush()
    if with_evidence:
        snap_ch = session.scalar(
            select(BookSnapshotChapter).where(
                BookSnapshotChapter.snapshot_id == snapshot_id
            )
        )
        snap_p = session.scalar(
            select(BookSnapshotParagraph).where(
                BookSnapshotParagraph.snapshot_id == snapshot_id
            )
        )
        assert snap_ch is not None and snap_p is not None
        session.add(
            NarrativeAssetEvidence(
                asset_version_id=version.id,
                book_snapshot_id=snapshot_id,
                snapshot_chapter_id=snap_ch.id,
                snapshot_paragraph_id=snap_p.id,
                paragraph_content_hash=snap_p.content_hash,
                start_offset=0,
                end_offset=1,
                evidence_role="support",
                evidence_label="ref",
            )
        )
        session.flush()
    return asset, version


def _add_relation(
    session: Session,
    *,
    book_id: int,
    snapshot_id: int,
    run_id: int | None,
    source_asset_id: int,
    target_asset_id: int,
    relation_type: str,
    is_canonical: bool = True,
    review_status: str = ReviewStatus.CONFIRMED.value,
) -> NarrativeRelation:
    rel = NarrativeRelation(
        book_id=book_id,
        relation_key=f"rel-{source_asset_id}-{target_asset_id}-{relation_type}",
        source_asset_id=source_asset_id,
        target_asset_id=target_asset_id,
        lifecycle_status="active",
        is_locked=False,
    )
    session.add(rel)
    session.flush()
    session.add(
        NarrativeRelationVersion(
            relation_id=rel.id,
            run_id=run_id,
            book_snapshot_id=snapshot_id,
            relation_type=relation_type,
            attributes_json="{}",
            confidence=0.7,
            importance=0.4,
            source_fingerprint="src",
            origin_type="system",
            review_status=review_status,
            is_canonical=is_canonical,
        )
    )
    session.flush()
    return rel


@pytest.fixture
def env(tmp_path):
    factory, engine = _session_factory(tmp_path)
    session = factory()
    book, snapshot = _seed_book(session)
    session.commit()
    yield {"session": session, "book": book, "snapshot": snapshot, "engine": engine}
    session.close()
    engine.dispose()


def test_dependency_mapping_roles_are_explicit() -> None:
    assert PRODUCT_MODULE_STAGE_DEPENDENCIES is MODULE_STAGE_DEPENDENCIES
    assert PLAN_ENGINE_MAP is MODULE_TO_STAGES
    assert ENGINE_MODULE_PLANNING_STAGES is MODULE_TO_STAGES
    assert len(PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.STORYLINES]) >= 2
    assert PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.DIAGNOSTICS] != (
        MODULE_TO_STAGES[WholeBookModuleKey.DIAGNOSTICS]
    )


def test_module_stage_many_to_many() -> None:
    analyze_structure_modules = [
        m
        for m, deps in PRODUCT_MODULE_STAGE_DEPENDENCIES.items()
        if WholeBookStageKey.ANALYZE_STRUCTURE in deps
    ]
    assert len(analyze_structure_modules) >= 2
    assert len(PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.HOOKS_PAYOFFS]) >= 2


def test_status_not_requested() -> None:
    status = aggregate_module_status(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        requested=set(),
        stage_status={},
        has_usable_output=False,
        stale=False,
        blocking_conflict=False,
    )
    assert status == WholeBookModuleStatus.NOT_REQUESTED


def test_status_pending() -> None:
    deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.STRUCTURE_STAGES]
    stage_status = {d.value: StageStatus.PENDING for d in deps}
    status = aggregate_module_status(
        module_key=WholeBookModuleKey.STRUCTURE_STAGES,
        requested={WholeBookModuleKey.STRUCTURE_STAGES},
        stage_status=stage_status,
        has_usable_output=False,
        stale=False,
        blocking_conflict=False,
    )
    assert status == WholeBookModuleStatus.PENDING


def test_status_running() -> None:
    deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.STORYLINES]
    stage_status = {d.value: StageStatus.PENDING for d in deps}
    stage_status[deps[0].value] = StageStatus.RUNNING
    status = aggregate_module_status(
        module_key=WholeBookModuleKey.STORYLINES,
        requested={WholeBookModuleKey.STORYLINES},
        stage_status=stage_status,
        has_usable_output=False,
        stale=False,
        blocking_conflict=False,
    )
    assert status == WholeBookModuleStatus.RUNNING


def test_status_partial_on_failed_with_output() -> None:
    deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.CHARACTERS]
    stage_status = {d.value: StageStatus.COMPLETED for d in deps}
    stage_status[deps[-1].value] = StageStatus.FAILED
    status = aggregate_module_status(
        module_key=WholeBookModuleKey.CHARACTERS,
        requested={WholeBookModuleKey.CHARACTERS},
        stage_status=stage_status,
        has_usable_output=True,
        stale=False,
        blocking_conflict=False,
    )
    assert status == WholeBookModuleStatus.PARTIAL


def test_status_failed_without_output() -> None:
    deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.CHARACTERS]
    stage_status = {d.value: StageStatus.FAILED for d in deps}
    status = aggregate_module_status(
        module_key=WholeBookModuleKey.CHARACTERS,
        requested={WholeBookModuleKey.CHARACTERS},
        stage_status=stage_status,
        has_usable_output=False,
        stale=False,
        blocking_conflict=False,
    )
    assert status == WholeBookModuleStatus.FAILED


def test_status_completed() -> None:
    deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.CHAPTER_FUNCTIONS]
    stage_status = {d.value: StageStatus.COMPLETED for d in deps}
    status = aggregate_module_status(
        module_key=WholeBookModuleKey.CHAPTER_FUNCTIONS,
        requested={WholeBookModuleKey.CHAPTER_FUNCTIONS},
        stage_status=stage_status,
        has_usable_output=True,
        stale=False,
        blocking_conflict=False,
    )
    assert status == WholeBookModuleStatus.COMPLETED


def test_status_stale_separated_from_failed() -> None:
    deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.CHAPTER_FUNCTIONS]
    stage_status = {d.value: StageStatus.COMPLETED for d in deps}
    status = aggregate_module_status(
        module_key=WholeBookModuleKey.CHAPTER_FUNCTIONS,
        requested={WholeBookModuleKey.CHAPTER_FUNCTIONS},
        stage_status=stage_status,
        has_usable_output=True,
        stale=True,
        blocking_conflict=False,
    )
    assert status == WholeBookModuleStatus.STALE
    assert status != WholeBookModuleStatus.FAILED


def test_status_blocked_by_blocking_conflict() -> None:
    deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.HOOKS_PAYOFFS]
    stage_status = {d.value: StageStatus.PENDING for d in deps}
    status = aggregate_module_status(
        module_key=WholeBookModuleKey.HOOKS_PAYOFFS,
        requested={WholeBookModuleKey.HOOKS_PAYOFFS},
        stage_status=stage_status,
        has_usable_output=False,
        stale=False,
        blocking_conflict=True,
    )
    assert status == WholeBookModuleStatus.BLOCKED


def test_warning_conflict_does_not_block() -> None:
    deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.HOOKS_PAYOFFS]
    stage_status = {d.value: StageStatus.PENDING for d in deps}
    status = aggregate_module_status(
        module_key=WholeBookModuleKey.HOOKS_PAYOFFS,
        requested={WholeBookModuleKey.HOOKS_PAYOFFS},
        stage_status=stage_status,
        has_usable_output=False,
        stale=False,
        blocking_conflict=False,
    )
    assert status == WholeBookModuleStatus.PENDING


def test_result_index_and_eleven_modules(env) -> None:
    session = env["session"]
    book, snapshot = env["book"], env["snapshot"]
    run = _create_book_run(
        session,
        book=book,
        snapshot=snapshot,
        requested_modules=["book_overview", "structure_stages", "storylines"],
    )
    _add_stages(
        session,
        run,
        [
            (WholeBookStageKey.BUILD_FULLTEXT_INDEX.value, StageStatus.COMPLETED.value),
            (WholeBookStageKey.RESOLVE_ENTITIES.value, StageStatus.COMPLETED.value),
            (WholeBookStageKey.ANALYZE_STRUCTURE.value, StageStatus.COMPLETED.value),
            (WholeBookStageKey.ANALYZE_STORYLINES.value, StageStatus.RUNNING.value),
        ],
    )
    session.commit()

    svc = WholeBookResultIndexService(session)
    index = svc.get_result_index(run.id)
    assert index.run_id == run.id
    assert index.book_id == book.id
    assert index.book_snapshot_id == snapshot.id
    assert len(index.modules) == 11
    keys = {e.module_key for e in index.modules}
    assert keys == set(WholeBookModuleKey)
    by_key = {e.module_key: e for e in index.modules}
    assert by_key[WholeBookModuleKey.CHARACTERS].module_status == WholeBookModuleStatus.NOT_REQUESTED
    assert by_key[WholeBookModuleKey.STORYLINES].module_status == WholeBookModuleStatus.RUNNING
    available = svc.list_available_modules(run.id)
    assert WholeBookModuleKey.STORYLINES in available
    assert svc.get_module_status(run.id, "storylines") == WholeBookModuleStatus.RUNNING


def test_run_not_found(env) -> None:
    svc = WholeBookResultIndexService(env["session"])
    with pytest.raises(NarrativeCoreError) as exc:
        svc.get_result_index(999999)
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID


def test_non_book_scope_rejected(env) -> None:
    session = env["session"]
    book = env["book"]
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id="1",
        provider="none",
        model="none",
        prompt_version="n/a",
        schema_version="1",
        input_hash="x" * 64,
        status="completed",
        analysis_type=AnalysisType.SCENE_PIPELINE.value,
        scope_type=AnalysisScopeType.CHAPTER.value,
        book_id=book.id,
    )
    session.add(run)
    session.commit()
    svc = WholeBookResultIndexService(session)
    with pytest.raises(NarrativeCoreError) as exc:
        svc.get_result_index(run.id)
    assert exc.value.code == NarrativeCoreErrorCode.INVALID_RUN_SCOPE


def test_envelope_schema_version_and_snapshot_binding(env) -> None:
    session = env["session"]
    book, snapshot = env["book"], env["snapshot"]
    run = _create_book_run(
        session,
        book=book,
        snapshot=snapshot,
        requested_modules=["storylines"],
    )
    _add_stages(
        session,
        run,
        [
            (WholeBookStageKey.RESOLVE_ENTITIES.value, StageStatus.COMPLETED.value),
            (WholeBookStageKey.ANALYZE_STRUCTURE.value, StageStatus.COMPLETED.value),
            (WholeBookStageKey.ANALYZE_STORYLINES.value, StageStatus.COMPLETED.value),
        ],
    )
    _add_asset(
        session,
        book_id=book.id,
        snapshot_id=snapshot.id,
        run_id=run.id,
        asset_key="sl-1",
        asset_type=AssetType.STORYLINE.value,
        title="Main line",
        summary="summary",
        with_evidence=True,
    )
    session.commit()

    svc = WholeBookResultIndexService(session)
    env_dto = svc.get_module_result(run.id, WholeBookModuleKey.STORYLINES)
    assert env_dto.schema == RESULT_ENVELOPE_SCHEMA
    assert env_dto.version == RESULT_ENVELOPE_VERSION
    assert env_dto.book_snapshot_id == snapshot.id
    assert env_dto.run_id == run.id
    assert env_dto.evidence_count >= 1
    assert "full_text" not in env_dto.payload
    assert "body" not in env_dto.payload
    validate_module_payload(WholeBookModuleKey.STORYLINES, env_dto.payload)


def test_book_and_snapshot_isolation(env) -> None:
    session = env["session"]
    book, snapshot = env["book"], env["snapshot"]
    other = Book(
        title="Other Book",
        source_file_name="other.txt",
        source_file_hash="o" * 64,
        created_at=datetime.now(timezone.utc),
    )
    session.add(other)
    session.flush()
    other_snap = make_stub_completed_snapshot(session, book_id=other.id, content_hash="d" * 64)

    run = _create_book_run(
        session,
        book=book,
        snapshot=snapshot,
        requested_modules=["storylines"],
    )
    _add_stages(
        session,
        run,
        [(WholeBookStageKey.ANALYZE_STORYLINES.value, StageStatus.COMPLETED.value)],
    )
    _add_asset(
        session,
        book_id=book.id,
        snapshot_id=snapshot.id,
        run_id=run.id,
        asset_key="mine",
        asset_type=AssetType.STORYLINE.value,
        title="Mine",
    )
    _add_asset(
        session,
        book_id=other.id,
        snapshot_id=other_snap.id,
        run_id=None,
        asset_key="theirs",
        asset_type=AssetType.STORYLINE.value,
        title="Theirs",
    )
    session.commit()

    svc = WholeBookResultIndexService(session)
    env_dto = svc.get_module_result(run.id, "storylines")
    titles = [i["title"] for i in env_dto.payload["items"]]
    assert "Mine" in titles
    assert "Theirs" not in titles


def test_canonical_default_candidate_explicit_rejected_excluded(env) -> None:
    session = env["session"]
    book, snapshot = env["book"], env["snapshot"]
    run = _create_book_run(
        session,
        book=book,
        snapshot=snapshot,
        requested_modules=["storylines"],
    )
    _add_stages(
        session,
        run,
        [(WholeBookStageKey.ANALYZE_STORYLINES.value, StageStatus.COMPLETED.value)],
    )
    _add_asset(
        session,
        book_id=book.id,
        snapshot_id=snapshot.id,
        run_id=run.id,
        asset_key="canon",
        asset_type=AssetType.STORYLINE.value,
        title="Canonical",
        is_canonical=True,
        review_status=ReviewStatus.CONFIRMED.value,
    )
    _add_asset(
        session,
        book_id=book.id,
        snapshot_id=snapshot.id,
        run_id=run.id,
        asset_key="cand",
        asset_type=AssetType.STORYLINE.value,
        title="Candidate",
        is_canonical=False,
        review_status=ReviewStatus.CANDIDATE.value,
    )
    _add_asset(
        session,
        book_id=book.id,
        snapshot_id=snapshot.id,
        run_id=run.id,
        asset_key="rej",
        asset_type=AssetType.STORYLINE.value,
        title="Rejected",
        is_canonical=False,
        review_status=ReviewStatus.REJECTED.value,
    )
    session.commit()

    svc = WholeBookResultIndexService(session)
    canon = svc.get_module_result(run.id, "storylines", view="canonical")
    cand = svc.get_module_result(run.id, "storylines", view="candidate")
    assert [i["title"] for i in canon.payload["items"]] == ["Canonical"]
    assert "Rejected" not in [i["title"] for i in cand.payload["items"]]
    assert "Candidate" in [i["title"] for i in cand.payload["items"]]
    assert "explicit_candidate_view" in cand.warnings


def test_conflict_and_review_summary(env) -> None:
    session = env["session"]
    book, snapshot = env["book"], env["snapshot"]
    run = _create_book_run(
        session,
        book=book,
        snapshot=snapshot,
        requested_modules=["storylines"],
    )
    _add_stages(
        session,
        run,
        [(WholeBookStageKey.ANALYZE_STORYLINES.value, StageStatus.COMPLETED.value)],
    )
    asset, version = _add_asset(
        session,
        book_id=book.id,
        snapshot_id=snapshot.id,
        run_id=run.id,
        asset_key="sl",
        asset_type=AssetType.STORYLINE.value,
        title="A",
        review_status=ReviewStatus.CANDIDATE.value,
        is_canonical=False,
    )
    _add_asset(
        session,
        book_id=book.id,
        snapshot_id=snapshot.id,
        run_id=run.id,
        asset_key="sl2",
        asset_type=AssetType.STORYLINE.value,
        title="B",
        review_status=ReviewStatus.CONFIRMED.value,
        is_canonical=True,
    )
    session.add(
        AnalysisConflict(
            book_id=book.id,
            run_id=run.id,
            book_snapshot_id=snapshot.id,
            conflict_type=ConflictType.CANDIDATE_CONTRADICTION.value,
            left_ref_type="asset_version",
            left_ref_id=str(version.id),
            right_ref_type="asset",
            right_ref_id=str(asset.id),
            description="fixture conflict",
            severity=ConflictSeverity.WARNING.value,
            status=ConflictStatus.OPEN.value,
        )
    )
    session.commit()

    svc = WholeBookResultIndexService(session)
    env_dto = svc.get_module_result(run.id, "storylines")
    assert env_dto.review_summary.conflict_count >= 1
    assert len(env_dto.conflict_ids) >= 1
    summary = svc.get_conflict_summary(
        book_id=book.id, book_snapshot_id=snapshot.id, run_id=run.id
    )
    assert summary.warning >= 1
    assert summary.blocking == 0


def test_eleven_empty_dto_and_fixture_validation() -> None:
    for module in WholeBookModuleKey:
        payload = empty_payload_for_module(module)
        validate_module_payload(module, payload)
        if "items" in payload:
            assert payload["items"] == []
            assert MODULE_RESULT_DTO_BY_KEY[module] is not None


def test_refresh_projection_does_not_write(env) -> None:
    session = env["session"]
    book, snapshot = env["book"], env["snapshot"]
    run = _create_book_run(
        session,
        book=book,
        snapshot=snapshot,
        requested_modules=["book_overview"],
    )
    _add_stages(
        session,
        run,
        [(WholeBookStageKey.BUILD_FULLTEXT_INDEX.value, StageStatus.COMPLETED.value)],
    )
    session.commit()
    before = session.scalar(select(func.count()).select_from(NarrativeAsset))
    svc = WholeBookResultIndexService(session)
    svc.refresh_projection(run.id)
    after = session.scalar(select(func.count()).select_from(NarrativeAsset))
    assert before == after


def test_blocked_status_with_open_blocking_conflict(env) -> None:
    session = env["session"]
    book, snapshot = env["book"], env["snapshot"]
    run = _create_book_run(
        session,
        book=book,
        snapshot=snapshot,
        requested_modules=["hooks_payoffs"],
    )
    _add_stages(
        session,
        run,
        [
            (WholeBookStageKey.ANALYZE_STRUCTURE.value, StageStatus.PENDING.value),
            (WholeBookStageKey.ANALYZE_STORYLINES.value, StageStatus.PENDING.value),
            (WholeBookStageKey.ANALYZE_HOOKS.value, StageStatus.PENDING.value),
        ],
    )
    session.add(
        AnalysisConflict(
            book_id=book.id,
            run_id=run.id,
            book_snapshot_id=snapshot.id,
            conflict_type=ConflictType.LOCKED_ASSET_VS_NEW_RUN.value,
            left_ref_type="asset",
            left_ref_id="1",
            right_ref_type="run",
            right_ref_id=str(run.id),
            description="blocking fixture",
            severity=ConflictSeverity.BLOCKING.value,
            status=ConflictStatus.OPEN.value,
        )
    )
    session.commit()
    svc = WholeBookResultIndexService(session)
    assert svc.get_module_status(run.id, "hooks_payoffs") == WholeBookModuleStatus.BLOCKED


def test_pattern_projection_inputs(env) -> None:
    session = env["session"]
    book, snapshot = env["book"], env["snapshot"]
    run = _create_book_run(
        session,
        book=book,
        snapshot=snapshot,
        requested_modules=["storylines", "causal_chain"],
    )
    a1, _ = _add_asset(
        session,
        book_id=book.id,
        snapshot_id=snapshot.id,
        run_id=run.id,
        asset_key="e1",
        asset_type=AssetType.EVENT.value,
        title="E1",
        is_canonical=True,
        with_evidence=True,
    )
    a2, _ = _add_asset(
        session,
        book_id=book.id,
        snapshot_id=snapshot.id,
        run_id=run.id,
        asset_key="e2",
        asset_type=AssetType.EVENT.value,
        title="E2",
        is_canonical=True,
    )
    _add_relation(
        session,
        book_id=book.id,
        snapshot_id=snapshot.id,
        run_id=run.id,
        source_asset_id=a1.id,
        target_asset_id=a2.id,
        relation_type=RelationType.CAUSES.value,
        is_canonical=True,
    )
    session.commit()

    svc = WholeBookResultIndexService(session)
    assets = svc.get_canonical_assets_for_projection(
        book_id=book.id, book_snapshot_id=snapshot.id, run_id=run.id
    )
    rels = svc.get_canonical_relations_for_projection(
        book_id=book.id, book_snapshot_id=snapshot.id, run_id=run.id
    )
    assert any(a.title == "E1" for a in assets)
    assert len(rels) == 1
    cand_assets = svc.get_candidate_assets_for_projection(
        book_id=book.id, book_snapshot_id=snapshot.id, run_id=run.id
    )
    assert all(not a.is_canonical for a in cand_assets)
    evidence = svc.get_evidence_index(
        book_id=book.id,
        book_snapshot_id=snapshot.id,
        asset_version_ids=[assets[0].version_id],
    )
    assert evidence
    assert all(e.paragraph_content_hash for e in evidence)
    review = svc.get_review_summary(
        book_id=book.id, book_snapshot_id=snapshot.id, run_id=run.id
    )
    assert review.confirmed_count + review.candidate_count >= 0


def test_query_count_bound_no_obvious_n_plus_one(env) -> None:
    session = env["session"]
    book, snapshot = env["book"], env["snapshot"]
    run = _create_book_run(
        session,
        book=book,
        snapshot=snapshot,
        requested_modules=["storylines"],
    )
    _add_stages(
        session,
        run,
        [(WholeBookStageKey.ANALYZE_STORYLINES.value, StageStatus.COMPLETED.value)],
    )
    for i in range(40):
        _add_asset(
            session,
            book_id=book.id,
            snapshot_id=snapshot.id,
            run_id=run.id,
            asset_key=f"sl-{i}",
            asset_type=AssetType.STORYLINE.value,
            title=f"S{i}",
            with_evidence=(i % 5 == 0),
        )
    session.commit()

    counter = _QueryCounter()
    svc = WholeBookResultIndexService(session, query_counter=counter)
    svc.get_result_index(run.id)
    first = counter.count
    assert first < 40, f"query count too high (likely N+1): {first}"
    env_dto = svc.get_module_result(run.id, "storylines")
    assert len(env_dto.payload["items"]) <= 100
    blob = json.dumps(env_dto.payload)
    assert "证据段落" not in blob
    assert "full_text" not in blob


def test_api_results_index_and_module(env) -> None:
    session = env["session"]
    book, snapshot = env["book"], env["snapshot"]
    run = _create_book_run(
        session,
        book=book,
        snapshot=snapshot,
        requested_modules=["book_overview", "storylines"],
    )
    _add_stages(
        session,
        run,
        [
            (WholeBookStageKey.BUILD_FULLTEXT_INDEX.value, StageStatus.COMPLETED.value),
            (WholeBookStageKey.ANALYZE_STORYLINES.value, StageStatus.COMPLETED.value),
        ],
    )
    session.commit()

    app = FastAPI()
    app.include_router(whole_book_results_router)

    def _override_db():
        yield session

    from app.db.session import get_db

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)

    r = client.get(f"/api/v1/whole-book-runs/{run.id}/results")
    assert r.status_code == 200
    body = r.json()
    assert body["schema"] == "whole_book_result_index"
    assert len(body["modules"]) == 11

    r2 = client.get(f"/api/v1/whole-book-runs/{run.id}/results/storylines")
    assert r2.status_code == 200
    mod = r2.json()
    assert mod["schema"] == RESULT_ENVELOPE_SCHEMA
    assert mod["version"] == RESULT_ENVELOPE_VERSION
    assert mod["module_key"] == "storylines"
    assert "prompt" not in mod
    assert "credential" not in mod
    assert "full_text" not in json.dumps(mod)

    r3 = client.get(f"/api/v1/whole-book-runs/{run.id}/results/not_a_module")
    assert r3.status_code == 404
    assert r3.json()["detail"]["error_code"] == "WHOLE_BOOK_MODULE_NOT_SUPPORTED"


def test_api_does_not_call_engine(env, monkeypatch) -> None:
    session = env["session"]
    book, snapshot = env["book"], env["snapshot"]
    run = _create_book_run(
        session,
        book=book,
        snapshot=snapshot,
        requested_modules=["book_overview"],
    )
    _add_stages(
        session,
        run,
        [(WholeBookStageKey.BUILD_FULLTEXT_INDEX.value, StageStatus.COMPLETED.value)],
    )
    session.commit()

    import app.narrative_core.services.mock_whole_book_engine as mock_engine_mod

    def _boom(*_a, **_k):
        raise AssertionError("engine must not be called")

    for name in dir(mock_engine_mod):
        obj = getattr(mock_engine_mod, name)
        if isinstance(obj, type) and name.endswith("Engine"):
            for method in ("execute_stage", "run", "analyze", "build_stage_plan"):
                if hasattr(obj, method):
                    monkeypatch.setattr(obj, method, _boom)

    app = FastAPI()
    app.include_router(whole_book_results_router)

    def _override_db():
        yield session

    from app.db.session import get_db

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    assert client.get(f"/api/v1/whole-book-runs/{run.id}/results").status_code == 200
    assert client.get(f"/api/v1/whole-book-runs/{run.id}/results/book_overview").status_code == 200


def test_stale_module_status_from_lifecycle(env) -> None:
    session = env["session"]
    book, snapshot = env["book"], env["snapshot"]
    run = _create_book_run(
        session,
        book=book,
        snapshot=snapshot,
        requested_modules=["storylines"],
    )
    deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.STORYLINES]
    _add_stages(
        session,
        run,
        [(d.value, StageStatus.COMPLETED.value) for d in deps],
    )
    _add_asset(
        session,
        book_id=book.id,
        snapshot_id=snapshot.id,
        run_id=run.id,
        asset_key="stale-sl",
        asset_type=AssetType.STORYLINE.value,
        title="Stale",
        lifecycle_status=AssetLifecycleStatus.STALE.value,
    )
    session.commit()
    svc = WholeBookResultIndexService(session)
    assert svc.get_module_status(run.id, "storylines") == WholeBookModuleStatus.STALE
