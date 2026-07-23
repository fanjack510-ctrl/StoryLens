"""Idempotent Phase 1P narrative schema migrations.

Creates minimum shared skeleton only. Does not backfill hashes or build snapshots.
Checksums are derived from each migration's SQL body constant.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.migrations import (
    BASELINE_MARKER_ID,
    MIGRATION_ANALYSIS_RUN_SCOPE,
    MIGRATION_ANALYSIS_RUN_STAGES,
    MIGRATION_BOOK_SNAPSHOTS,
    MIGRATION_CONTENT_HASHES,
    MIGRATION_SCHEMA_MIGRATIONS,
    migration_checksum,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _table_names(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _column_names(engine: Engine, table: str) -> set[str]:
    if table not in _table_names(engine):
        return set()
    return {column["name"] for column in inspect(engine).get_columns(table)}


def _ensure_schema_migrations_table(engine: Engine) -> None:
    if "schema_migrations" in _table_names(engine):
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE schema_migrations (
                    migration_id VARCHAR(128) NOT NULL PRIMARY KEY,
                    checksum VARCHAR(64) NOT NULL,
                    app_version VARCHAR(32) NOT NULL,
                    applied_at DATETIME NOT NULL
                )
                """
            )
        )


def _get_applied_checksum(engine: Engine, migration_id: str) -> str | None:
    if "schema_migrations" not in _table_names(engine):
        return None
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT checksum FROM schema_migrations WHERE migration_id = :migration_id"
            ),
            {"migration_id": migration_id},
        ).fetchone()
    return None if row is None else str(row[0])


def _record_applied(engine: Engine, migration_id: str, checksum: str) -> None:
    existing = _get_applied_checksum(engine, migration_id)
    if existing is not None:
        if existing != checksum:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.MIGRATION_CHECKSUM_MISMATCH,
                f"{migration_id} stored={existing} expected={checksum}",
            )
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO schema_migrations (migration_id, checksum, app_version, applied_at)
                VALUES (:migration_id, :checksum, :app_version, :applied_at)
                """
            ),
            {
                "migration_id": migration_id,
                "checksum": checksum,
                "app_version": "1.0.5",
                "applied_at": _utc_now_iso(),
            },
        )


def register_baseline_1_0_5(engine: Engine) -> None:
    """Mark that this database is evolving from the 1.0.5 product baseline."""
    _ensure_schema_migrations_table(engine)
    marker_source = "StoryLens baseline 1.0.5 narrative phase1 prelude"
    checksum = migration_checksum(marker_source)
    existing = _get_applied_checksum(engine, BASELINE_MARKER_ID)
    if existing is not None:
        if existing != checksum:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.MIGRATION_BASELINE_INVALID,
                "baseline_1_0_5 checksum mismatch",
            )
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO schema_migrations (migration_id, checksum, app_version, applied_at)
                VALUES (:migration_id, :checksum, :app_version, :applied_at)
                """
            ),
            {
                "migration_id": BASELINE_MARKER_ID,
                "checksum": checksum,
                "app_version": "1.0.5",
                "applied_at": _utc_now_iso(),
            },
        )


SQL_001 = """
CREATE TABLE schema_migrations (
    migration_id VARCHAR(128) NOT NULL PRIMARY KEY,
    checksum VARCHAR(64) NOT NULL,
    app_version VARCHAR(32) NOT NULL,
    applied_at DATETIME NOT NULL
)
"""

SQL_002 = """
ALTER TABLE chapters ADD COLUMN content_hash VARCHAR(64);
ALTER TABLE paragraphs ADD COLUMN content_hash VARCHAR(64);
CREATE INDEX IF NOT EXISTS ix_chapters_content_hash ON chapters (content_hash);
CREATE INDEX IF NOT EXISTS ix_paragraphs_content_hash ON paragraphs (content_hash);
"""

SQL_003 = """
CREATE TABLE book_snapshots (
    id INTEGER NOT NULL PRIMARY KEY,
    book_id INTEGER NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    chapter_count INTEGER NOT NULL DEFAULT 0,
    paragraph_count INTEGER NOT NULL DEFAULT 0,
    character_count INTEGER NOT NULL DEFAULT 0,
    snapshot_status VARCHAR(32) NOT NULL DEFAULT 'building',
    source_fingerprint VARCHAR(64) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL,
    FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE,
    UNIQUE (book_id, content_hash)
);
CREATE TABLE book_snapshot_chapters (
    id INTEGER NOT NULL PRIMARY KEY,
    snapshot_id INTEGER NOT NULL,
    source_chapter_id INTEGER,
    chapter_order INTEGER NOT NULL,
    title VARCHAR(600) NOT NULL DEFAULT '',
    content_hash VARCHAR(64) NOT NULL,
    content_text TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(snapshot_id) REFERENCES book_snapshots (id) ON DELETE CASCADE,
    FOREIGN KEY(source_chapter_id) REFERENCES chapters (id) ON DELETE SET NULL,
    UNIQUE (snapshot_id, chapter_order),
    UNIQUE (snapshot_id, source_chapter_id)
);
CREATE TABLE book_snapshot_paragraphs (
    id INTEGER NOT NULL PRIMARY KEY,
    snapshot_id INTEGER NOT NULL,
    snapshot_chapter_id INTEGER NOT NULL,
    source_paragraph_id VARCHAR(32),
    stable_paragraph_id VARCHAR(32) NOT NULL,
    paragraph_order INTEGER NOT NULL,
    start_offset INTEGER NOT NULL DEFAULT 0,
    end_offset INTEGER NOT NULL DEFAULT 0,
    content_hash VARCHAR(64) NOT NULL,
    FOREIGN KEY(snapshot_id) REFERENCES book_snapshots (id) ON DELETE CASCADE,
    FOREIGN KEY(snapshot_chapter_id) REFERENCES book_snapshot_chapters (id) ON DELETE CASCADE,
    UNIQUE (snapshot_chapter_id, paragraph_order),
    CHECK (start_offset >= 0),
    CHECK (end_offset >= start_offset)
);
"""

SQL_004 = """
ALTER TABLE analysis_runs ADD COLUMN analysis_type VARCHAR(64);
ALTER TABLE analysis_runs ADD COLUMN scope_type VARCHAR(32);
ALTER TABLE analysis_runs ADD COLUMN book_id INTEGER REFERENCES books(id) ON DELETE SET NULL;
ALTER TABLE analysis_runs ADD COLUMN start_chapter_id INTEGER REFERENCES chapters(id) ON DELETE SET NULL;
ALTER TABLE analysis_runs ADD COLUMN end_chapter_id INTEGER REFERENCES chapters(id) ON DELETE SET NULL;
ALTER TABLE analysis_runs ADD COLUMN book_snapshot_id INTEGER REFERENCES book_snapshots(id) ON DELETE SET NULL;
ALTER TABLE analysis_runs ADD COLUMN configuration_fingerprint VARCHAR(64);
CREATE INDEX IF NOT EXISTS ix_analysis_runs_analysis_type ON analysis_runs (analysis_type);
CREATE INDEX IF NOT EXISTS ix_analysis_runs_scope_type ON analysis_runs (scope_type);
CREATE INDEX IF NOT EXISTS ix_analysis_runs_book_id ON analysis_runs (book_id);
CREATE INDEX IF NOT EXISTS ix_analysis_runs_book_snapshot_id ON analysis_runs (book_snapshot_id);
"""

SQL_005 = """
CREATE TABLE analysis_run_stages (
    id INTEGER NOT NULL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    stage_key VARCHAR(64) NOT NULL,
    stage_order INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    input_fingerprint VARCHAR(64) NOT NULL DEFAULT '',
    output_artifact_id INTEGER,
    checkpoint_json TEXT NOT NULL DEFAULT '{}',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    token_input INTEGER NOT NULL DEFAULT 0,
    token_output INTEGER NOT NULL DEFAULT 0,
    cost FLOAT NOT NULL DEFAULT 0,
    started_at DATETIME,
    completed_at DATETIME,
    error_code VARCHAR(100),
    error_message TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE CASCADE,
    FOREIGN KEY(output_artifact_id) REFERENCES analysis_artifacts (id) ON DELETE SET NULL,
    UNIQUE (run_id, stage_key),
    CHECK (stage_order >= 0),
    CHECK (attempt_count >= 0)
);
CREATE INDEX IF NOT EXISTS ix_analysis_run_stages_run_id ON analysis_run_stages (run_id);
CREATE INDEX IF NOT EXISTS ix_analysis_run_stages_status ON analysis_run_stages (status);
CREATE INDEX IF NOT EXISTS ix_analysis_run_stages_run_order ON analysis_run_stages (run_id, stage_order);
"""


def migrate_narrative_20260723_001_schema_migrations(engine: Engine) -> None:
    checksum = migration_checksum(SQL_001)
    _ensure_schema_migrations_table(engine)
    _record_applied(engine, MIGRATION_SCHEMA_MIGRATIONS, checksum)


def migrate_narrative_20260723_002_content_hashes(engine: Engine) -> None:
    checksum = migration_checksum(SQL_002)
    names = _table_names(engine)
    if "chapters" not in names or "paragraphs" not in names:
        return
    if "content_hash" not in _column_names(engine, "chapters"):
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE chapters ADD COLUMN content_hash VARCHAR(64)"))
    if "content_hash" not in _column_names(engine, "paragraphs"):
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE paragraphs ADD COLUMN content_hash VARCHAR(64)"))
    with engine.begin() as connection:
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_chapters_content_hash ON chapters (content_hash)")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_paragraphs_content_hash ON paragraphs (content_hash)"
            )
        )
    _ensure_schema_migrations_table(engine)
    _record_applied(engine, MIGRATION_CONTENT_HASHES, checksum)


def migrate_narrative_20260723_003_book_snapshots(engine: Engine) -> None:
    checksum = migration_checksum(SQL_003)
    names = _table_names(engine)
    with engine.begin() as connection:
        if "book_snapshots" not in names:
            connection.execute(
                text(
                    """
                    CREATE TABLE book_snapshots (
                        id INTEGER NOT NULL PRIMARY KEY,
                        book_id INTEGER NOT NULL,
                        content_hash VARCHAR(64) NOT NULL,
                        chapter_count INTEGER NOT NULL DEFAULT 0,
                        paragraph_count INTEGER NOT NULL DEFAULT 0,
                        character_count INTEGER NOT NULL DEFAULT 0,
                        snapshot_status VARCHAR(32) NOT NULL DEFAULT 'building',
                        source_fingerprint VARCHAR(64) NOT NULL DEFAULT '',
                        created_at DATETIME NOT NULL,
                        FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE,
                        UNIQUE (book_id, content_hash)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_book_snapshots_book_id "
                    "ON book_snapshots (book_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_book_snapshots_content_hash "
                    "ON book_snapshots (content_hash)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_book_snapshots_book_status "
                    "ON book_snapshots (book_id, snapshot_status)"
                )
            )
        if "book_snapshot_chapters" not in names:
            connection.execute(
                text(
                    """
                    CREATE TABLE book_snapshot_chapters (
                        id INTEGER NOT NULL PRIMARY KEY,
                        snapshot_id INTEGER NOT NULL,
                        source_chapter_id INTEGER,
                        chapter_order INTEGER NOT NULL,
                        title VARCHAR(600) NOT NULL DEFAULT '',
                        content_hash VARCHAR(64) NOT NULL,
                        content_text TEXT NOT NULL DEFAULT '',
                        FOREIGN KEY(snapshot_id) REFERENCES book_snapshots (id) ON DELETE CASCADE,
                        FOREIGN KEY(source_chapter_id) REFERENCES chapters (id) ON DELETE SET NULL,
                        UNIQUE (snapshot_id, chapter_order),
                        UNIQUE (snapshot_id, source_chapter_id)
                    )
                    """
                )
            )
        if "book_snapshot_paragraphs" not in names:
            connection.execute(
                text(
                    """
                    CREATE TABLE book_snapshot_paragraphs (
                        id INTEGER NOT NULL PRIMARY KEY,
                        snapshot_id INTEGER NOT NULL,
                        snapshot_chapter_id INTEGER NOT NULL,
                        source_paragraph_id VARCHAR(32),
                        stable_paragraph_id VARCHAR(32) NOT NULL,
                        paragraph_order INTEGER NOT NULL,
                        start_offset INTEGER NOT NULL DEFAULT 0,
                        end_offset INTEGER NOT NULL DEFAULT 0,
                        content_hash VARCHAR(64) NOT NULL,
                        FOREIGN KEY(snapshot_id) REFERENCES book_snapshots (id) ON DELETE CASCADE,
                        FOREIGN KEY(snapshot_chapter_id)
                            REFERENCES book_snapshot_chapters (id) ON DELETE CASCADE,
                        UNIQUE (snapshot_chapter_id, paragraph_order),
                        CHECK (start_offset >= 0),
                        CHECK (end_offset >= start_offset)
                    )
                    """
                )
            )
    _ensure_schema_migrations_table(engine)
    _record_applied(engine, MIGRATION_BOOK_SNAPSHOTS, checksum)


def migrate_narrative_20260723_004_analysis_run_scope(engine: Engine) -> None:
    checksum = migration_checksum(SQL_004)
    if "analysis_runs" not in _table_names(engine):
        return
    if "book_snapshots" not in _table_names(engine):
        # Scope FK target must exist; 003 runs first in apply_narrative_phase1p_migrations.
        migrate_narrative_20260723_003_book_snapshots(engine)
    existing = _column_names(engine, "analysis_runs")
    additions = {
        "analysis_type": "VARCHAR(64)",
        "scope_type": "VARCHAR(32)",
        "book_id": "INTEGER REFERENCES books(id) ON DELETE SET NULL",
        "start_chapter_id": "INTEGER REFERENCES chapters(id) ON DELETE SET NULL",
        "end_chapter_id": "INTEGER REFERENCES chapters(id) ON DELETE SET NULL",
        "book_snapshot_id": "INTEGER REFERENCES book_snapshots(id) ON DELETE SET NULL",
        "configuration_fingerprint": "VARCHAR(64)",
    }
    with engine.begin() as connection:
        for name, ddl in additions.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE analysis_runs ADD COLUMN {name} {ddl}"))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_analysis_runs_analysis_type "
                "ON analysis_runs (analysis_type)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_analysis_runs_scope_type "
                "ON analysis_runs (scope_type)"
            )
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_analysis_runs_book_id ON analysis_runs (book_id)")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_analysis_runs_book_snapshot_id "
                "ON analysis_runs (book_snapshot_id)"
            )
        )
    _ensure_schema_migrations_table(engine)
    _record_applied(engine, MIGRATION_ANALYSIS_RUN_SCOPE, checksum)


def migrate_narrative_20260723_005_analysis_run_stages(engine: Engine) -> None:
    checksum = migration_checksum(SQL_005)
    if "analysis_run_stages" not in _table_names(engine):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE analysis_run_stages (
                        id INTEGER NOT NULL PRIMARY KEY,
                        run_id INTEGER NOT NULL,
                        stage_key VARCHAR(64) NOT NULL,
                        stage_order INTEGER NOT NULL DEFAULT 0,
                        status VARCHAR(32) NOT NULL DEFAULT 'pending',
                        input_fingerprint VARCHAR(64) NOT NULL DEFAULT '',
                        output_artifact_id INTEGER,
                        checkpoint_json TEXT NOT NULL DEFAULT '{}',
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        token_input INTEGER NOT NULL DEFAULT 0,
                        token_output INTEGER NOT NULL DEFAULT 0,
                        cost FLOAT NOT NULL DEFAULT 0,
                        started_at DATETIME,
                        completed_at DATETIME,
                        error_code VARCHAR(100),
                        error_message TEXT,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE CASCADE,
                        FOREIGN KEY(output_artifact_id)
                            REFERENCES analysis_artifacts (id) ON DELETE SET NULL,
                        UNIQUE (run_id, stage_key),
                        CHECK (stage_order >= 0),
                        CHECK (attempt_count >= 0)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_analysis_run_stages_run_id "
                    "ON analysis_run_stages (run_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_analysis_run_stages_status "
                    "ON analysis_run_stages (status)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_analysis_run_stages_run_order "
                    "ON analysis_run_stages (run_id, stage_order)"
                )
            )
    _ensure_schema_migrations_table(engine)
    _record_applied(engine, MIGRATION_ANALYSIS_RUN_STAGES, checksum)


def apply_narrative_phase1p_migrations(engine: Engine) -> None:
    """Apply Phase 1P shared skeleton migrations in frozen order."""
    register_baseline_1_0_5(engine)
    migrate_narrative_20260723_001_schema_migrations(engine)
    migrate_narrative_20260723_002_content_hashes(engine)
    migrate_narrative_20260723_003_book_snapshots(engine)
    migrate_narrative_20260723_004_analysis_run_scope(engine)
    migrate_narrative_20260723_005_analysis_run_stages(engine)
