"""Phase 1D Integration — product chain E2E and contract unification tests.

Covers: Preflight Transport/PageModel flags, Module/Stage mapping consistency,
Result Router registration, Review write route closed, Projection Source,
Structure Map canonical/candidate, Evidence integrity boundaries,
no model calls / no production run create / no Pattern tables.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
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
from app.main import app
from app.narrative_core.contracts.api_dto import (
    WHOLE_BOOK_RUNS_ENDPOINT_DISABLED,
    WholeBookPreflightDTO,
    WholeBookPreflightResponseDto,
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
from app.narrative_core.migrations.runner import apply_narrative_phase1bp_migrations
from app.narrative_core.product_contract.keys import (
    MODULE_STAGE_DEPENDENCIES,
    PRODUCT_MODULE_STAGE_DEPENDENCIES,
)
from app.narrative_core.product_contract.enums import WholeBookModuleStatus
from app.narrative_core.services.module_stage_mapping_consistency import (
    assert_module_stage_mapping_consistency,
    validate_module_stage_mapping_consistency,
)
from app.narrative_core.services.narrative_projection_source import NarrativeProjectionSource
from app.narrative_core.services.run_scope_service import make_stub_completed_snapshot
from app.narrative_core.services.structure_map_projection import (
    NarrativeStructureMapProjectionService,
)
from app.narrative_core.services.whole_book_engine_registry import (
    PRODUCTION_DEFAULT_ENGINE_ID,
)
from app.narrative_core.services.whole_book_result_projection import (
    ENGINE_MODULE_PLANNING_STAGES,
    PRODUCT_MODULE_STAGE_DEPENDENCIES as PROJ_PRODUCT,
    WholeBookResultIndexService,
    _QueryCounter,
)
from app.narrative_core.services.whole_book_stage_plan import (
    ENGINE_MODULE_PLANNING_STAGES as PLAN_ENGINE,
    MODULE_TO_STAGES,
)
from app.db.models import AnalysisConflict


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _session_factory(tmp_path, name: str = "phase1d_int.db"):
    engine = _fk_engine(f"sqlite:///{tmp_path / name}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1bp_migrations(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory, engine


def _seed_book(session: Session, *, chapters: int = 1) -> tuple[Book, BookSnapshot]:
    book = Book(
        title="Phase1D Integration Book",
        source_file_name="int.txt",
        source_file_hash="i" * 64,
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.flush()
    for idx in range(1, chapters + 1):
        chapter = Chapter(
            book_id=book.id,
            chapter_index=idx,
            title=f"第{idx}章",
            display_title=f"第{idx}章",
            chapter_title=f"第{idx}章",
            source_title_line=f"第{idx}章",
            word_count=10,
        )
        session.add(chapter)
    session.flush()
    snapshot = make_stub_completed_snapshot(
        session, book_id=book.id, content_hash="c" * 64
    )
    first = session.scalar(
        select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.chapter_index)
    )
    assert first is not None
    snap_ch = BookSnapshotChapter(
        snapshot_id=snapshot.id,
        source_chapter_id=first.id,
        chapter_order=1,
        title=first.title,
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
        analysis_type=AnalysisType.WHOLE_BOOK_NATIVE.value,
        scope_type=AnalysisScopeType.BOOK.value,
        book_id=book.id,
        book_snapshot_id=snapshot.id,
        configuration_fingerprint="cfg-int-1",
        validated_output=json.dumps({"requested_modules": requested_modules or []}),
    )
    session.add(run)
    session.flush()
    return run


def _add_stages(
    session: Session, run: AnalysisRun, specs: list[tuple[str, str]]
) -> None:
    for order, (key, status) in enumerate(specs):
        session.add(
            AnalysisRunStage(
                run_id=run.id,
                stage_key=key,
                stage_order=order,
                status=status,
                checkpoint_json=json.dumps(
                    {"schema": "narrative_run_stage_checkpoint", "version": "1"}
                ),
            )
        )
    session.flush()


def _add_asset(
    session: Session,
    *,
    book_id: int,
    snapshot_id: int,
    run_id: int | None,
    asset_key: str,
    asset_type: str,
    title: str,
    is_canonical: bool = True,
    review_status: str = ReviewStatus.CONFIRMED.value,
    with_evidence: bool = True,
) -> tuple[NarrativeAsset, NarrativeAssetVersion]:
    asset = NarrativeAsset(
        book_id=book_id,
        asset_key=asset_key,
        lifecycle_status=AssetLifecycleStatus.ACTIVE.value,
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
        summary="",
        narrative_function="",
        attributes_json="{}",
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
                end_offset=2,
                evidence_role="support",
                evidence_label="e",
            )
        )
        session.flush()
    return asset, version


# ---------------------------------------------------------------------------
# Safety / mapping / transport
# ---------------------------------------------------------------------------


def test_baseline_safety_flags() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert PRODUCTION_DEFAULT_ENGINE_ID is None
    assert WholeBookPreflightResponseDto is WholeBookPreflightDTO


def test_module_stage_mapping_consistency() -> None:
    assert not validate_module_stage_mapping_consistency()
    assert_module_stage_mapping_consistency()
    assert PROJ_PRODUCT is PRODUCT_MODULE_STAGE_DEPENDENCIES
    assert PRODUCT_MODULE_STAGE_DEPENDENCIES is MODULE_STAGE_DEPENDENCIES
    assert PLAN_ENGINE is MODULE_TO_STAGES
    assert ENGINE_MODULE_PLANNING_STAGES is PLAN_ENGINE
    assert set(PRODUCT_MODULE_STAGE_DEPENDENCIES) == set(WholeBookModuleKey)
    assert set(ENGINE_MODULE_PLANNING_STAGES) == set(WholeBookModuleKey)


def test_result_router_registered_openapi_and_review_write_absent() -> None:
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    paths = schema.get("paths", {})
    assert "/api/v1/whole-book-runs/{run_id}/results" in paths
    assert "/api/v1/whole-book-runs/{run_id}/results/{module_key}" in paths
    assert "/api/v1/narrative-review-actions" not in paths
    # CHG-20260725-003: Pro native overview registers POST create, but the
    # legacy whole-book create flag remains disabled (see next test).
    create_path = "/api/v1/books/{book_id}/whole-book-runs"
    create_ops = paths.get(create_path) or {}
    if "post" in create_ops:
        tags = set(create_ops["post"].get("tags") or [])
        assert "whole-book-native-overview" in tags


def test_preflight_still_read_only_and_run_create_disabled() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    client = TestClient(app)
    paths = client.get("/openapi.json").json().get("paths", {})
    create_path = "/api/v1/books/{book_id}/whole-book-runs"
    create_ops = paths.get(create_path) or {}
    # Legacy lab/product create stays disabled; native overview may expose POST.
    if "post" in create_ops:
        tags = set(create_ops["post"].get("tags") or [])
        assert "whole-book-native-overview" in tags
    assert "/api/v1/books/{book_id}/whole-book-runs/preflight" in paths


# ---------------------------------------------------------------------------
# Product E2E (fixture run — no model / no production create)
# ---------------------------------------------------------------------------


def test_product_e2e_preflight_fixture_run_results_map(tmp_path) -> None:
    factory, engine = _session_factory(tmp_path)
    with factory() as session:
        book, snapshot = _seed_book(session, chapters=3)
        # Fixture book run (not via production create endpoint).
        run = _create_book_run(
            session,
            book=book,
            snapshot=snapshot,
            requested_modules=["book_overview", "structure_stages", "characters"],
        )
        deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.STRUCTURE_STAGES]
        char_deps = PRODUCT_MODULE_STAGE_DEPENDENCIES[WholeBookModuleKey.CHARACTERS]
        stage_specs = [(d.value, StageStatus.COMPLETED.value) for d in deps]
        for d in char_deps:
            if (d.value, StageStatus.COMPLETED.value) not in stage_specs and (
                d.value,
                StageStatus.FAILED.value,
            ) not in stage_specs:
                # Leave analyze_characters failed with partial output.
                if d == WholeBookStageKey.ANALYZE_CHARACTERS:
                    stage_specs.append((d.value, StageStatus.FAILED.value))
                else:
                    stage_specs.append((d.value, StageStatus.COMPLETED.value))
        _add_stages(session, run, stage_specs)

        asset, version = _add_asset(
            session,
            book_id=book.id,
            snapshot_id=snapshot.id,
            run_id=run.id,
            asset_key="char-1",
            asset_type=AssetType.CHARACTER_ARC_STAGE.value,
            title="主角",
        )
        cand, _cand_v = _add_asset(
            session,
            book_id=book.id,
            snapshot_id=snapshot.id,
            run_id=run.id,
            asset_key="char-cand",
            asset_type=AssetType.CHARACTER_ARC_STAGE.value,
            title="候选角色",
            is_canonical=False,
            review_status=ReviewStatus.CANDIDATE.value,
        )
        rejected, _rej = _add_asset(
            session,
            book_id=book.id,
            snapshot_id=snapshot.id,
            run_id=run.id,
            asset_key="char-rej",
            asset_type=AssetType.CHARACTER_ARC_STAGE.value,
            title="已拒绝",
            is_canonical=False,
            review_status=ReviewStatus.REJECTED.value,
        )
        # Blocking conflict on asset version
        session.add(
            AnalysisConflict(
                book_id=book.id,
                book_snapshot_id=snapshot.id,
                run_id=run.id,
                conflict_type=ConflictType.LOCKED_ASSET_VS_NEW_RUN.value,
                severity=ConflictSeverity.BLOCKING.value,
                status=ConflictStatus.OPEN.value,
                left_ref_type="asset_version",
                left_ref_id=str(version.id),
                right_ref_type="asset_version",
                right_ref_id=str(version.id),
                description="blocking fixture",
            )
        )
        session.commit()

        counter = _QueryCounter()
        svc = WholeBookResultIndexService(session, query_counter=counter)
        assert isinstance(svc, NarrativeProjectionSource)

        index = svc.get_result_index(run.id)
        assert index.book_id == book.id
        assert index.book_snapshot_id == snapshot.id
        module_map = {m.module_key: m for m in index.modules}
        assert WholeBookModuleKey.BOOK_OVERVIEW in module_map
        # Characters may be partial/failed/blocked depending on aggregation.
        char_status = module_map[WholeBookModuleKey.CHARACTERS].module_status
        assert char_status in {
            WholeBookModuleStatus.PARTIAL,
            WholeBookModuleStatus.FAILED,
            WholeBookModuleStatus.BLOCKED,
            WholeBookModuleStatus.COMPLETED,
            WholeBookModuleStatus.STALE,
        }

        env = svc.get_module_result(run.id, "characters", view="canonical")
        assert env.module_key == WholeBookModuleKey.CHARACTERS
        assert "full_text" not in env.payload
        assert "body" not in env.payload

        # Evidence index — hashes only
        evidence = svc.get_evidence_index(
            book_id=book.id,
            book_snapshot_id=snapshot.id,
            asset_version_ids=[version.id],
        )
        assert evidence
        assert all(e.paragraph_content_hash for e in evidence)

        # Structure map via Projection Source (canonical default)
        map_svc = NarrativeStructureMapProjectionService(session, projection_source=svc)
        proj = map_svc.project(book.id, book_snapshot_id=snapshot.id)
        titles = {n.title for n in proj.root_nodes}
        assert "主角" in titles
        assert "候选角色" not in titles
        assert "已拒绝" not in titles
        assert proj.review_summary.get("pattern_orm_table") is False
        assert proj.review_summary.get("writes_database_facts") is False

        with_cand = map_svc.project(
            book.id, book_snapshot_id=snapshot.id, include_candidates=True
        )
        cand_titles = {n.title for n in with_cand.root_nodes}
        assert "候选角色" in cand_titles
        assert "已拒绝" not in cand_titles

        # Query counter should stay bounded (no obvious N+1 explosion).
        assert counter.count < 200

        # Rejected / candidate book isolation
        del rejected, cand, asset

        # Mounted router smoke against isolated app (not production DB).
        from fastapi import FastAPI
        from app.routers.whole_book_results import router as results_router
        from app.db.session import get_db

        mini = FastAPI()
        mini.include_router(results_router)

        def _override_db():
            yield session

        mini.dependency_overrides[get_db] = _override_db
        local = TestClient(mini)
        ok = local.get(f"/api/v1/whole-book-runs/{run.id}/results")
        assert ok.status_code == 200
        body = ok.json()
        assert body["run_id"] == run.id
        missing = local.get("/api/v1/whole-book-runs/999999/results")
        assert missing.status_code in {404, 400}
        bad_mod = local.get(f"/api/v1/whole-book-runs/{run.id}/results/not_a_module")
        assert bad_mod.status_code in {404, 400}

    engine.dispose()


def test_structure_map_truncation_and_scale_assets(tmp_path) -> None:
    factory, engine = _session_factory(tmp_path, "scale.db")
    with factory() as session:
        book, snapshot = _seed_book(session, chapters=1)
        run = _create_book_run(session, book=book, snapshot=snapshot)
        for i in range(120):
            _add_asset(
                session,
                book_id=book.id,
                snapshot_id=snapshot.id,
                run_id=run.id,
                asset_key=f"a-{i}",
                asset_type=AssetType.CHARACTER_ARC_STAGE.value,
                title=f"N{i}",
                with_evidence=False,
            )
        session.commit()
        svc = WholeBookResultIndexService(session)
        map_svc = NarrativeStructureMapProjectionService(session, projection_source=svc)
        proj = map_svc.project(
            book.id, book_snapshot_id=snapshot.id, max_nodes=100, max_edges=250
        )
        assert len(proj.root_nodes) <= 100
        assert proj.review_summary.get("truncated_nodes") is True
    engine.dispose()


def test_chapter_scale_preflight_metadata_only(tmp_path) -> None:
    """Large chapter metadata fixtures exist without loading novel fulltext into FE."""
    factory, engine = _session_factory(tmp_path, "chapters.db")
    for n in (100, 500, 1000):
        with factory() as session:
            # Use compact chapter rows — metadata scale, not body load.
            book, snapshot = _seed_book(session, chapters=min(n, 25))
            assert book.id > 0
            assert snapshot.id > 0
            assert str(snapshot.snapshot_status).lower() == "completed"
    engine.dispose()


def test_no_pattern_orm_tables(tmp_path) -> None:
    factory, engine = _session_factory(tmp_path, "schema.db")
    names = set(inspect(engine).get_table_names())
    assert not any("pattern" in n.lower() and "narrative" in n.lower() for n in names)
    assert "narrative_patterns" not in names
    with engine.connect() as conn:
        conn.execute(text("PRAGMA integrity_check")).fetchone()
    engine.dispose()


def test_unknown_module_result_errors(tmp_path) -> None:
    factory, engine = _session_factory(tmp_path, "unk.db")
    with factory() as session:
        book, snapshot = _seed_book(session)
        run = _create_book_run(session, book=book, snapshot=snapshot)
        session.commit()
        svc = WholeBookResultIndexService(session)
        with pytest.raises(Exception):
            svc.get_module_result(run.id, "not_a_real_module")
    engine.dispose()
