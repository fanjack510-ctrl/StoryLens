"""Phase 1A Integration: Snapshot + Run Stage + migration directed tests.

Cross-module verification only. Does not call models, create whole-book jobs,
or start Phase 1B.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AnalysisRun, AnalysisRunStage, Base, Book, BookSnapshot, Chapter, Paragraph
from app.narrative_core.enums import (
    AnalysisScopeType,
    AnalysisType,
    RunStatus,
    SnapshotStatus,
    StageStatus,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.hash_canon import BookHashChapterInput, calculate_book_content_hash, calculate_text_hash
from app.narrative_core.migrations import (
    MIGRATION_BOOK_SNAPSHOTS,
    NARRATIVE_MIGRATION_ORDER,
    migration_checksum,
)
from app.narrative_core.migrations.runner import (
    SQL_003,
    apply_narrative_phase1p_migrations,
    register_baseline_1_0_5,
)
from app.narrative_core.services.hash_backfill import ContentHashServiceImpl
from app.narrative_core.services.run_stage_service import RunStageService, SimulatedStageRunner
from app.narrative_core.services.snapshot_repository import BookSnapshotRepositoryImpl
from app.narrative_core.services.snapshot_service import (
    BookSnapshotServiceImpl,
    SnapshotValidationGatewayImpl,
)
from app.services.scene_pipeline import mark_interrupted_runs_failed


def _engine(tmp_path, name: str = "phase1a.db"):
    engine = create_engine(
        f"sqlite:///{tmp_path / name}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _session(engine) -> Session:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _seed_book(session: Session, *, suffix: str = "") -> Book:
    book = Book(
        title=f"Integration Book{suffix}",
        source_file_name=f"int{suffix}.txt",
        source_file_hash=f"src{suffix}"[:64].ljust(16, "0"),
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.flush()
    for idx, (title, bodies) in enumerate(
        [("第一章", ["甲段", "乙段"]), ("第二章", ["丙段"])],
        start=1,
    ):
        chapter = Chapter(
            book_id=book.id,
            chapter_index=idx,
            title=title,
            display_title=title,
            chapter_title=title,
            source_title_line=title,
            word_count=sum(len(b) for b in bodies),
        )
        session.add(chapter)
        session.flush()
        offset = 0
        for pidx, body in enumerate(bodies, start=1):
            session.add(
                Paragraph(
                    id=f"B{book.id:04d}-C{idx:04d}-P{pidx:04d}",
                    book_id=book.id,
                    chapter_id=chapter.id,
                    paragraph_index=pidx,
                    raw_text=body,
                    normalized_text=body,
                    char_start=offset,
                    char_end=offset + len(body),
                )
            )
            offset += len(body) + 1
    session.commit()
    return book


def test_migrations_001_to_005_order_idempotent_and_checksum(tmp_path) -> None:
    assert NARRATIVE_MIGRATION_ORDER == (
        "20260723_001_schema_migrations",
        "20260723_002_content_hashes",
        "20260723_003_book_snapshots",
        "20260723_004_analysis_run_scope",
        "20260723_005_analysis_run_stages",
    )
    engine = _engine(tmp_path, "mig.db")
    Base.metadata.create_all(engine)
    register_baseline_1_0_5(engine)
    apply_narrative_phase1p_migrations(engine)
    apply_narrative_phase1p_migrations(engine)  # idempotent

    cols = {c["name"] for c in inspect(engine).get_columns("book_snapshots")}
    assert {"error_code", "error_message", "source_fingerprint"} <= cols

    with engine.begin() as connection:
        rows = connection.execute(
            text("SELECT migration_id, checksum FROM schema_migrations ORDER BY migration_id")
        ).fetchall()
    ids = [r[0] for r in rows]
    assert "baseline_1_0_5" in ids
    assert MIGRATION_BOOK_SNAPSHOTS in ids
    stored = {r[0]: r[1] for r in rows}
    assert stored[MIGRATION_BOOK_SNAPSHOTS] == migration_checksum(SQL_003)

    # Checksum conflict must fail clearly.
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE schema_migrations SET checksum = :bad WHERE migration_id = :mid"
            ),
            {"bad": "0" * 64, "mid": MIGRATION_BOOK_SNAPSHOTS},
        )
    with pytest.raises(NarrativeCoreError) as exc_info:
        apply_narrative_phase1p_migrations(engine)
    assert exc_info.value.code == NarrativeCoreErrorCode.MIGRATION_CHECKSUM_MISMATCH
    engine.dispose()


def test_simulate_1_0_5_upgrade_preserves_legacy_run(tmp_path) -> None:
    engine = _engine(tmp_path, "legacy.db")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE books (
                    id INTEGER PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    author VARCHAR(255),
                    source_file_name VARCHAR(500) NOT NULL,
                    source_file_hash VARCHAR(64) NOT NULL,
                    import_status VARCHAR(32) NOT NULL DEFAULT 'imported',
                    language VARCHAR(32) NOT NULL DEFAULT 'zh-CN',
                    revision_number INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE chapters (
                    id INTEGER PRIMARY KEY,
                    book_id INTEGER NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    word_count INTEGER NOT NULL DEFAULT 0,
                    section_type VARCHAR(32) NOT NULL DEFAULT 'body',
                    chapter_title VARCHAR(500) NOT NULL DEFAULT '',
                    display_title VARCHAR(600) NOT NULL DEFAULT '',
                    source_title_line VARCHAR(600) NOT NULL DEFAULT '',
                    FOREIGN KEY(book_id) REFERENCES books(id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE analysis_runs (
                    id INTEGER PRIMARY KEY,
                    task_type VARCHAR(100) NOT NULL,
                    subject_type VARCHAR(50) NOT NULL,
                    subject_id VARCHAR(100) NOT NULL,
                    provider VARCHAR(100) NOT NULL,
                    model VARCHAR(255) NOT NULL,
                    prompt_version VARCHAR(50) NOT NULL,
                    schema_version VARCHAR(50) NOT NULL,
                    input_hash VARCHAR(64) NOT NULL,
                    prompt_hash VARCHAR(64) NOT NULL DEFAULT '',
                    status VARCHAR(32) NOT NULL,
                    progress_current INTEGER NOT NULL DEFAULT 0,
                    progress_total INTEGER NOT NULL DEFAULT 0,
                    error_code VARCHAR(100),
                    created_at DATETIME NOT NULL,
                    queued_at DATETIME NOT NULL,
                    started_at DATETIME NOT NULL,
                    run_started_at DATETIME,
                    completed_at DATETIME,
                    error_message TEXT,
                    retryable INTEGER NOT NULL DEFAULT 0,
                    execution_mode VARCHAR(16) NOT NULL DEFAULT 'local',
                    analysis_mode VARCHAR(40) NOT NULL DEFAULT 'automatic'
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO books (id,title,source_file_name,source_file_hash,created_at) "
                "VALUES (1,'Legacy','a.txt','h','2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO analysis_runs "
                "(id,task_type,subject_type,subject_id,provider,model,prompt_version,"
                "schema_version,input_hash,status,created_at,queued_at,started_at) "
                "VALUES (1,'scene_pipeline','chapter','1','local','m','v1','v1',"
                ":ih,'completed','2026-01-01','2026-01-01','2026-01-01')"
            ),
            {"ih": "0" * 64},
        )
    apply_narrative_phase1p_migrations(engine)
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT subject_type, subject_id, status, scope_type FROM analysis_runs WHERE id=1")
        ).fetchone()
    assert row is not None
    assert row[0] == "chapter"
    assert row[1] == "1"
    assert row[2] == "completed"
    assert row[3] is None
    engine.dispose()


def test_book_hash_title_and_order_change(tmp_path) -> None:
    engine = _engine(tmp_path, "hash.db")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    session = _session(engine)
    h1 = calculate_text_hash("body-a")
    h2 = calculate_text_hash("body-b")
    base = calculate_book_content_hash(
        [BookHashChapterInput(1, "T1", h1), BookHashChapterInput(2, "T2", h2)]
    )
    assert base != calculate_book_content_hash(
        [BookHashChapterInput(1, "T1-changed", h1), BookHashChapterInput(2, "T2", h2)]
    )
    assert base != calculate_book_content_hash(
        [BookHashChapterInput(2, "T1", h1), BookHashChapterInput(1, "T2", h2)]
    )
    assert base != calculate_book_content_hash(
        [
            BookHashChapterInput(1, "T1", calculate_text_hash("body-a2")),
            BookHashChapterInput(2, "T2", h2),
        ]
    )
    service = ContentHashServiceImpl(session)
    assert service.calculate_book_content_hash(
        [BookHashChapterInput(1, "T1", h1), BookHashChapterInput(2, "T2", h2)]
    ) == base
    session.close()
    engine.dispose()


def test_snapshot_create_reuse_error_fields_and_fingerprint(tmp_path) -> None:
    engine = _engine(tmp_path, "snap.db")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    session = _session(engine)
    book = _seed_book(session, suffix="-s")
    service = BookSnapshotServiceImpl(session)
    first = service.create_or_reuse_snapshot(book.id)
    session.commit()
    assert first.snapshot_status == SnapshotStatus.COMPLETED
    assert first.error_code is None
    assert first.error_message is None
    fingerprint = first.source_fingerprint
    assert fingerprint == book.source_file_hash
    assert "error:" not in (fingerprint or "")

    reused = service.create_or_reuse_snapshot(book.id)
    session.commit()
    assert reused.id == first.id

    # Force FAILED with dedicated error fields; fingerprint must stay pure.
    repo = BookSnapshotRepositoryImpl(session)
    repo.mark_snapshot_failed(
        first.id,
        error_code="SIMULATED_FAIL",
        error_message="short diagnostic only",
    )
    session.commit()
    session.refresh(first)
    assert first.snapshot_status == SnapshotStatus.FAILED
    assert first.error_code == "SIMULATED_FAIL"
    assert first.error_message == "short diagnostic only"
    assert first.source_fingerprint == fingerprint

    # Successful rebuild must not pollute fingerprint or leave old errors.
    rebuilt = service.create_or_reuse_snapshot(book.id)
    session.commit()
    assert rebuilt.snapshot_status == SnapshotStatus.COMPLETED
    assert rebuilt.source_fingerprint == fingerprint
    assert rebuilt.error_code is None
    assert rebuilt.error_message is None
    session.close()
    engine.dispose()


def test_real_gateway_book_run_and_rejections(tmp_path) -> None:
    engine = _engine(tmp_path, "gw.db")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    session = _session(engine)
    book = _seed_book(session, suffix="-g")
    other = _seed_book(session, suffix="-o")
    snap_service = BookSnapshotServiceImpl(session)
    completed = snap_service.create_or_reuse_snapshot(book.id)
    session.commit()

    # Production default wiring: real gateway (no Stub).
    stages = RunStageService(session)
    assert isinstance(stages._scope._snapshot_gateway, SnapshotValidationGatewayImpl)

    run = stages.create_scoped_run(
        scope_type=AnalysisScopeType.BOOK,
        analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
        book_id=book.id,
        book_snapshot_id=completed.id,
    )
    assert run.book_snapshot_id == completed.id
    assert run.scope_type == AnalysisScopeType.BOOK

    # CHAPTER scope does not require snapshot.
    chapter = session.scalar(select(Chapter).where(Chapter.book_id == book.id))
    assert chapter is not None
    chapter_run = stages.create_scoped_run(
        scope_type=AnalysisScopeType.CHAPTER,
        analysis_type=AnalysisType.SCENE_PIPELINE,
        book_id=book.id,
        chapter_id=chapter.id,
    )
    assert chapter_run.book_snapshot_id is None

    # Snapshot / book mismatch.
    with pytest.raises(NarrativeCoreError) as mismatch:
        stages.create_scoped_run(
            scope_type=AnalysisScopeType.BOOK,
            analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
            book_id=other.id,
            book_snapshot_id=completed.id,
        )
    assert mismatch.value.code == NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH

    # Missing snapshot.
    with pytest.raises(NarrativeCoreError) as missing:
        stages.create_scoped_run(
            scope_type=AnalysisScopeType.BOOK,
            analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
            book_id=book.id,
            book_snapshot_id=999999,
        )
    assert missing.value.code == NarrativeCoreErrorCode.SNAPSHOT_NOT_FOUND

    # BUILDING / FAILED / INVALID rejections.
    repo = BookSnapshotRepositoryImpl(session)
    for status, code in (
        (SnapshotStatus.BUILDING, NarrativeCoreErrorCode.SNAPSHOT_NOT_COMPLETED),
        (SnapshotStatus.FAILED, NarrativeCoreErrorCode.SNAPSHOT_NOT_COMPLETED),
        (SnapshotStatus.INVALID, NarrativeCoreErrorCode.SNAPSHOT_NOT_COMPLETED),
    ):
        row = BookSnapshot(
            book_id=book.id,
            content_hash=f"{status.value}"[:8].ljust(64, "a"),
            snapshot_status=status.value,
            source_fingerprint=book.source_file_hash,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.flush()
        with pytest.raises(NarrativeCoreError) as rejected:
            stages.create_scoped_run(
                scope_type=AnalysisScopeType.BOOK,
                analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
                book_id=book.id,
                book_snapshot_id=row.id,
            )
        assert rejected.value.code == code

    session.close()
    engine.dispose()


def test_stage_lifecycle_pause_resume_interrupt_retry(tmp_path) -> None:
    engine = _engine(tmp_path, "stage.db")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    session = _session(engine)
    book = _seed_book(session, suffix="-st")
    snap = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    service = RunStageService(session)
    runner = SimulatedStageRunner(service)
    run = service.create_scoped_run(
        scope_type=AnalysisScopeType.BOOK,
        analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
        book_id=book.id,
        book_snapshot_id=snap.id,
        status=RunStatus.RUNNING,
    )
    runner.bootstrap(run.id)
    runner.start(run.id, "prepare")
    runner.complete(
        run.id,
        "prepare",
        checkpoint={"schema": "narrative_run_stage_checkpoint", "version": "1", "cursor": 1},
    )
    runner.start(run.id, "analyze")
    runner.checkpoint(
        run.id,
        "analyze",
        {"schema": "narrative_run_stage_checkpoint", "version": "1", "cursor": 2},
    )

    paused = runner.pause(run.id)
    assert paused.status == RunStatus.PAUSED
    analyze = session.scalar(
        select(AnalysisRunStage).where(
            AnalysisRunStage.run_id == run.id, AnalysisRunStage.stage_key == "analyze"
        )
    )
    assert analyze is not None
    assert analyze.status == StageStatus.PAUSED
    assert analyze.checkpoint_json

    resumed = runner.resume(run.id)
    assert resumed.status == RunStatus.RUNNING
    session.refresh(analyze)
    assert analyze.status == StageStatus.RUNNING

    interrupted = runner.interrupt(run.id)
    assert interrupted.status == RunStatus.INTERRUPTED
    session.refresh(analyze)
    assert analyze.status == StageStatus.INTERRUPTED
    prepare = session.scalar(
        select(AnalysisRunStage).where(
            AnalysisRunStage.run_id == run.id, AnalysisRunStage.stage_key == "prepare"
        )
    )
    assert prepare is not None
    assert prepare.status == StageStatus.COMPLETED

    runner.resume(run.id)
    runner.fail(run.id, "analyze", error_code="X", error_message="fail")
    # resume must not revive failed stages — requires explicit retry.
    service.resume_run(run.id)
    analyze_failed = session.scalar(
        select(AnalysisRunStage).where(
            AnalysisRunStage.run_id == run.id, AnalysisRunStage.stage_key == "analyze"
        )
    )
    assert analyze_failed is not None
    assert analyze_failed.status == StageStatus.FAILED
    retried = runner.retry(run.id, "analyze")
    assert retried.status == StageStatus.RUNNING
    assert retried.attempt_count >= 1

    # completed stage must not re-run via retry
    with pytest.raises(NarrativeCoreError) as completed_block:
        service.retry_failed_stage(run.id, "prepare")
    assert completed_block.value.code == NarrativeCoreErrorCode.COMPLETED_STAGE_CANNOT_RETRY

    session.close()
    engine.dispose()


def test_sidecar_interrupt_compat_staged_vs_legacy(tmp_path) -> None:
    engine = _engine(tmp_path, "sidecar.db")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    session = _session(engine)
    book = _seed_book(session, suffix="-sc")
    snap = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()

    service = RunStageService(session)
    staged = service.create_scoped_run(
        scope_type=AnalysisScopeType.BOOK,
        analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
        book_id=book.id,
        book_snapshot_id=snap.id,
        status=RunStatus.RUNNING,
    )
    runner = SimulatedStageRunner(service)
    runner.bootstrap(staged.id)
    runner.start(staged.id, "prepare")
    runner.complete(staged.id, "prepare")
    runner.start(staged.id, "analyze")
    analyze_before = session.scalar(
        select(AnalysisRunStage).where(
            AnalysisRunStage.run_id == staged.id, AnalysisRunStage.stage_key == "analyze"
        )
    )
    assert analyze_before is not None
    checkpoint = analyze_before.checkpoint_json

    legacy = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(session.scalar(select(Chapter.id).where(Chapter.book_id == book.id))),
        provider="local",
        model="m",
        prompt_version="v1",
        schema_version="v1",
        input_hash="1" * 64,
        status="running",
    )
    session.add(legacy)
    session.commit()

    mark_interrupted_runs_failed(session)
    session.refresh(staged)
    session.refresh(legacy)
    session.refresh(analyze_before)

    assert staged.status == RunStatus.INTERRUPTED
    assert staged.completed_at is None
    assert analyze_before.status == StageStatus.INTERRUPTED
    assert analyze_before.checkpoint_json == checkpoint

    prepare = session.scalar(
        select(AnalysisRunStage).where(
            AnalysisRunStage.run_id == staged.id, AnalysisRunStage.stage_key == "prepare"
        )
    )
    assert prepare is not None
    assert prepare.status == StageStatus.COMPLETED

    assert legacy.status == "failed"
    assert legacy.error_code == "PROCESS_INTERRUPTED"
    assert legacy.completed_at is not None

    # Idempotent re-entry.
    mark_interrupted_runs_failed(session)
    session.refresh(staged)
    session.refresh(legacy)
    assert staged.status == RunStatus.INTERRUPTED
    assert legacy.status == "failed"

    session.close()
    engine.dispose()


def test_sqlite_fk_and_integrity(tmp_path) -> None:
    engine = _engine(tmp_path, "fk.db")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1

    session = _session(engine)
    book = _seed_book(session, suffix="-fk")
    snap = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.execute(
                text(
                    "INSERT INTO book_snapshots "
                    "(book_id, content_hash, chapter_count, paragraph_count, "
                    "character_count, snapshot_status, source_fingerprint, created_at) "
                    "VALUES (:bid, :ch, 0, 0, 0, 'building', '', '2026-01-01')"
                ),
                {"bid": book.id, "ch": snap.content_hash},
            )
    session.close()
    engine.dispose()
