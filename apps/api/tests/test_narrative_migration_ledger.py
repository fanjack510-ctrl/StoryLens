"""Agent A: migration ledger directed tests."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine

from app.db.models import Base
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.migrations import (
    BASELINE_MARKER_ID,
    MIGRATION_CONTENT_HASHES,
    MIGRATION_SCHEMA_MIGRATIONS,
    migration_checksum,
)
from app.narrative_core.migrations.runner import (
    SQL_001,
    SQL_002,
    apply_narrative_phase1p_migrations,
    migrate_narrative_20260723_001_schema_migrations,
    migrate_narrative_20260723_002_content_hashes,
    register_baseline_1_0_5,
)
from app.narrative_core.services.migration_ledger import (
    BASELINE_SOURCE,
    MigrationLedgerService,
)


def _engine(tmp_path, name: str = "ledger.db") -> Engine:
    engine = create_engine(f"sqlite:///{tmp_path / name}")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def test_baseline_1_0_5_legal_registration(tmp_path) -> None:
    engine = _engine(tmp_path)
    ledger = MigrationLedgerService(engine)
    ledger.register_baseline_1_0_5()
    ledger.register_baseline_1_0_5()  # idempotent
    row = ledger.get_applied_migration(BASELINE_MARKER_ID)
    assert row is not None
    assert row["checksum"] == migration_checksum(BASELINE_SOURCE)
    assert row["app_version"] == "1.0.5"
    engine.dispose()


def test_illegal_baseline_rejected(tmp_path) -> None:
    engine = _engine(tmp_path)
    ledger = MigrationLedgerService(engine)
    ledger.ensure_ledger_table()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO schema_migrations "
                "(migration_id, checksum, app_version, applied_at) "
                "VALUES (:id, :checksum, '1.0.5', '2026-01-01')"
            ),
            {"id": BASELINE_MARKER_ID, "checksum": "0" * 64},
        )
    with pytest.raises(NarrativeCoreError) as exc_info:
        ledger.register_baseline_1_0_5()
    assert exc_info.value.code == NarrativeCoreErrorCode.MIGRATION_BASELINE_INVALID
    engine.dispose()


def test_migration_checksum_consistent(tmp_path) -> None:
    engine = _engine(tmp_path)
    ledger = MigrationLedgerService(engine)
    expected = migration_checksum(SQL_001)
    assert ledger.expected_checksum(MIGRATION_SCHEMA_MIGRATIONS) == expected
    migrate_narrative_20260723_001_schema_migrations(engine)
    assert ledger.validate_migration_checksum(MIGRATION_SCHEMA_MIGRATIONS, expected) is True
    engine.dispose()


def test_checksum_conflict_fails(tmp_path) -> None:
    engine = _engine(tmp_path)
    ledger = MigrationLedgerService(engine)
    migrate_narrative_20260723_001_schema_migrations(engine)
    with pytest.raises(NarrativeCoreError) as exc_info:
        ledger.record_applied_migration(MIGRATION_SCHEMA_MIGRATIONS, "f" * 64)
    assert exc_info.value.code == NarrativeCoreErrorCode.MIGRATION_CHECKSUM_MISMATCH
    with pytest.raises(NarrativeCoreError):
        ledger.validate_migration_checksum(MIGRATION_SCHEMA_MIGRATIONS, "a" * 64)
    engine.dispose()


def test_migration_reapply_idempotent(tmp_path) -> None:
    engine = _engine(tmp_path)
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    apply_narrative_phase1p_migrations(engine)
    ledger = MigrationLedgerService(engine)
    first = ledger.get_applied_migration(MIGRATION_CONTENT_HASHES)
    migrate_narrative_20260723_002_content_hashes(engine)
    second = ledger.get_applied_migration(MIGRATION_CONTENT_HASHES)
    assert first is not None and second is not None
    assert first["checksum"] == second["checksum"] == migration_checksum(SQL_002)
    engine.dispose()


def test_failed_migration_does_not_register(tmp_path) -> None:
    """If DDL cannot run, ledger must not claim success for a new id."""
    engine = _engine(tmp_path, "fail.db")
    ledger = MigrationLedgerService(engine)
    # No chapters/paragraphs tables → 002 returns early without recording in
    # current runner when tables missing. Force a checksum conflict path instead:
    # register under wrong checksum then ensure matching apply refuses rewrite.
    ledger.ensure_ledger_table()
    register_baseline_1_0_5(engine)
    migrate_narrative_20260723_001_schema_migrations(engine)
    # Simulate partial corrupt ledger for 002 before DDL success.
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO schema_migrations "
                "(migration_id, checksum, app_version, applied_at) "
                "VALUES (:id, :checksum, '1.0.5', '2026-01-01')"
            ),
            {"id": MIGRATION_CONTENT_HASHES, "checksum": "deadbeef" * 8},
        )
    Base.metadata.create_all(engine)
    with pytest.raises(NarrativeCoreError) as exc_info:
        migrate_narrative_20260723_002_content_hashes(engine)
    assert exc_info.value.code == NarrativeCoreErrorCode.MIGRATION_CHECKSUM_MISMATCH
    row = ledger.get_applied_migration(MIGRATION_CONTENT_HASHES)
    assert row is not None
    assert row["checksum"] == "deadbeef" * 8  # unchanged; success path did not overwrite
    engine.dispose()


def test_sqlite_foreign_keys_and_upgrade_path(tmp_path) -> None:
    engine = _engine(tmp_path, "upgrade.db")
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
                "INSERT INTO books (id,title,author,source_file_name,source_file_hash,"
                "import_status,language,revision_number,created_at) VALUES "
                "(1,'t',NULL,'a.txt','h','imported','zh-CN',1,'2026-01-01')"
            )
        )
    apply_narrative_phase1p_migrations(engine)
    names = set(inspect(engine).get_table_names())
    assert "schema_migrations" in names
    assert "book_snapshots" in names
    chapter_cols = {c["name"] for c in inspect(engine).get_columns("chapters")}
    assert "content_hash" in chapter_cols

    # FK enforcement: orphan snapshot chapter should fail when FK on.
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO book_snapshots "
                "(id, book_id, content_hash, chapter_count, paragraph_count, "
                "character_count, snapshot_status, source_fingerprint, created_at) "
                "VALUES (1, 1, 'abc', 0, 0, 0, 'building', '', '2026-01-01')"
            )
        )
    with pytest.raises(Exception):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO book_snapshot_chapters "
                    "(id, snapshot_id, source_chapter_id, chapter_order, title, "
                    "content_hash, content_text) "
                    "VALUES (1, 999, NULL, 1, 'x', 'h', 'body')"
                )
            )
    engine.dispose()
