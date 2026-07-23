"""Phase 1P contract verification tests (local, not full suite)."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from app.db.models import Base
from app.narrative_core.enums import AnalysisScopeType, AnalysisType, SnapshotStatus, StageStatus
from app.narrative_core.hash_canon import calculate_text_hash, canonicalize_text
from app.narrative_core.migrations import NARRATIVE_MIGRATION_ORDER, assert_unique_migration_ids
from app.narrative_core.migrations.runner import apply_narrative_phase1p_migrations
from app.narrative_core.stage_transitions import (
    ALLOWED_STAGE_TRANSITIONS,
    is_allowed_stage_transition,
)


def test_migration_ids_are_unique() -> None:
    assert_unique_migration_ids()
    assert len(NARRATIVE_MIGRATION_ORDER) == 5


def test_orm_table_names_unique() -> None:
    names = [table.name for table in Base.metadata.sorted_tables]
    assert len(names) == len(set(names))
    for required in (
        "schema_migrations",
        "book_snapshots",
        "book_snapshot_chapters",
        "book_snapshot_paragraphs",
        "analysis_run_stages",
    ):
        assert required in names


def test_create_all_on_empty_temp_db(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    apply_narrative_phase1p_migrations(engine)  # idempotent
    names = set(inspect(engine).get_table_names())
    assert "schema_migrations" in names
    assert "book_snapshots" in names
    assert "analysis_run_stages" in names
    chapter_cols = {c["name"] for c in inspect(engine).get_columns("chapters")}
    paragraph_cols = {c["name"] for c in inspect(engine).get_columns("paragraphs")}
    run_cols = {c["name"] for c in inspect(engine).get_columns("analysis_runs")}
    assert "content_hash" in chapter_cols
    assert "content_hash" in paragraph_cols
    assert {
        "analysis_type",
        "scope_type",
        "book_id",
        "start_chapter_id",
        "end_chapter_id",
        "book_snapshot_id",
        "configuration_fingerprint",
    } <= run_cols


def test_upgrade_from_simulated_1_0_5_preserves_old_run(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
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
                    import_status VARCHAR(32) NOT NULL,
                    language VARCHAR(32) NOT NULL,
                    revision_number INTEGER NOT NULL,
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
                    word_count INTEGER NOT NULL,
                    section_type VARCHAR(32) NOT NULL,
                    chapter_title VARCHAR(500) NOT NULL,
                    display_title VARCHAR(600) NOT NULL,
                    source_title_line VARCHAR(600) NOT NULL,
                    FOREIGN KEY(book_id) REFERENCES books(id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE paragraphs (
                    id VARCHAR(32) PRIMARY KEY,
                    book_id INTEGER NOT NULL,
                    chapter_id INTEGER NOT NULL,
                    paragraph_index INTEGER NOT NULL,
                    raw_text TEXT NOT NULL,
                    normalized_text TEXT NOT NULL,
                    char_start INTEGER NOT NULL,
                    char_end INTEGER NOT NULL
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
                    prompt_hash VARCHAR(64) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    progress_current INTEGER NOT NULL,
                    progress_total INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    queued_at DATETIME NOT NULL,
                    started_at DATETIME NOT NULL,
                    execution_mode VARCHAR(16) NOT NULL,
                    analysis_mode VARCHAR(40) NOT NULL,
                    cloud_consent INTEGER NOT NULL,
                    sends_content_to_cloud INTEGER NOT NULL,
                    retryable INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE analysis_artifacts (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER NOT NULL,
                    artifact_type VARCHAR(50) NOT NULL,
                    subject_type VARCHAR(50) NOT NULL,
                    subject_id VARCHAR(100) NOT NULL,
                    schema_version VARCHAR(50) NOT NULL,
                    prompt_version VARCHAR(50) NOT NULL,
                    payload_json TEXT NOT NULL,
                    confidence FLOAT NOT NULL,
                    validation_status VARCHAR(32) NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO analysis_runs ("
                "id,task_type,subject_type,subject_id,provider,model,prompt_version,"
                "schema_version,input_hash,prompt_hash,status,progress_current,progress_total,"
                "created_at,queued_at,started_at,execution_mode,analysis_mode,"
                "cloud_consent,sends_content_to_cloud,retryable"
                ") VALUES ("
                "42,'scene_pipeline','chapter','7','local','m','v1','v1','h','p',"
                "'completed',1,1,'2026-01-01','2026-01-01','2026-01-01','local',"
                "'automatic',0,0,0)"
            )
        )
    apply_narrative_phase1p_migrations(engine)
    apply_narrative_phase1p_migrations(engine)
    run_cols = {c["name"] for c in inspect(engine).get_columns("analysis_runs")}
    assert "scope_type" in run_cols
    assert "book_snapshot_id" in run_cols
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT subject_type, subject_id, status, scope_type, analysis_type, "
                "book_snapshot_id FROM analysis_runs WHERE id = 42"
            )
        ).fetchone()
    assert row is not None
    assert row[0] == "chapter"
    assert row[1] == "7"
    assert row[2] == "completed"
    assert row[3] is None
    assert row[4] is None
    assert row[5] is None
    assert "book_snapshots" in inspect(engine).get_table_names()
    assert "analysis_run_stages" in inspect(engine).get_table_names()


def test_scope_and_stage_enums() -> None:
    assert AnalysisScopeType.CHAPTER == "chapter"
    assert AnalysisScopeType.CHAPTER_RANGE == "chapter_range"
    assert AnalysisScopeType.BOOK == "book"
    assert SnapshotStatus.INVALID == "invalid"
    assert AnalysisType.WHOLE_BOOK_NATIVE == "whole_book_native"
    assert {s.value for s in StageStatus} >= {
        "pending",
        "running",
        "paused",
        "interrupted",
        "completed",
        "failed",
        "skipped",
        "cancelled",
    }


def test_stage_transition_matrix() -> None:
    assert is_allowed_stage_transition("pending", "running")
    assert is_allowed_stage_transition("running", "paused")
    assert is_allowed_stage_transition("failed", "running")
    assert not is_allowed_stage_transition("completed", "running")
    assert not is_allowed_stage_transition("skipped", "running")
    assert not is_allowed_stage_transition("cancelled", "pending")
    assert ALLOWED_STAGE_TRANSITIONS[StageStatus.COMPLETED] == frozenset()


def test_canonicalize_and_hash_stability() -> None:
    mixed = "a\r\nb\rc\n"
    assert canonicalize_text(mixed) == "a\nb\nc\n"
    assert calculate_text_hash("hello\r\n") == calculate_text_hash("hello\n")
    digest = calculate_text_hash("StoryLens")
    assert len(digest) == 64
    assert digest == calculate_text_hash("StoryLens")
    # Unicode: no NFC forced — composed vs decomposed remain distinct if different bytes.
    assert calculate_text_hash("café") == calculate_text_hash("café")


def test_protocol_modules_importable() -> None:
    from app.narrative_core.contracts import (
        AnalysisRunService,
        BookSnapshotRepository,
        ContentHashService,
        MigrationLedger,
        SnapshotValidationGateway,
    )

    assert MigrationLedger is not None
    assert ContentHashService is not None
    assert BookSnapshotRepository is not None
    assert SnapshotValidationGateway is not None
    assert AnalysisRunService is not None
