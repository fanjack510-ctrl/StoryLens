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
    MIGRATION_ANALYSIS_CONFLICTS,
    MIGRATION_ANALYSIS_RUN_SCOPE,
    MIGRATION_ANALYSIS_RUN_STAGES,
    MIGRATION_BOOK_SNAPSHOTS,
    MIGRATION_CONTENT_HASHES,
    MIGRATION_NARRATIVE_ASSET_EVIDENCE,
    MIGRATION_NARRATIVE_ASSETS_VERSIONS,
    MIGRATION_NARRATIVE_ENTITIES_ALIASES,
    MIGRATION_NARRATIVE_RELATIONS_VERSIONS_EVIDENCE,
    MIGRATION_SCHEMA_MIGRATIONS,
    MIGRATION_WHOLE_BOOK_FOUNDATION_V1,
    MIGRATION_WHOLE_BOOK_OVERVIEW_RUNTIME,
    MIGRATION_WHOLE_BOOK_SNAPSHOT_IMMUTABILITY,
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
    error_code VARCHAR(100),
    error_message TEXT,
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
                        error_code VARCHAR(100),
                        error_message TEXT,
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
        else:
            # Phase 1A pre-release schema correction: add dedicated error columns
            # without a new migration_id. Idempotent ADD COLUMN.
            rows = connection.execute(text("PRAGMA table_info(book_snapshots)")).fetchall()
            existing_cols = {str(row[1]) for row in rows}
            if "error_code" not in existing_cols:
                connection.execute(
                    text("ALTER TABLE book_snapshots ADD COLUMN error_code VARCHAR(100)")
                )
            if "error_message" not in existing_cols:
                connection.execute(
                    text("ALTER TABLE book_snapshots ADD COLUMN error_message TEXT")
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
    """Apply Phase 1P shared skeleton migrations in frozen order (001–005)."""
    register_baseline_1_0_5(engine)
    migrate_narrative_20260723_001_schema_migrations(engine)
    migrate_narrative_20260723_002_content_hashes(engine)
    migrate_narrative_20260723_003_book_snapshots(engine)
    migrate_narrative_20260723_004_analysis_run_scope(engine)
    migrate_narrative_20260723_005_analysis_run_stages(engine)


# ---------------------------------------------------------------------------
# Phase 1B-P — Migration DDL skeleton (006–010). Checksum = SQL_* body.
# Agent D owns 006 refinements; Agent E owns 007–008; Agent F owns 009–010.
# Do not renumber; do not insert migrations between these IDs.
# ---------------------------------------------------------------------------

SQL_006 = """
CREATE TABLE narrative_entities (
    id INTEGER NOT NULL PRIMARY KEY,
    book_id INTEGER NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    canonical_name VARCHAR(500) NOT NULL,
    normalized_name VARCHAR(500) NOT NULL,
    lifecycle_status VARCHAR(32) NOT NULL DEFAULT 'active',
    is_locked INTEGER NOT NULL DEFAULT 0,
    locked_at DATETIME,
    superseded_by_entity_id INTEGER,
    created_by VARCHAR(64),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE,
    FOREIGN KEY(superseded_by_entity_id) REFERENCES narrative_entities (id) ON DELETE SET NULL
);
CREATE TABLE narrative_entity_aliases (
    id INTEGER NOT NULL PRIMARY KEY,
    entity_id INTEGER NOT NULL,
    alias_text VARCHAR(500) NOT NULL,
    normalized_alias VARCHAR(500) NOT NULL,
    alias_type VARCHAR(32) NOT NULL DEFAULT 'display',
    source_run_id INTEGER,
    source_snapshot_id INTEGER,
    review_status VARCHAR(32) NOT NULL DEFAULT 'candidate',
    is_locked INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(entity_id) REFERENCES narrative_entities (id) ON DELETE CASCADE,
    FOREIGN KEY(source_run_id) REFERENCES analysis_runs (id) ON DELETE SET NULL,
    FOREIGN KEY(source_snapshot_id) REFERENCES book_snapshots (id) ON DELETE SET NULL,
    UNIQUE (entity_id, normalized_alias)
);
"""

SQL_007 = """
CREATE TABLE narrative_assets (
    id INTEGER NOT NULL PRIMARY KEY,
    book_id INTEGER NOT NULL,
    asset_key VARCHAR(128) NOT NULL,
    lifecycle_status VARCHAR(32) NOT NULL DEFAULT 'active',
    is_locked INTEGER NOT NULL DEFAULT 0,
    locked_at DATETIME,
    superseded_by_asset_id INTEGER,
    stale_at DATETIME,
    stale_reason TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE,
    FOREIGN KEY(superseded_by_asset_id) REFERENCES narrative_assets (id) ON DELETE SET NULL,
    UNIQUE (book_id, asset_key)
);
CREATE TABLE narrative_asset_versions (
    id INTEGER NOT NULL PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    run_id INTEGER,
    book_snapshot_id INTEGER,
    asset_type VARCHAR(64) NOT NULL,
    title VARCHAR(500) NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    narrative_function TEXT NOT NULL DEFAULT '',
    attributes_json TEXT NOT NULL DEFAULT '{}',
    confidence FLOAT NOT NULL DEFAULT 0,
    importance FLOAT NOT NULL DEFAULT 0,
    source_fingerprint VARCHAR(64) NOT NULL DEFAULT '',
    origin_type VARCHAR(32) NOT NULL DEFAULT 'model',
    review_status VARCHAR(32) NOT NULL DEFAULT 'candidate',
    is_canonical INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    FOREIGN KEY(asset_id) REFERENCES narrative_assets (id) ON DELETE CASCADE,
    FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE SET NULL,
    FOREIGN KEY(book_snapshot_id) REFERENCES book_snapshots (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX uq_narrative_asset_versions_one_canonical
    ON narrative_asset_versions (asset_id) WHERE is_canonical = 1;
"""

SQL_008 = """
CREATE TABLE narrative_asset_evidence (
    id INTEGER NOT NULL PRIMARY KEY,
    asset_version_id INTEGER NOT NULL,
    book_snapshot_id INTEGER NOT NULL,
    snapshot_chapter_id INTEGER NOT NULL,
    snapshot_paragraph_id INTEGER NOT NULL,
    source_scene_id INTEGER,
    paragraph_content_hash VARCHAR(64) NOT NULL,
    start_offset INTEGER NOT NULL DEFAULT 0,
    end_offset INTEGER NOT NULL DEFAULT 0,
    evidence_role VARCHAR(32) NOT NULL DEFAULT 'support',
    evidence_label VARCHAR(500) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL,
    FOREIGN KEY(asset_version_id) REFERENCES narrative_asset_versions (id) ON DELETE CASCADE,
    FOREIGN KEY(book_snapshot_id) REFERENCES book_snapshots (id) ON DELETE CASCADE,
    FOREIGN KEY(snapshot_chapter_id) REFERENCES book_snapshot_chapters (id) ON DELETE CASCADE,
    FOREIGN KEY(snapshot_paragraph_id) REFERENCES book_snapshot_paragraphs (id) ON DELETE CASCADE,
    FOREIGN KEY(source_scene_id) REFERENCES scenes (id) ON DELETE SET NULL,
    CHECK (start_offset >= 0),
    CHECK (end_offset >= start_offset)
);
"""

SQL_009 = """
CREATE TABLE narrative_relations (
    id INTEGER NOT NULL PRIMARY KEY,
    book_id INTEGER NOT NULL,
    source_asset_id INTEGER NOT NULL,
    target_asset_id INTEGER NOT NULL,
    relation_key VARCHAR(128) NOT NULL,
    lifecycle_status VARCHAR(32) NOT NULL DEFAULT 'active',
    is_locked INTEGER NOT NULL DEFAULT 0,
    locked_at DATETIME,
    superseded_by_relation_id INTEGER,
    stale_at DATETIME,
    stale_reason TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE,
    FOREIGN KEY(source_asset_id) REFERENCES narrative_assets (id) ON DELETE CASCADE,
    FOREIGN KEY(target_asset_id) REFERENCES narrative_assets (id) ON DELETE CASCADE,
    FOREIGN KEY(superseded_by_relation_id) REFERENCES narrative_relations (id) ON DELETE SET NULL,
    UNIQUE (book_id, relation_key),
    CHECK (source_asset_id != target_asset_id)
);
CREATE TABLE narrative_relation_versions (
    id INTEGER NOT NULL PRIMARY KEY,
    relation_id INTEGER NOT NULL,
    run_id INTEGER,
    book_snapshot_id INTEGER,
    relation_type VARCHAR(64) NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    attributes_json TEXT NOT NULL DEFAULT '{}',
    confidence FLOAT NOT NULL DEFAULT 0,
    importance FLOAT NOT NULL DEFAULT 0,
    source_fingerprint VARCHAR(64) NOT NULL DEFAULT '',
    origin_type VARCHAR(32) NOT NULL DEFAULT 'model',
    review_status VARCHAR(32) NOT NULL DEFAULT 'candidate',
    is_canonical INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    FOREIGN KEY(relation_id) REFERENCES narrative_relations (id) ON DELETE CASCADE,
    FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE SET NULL,
    FOREIGN KEY(book_snapshot_id) REFERENCES book_snapshots (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX uq_narrative_relation_versions_one_canonical
    ON narrative_relation_versions (relation_id) WHERE is_canonical = 1;
CREATE TABLE narrative_relation_evidence (
    id INTEGER NOT NULL PRIMARY KEY,
    relation_version_id INTEGER NOT NULL,
    book_snapshot_id INTEGER NOT NULL,
    snapshot_chapter_id INTEGER NOT NULL,
    snapshot_paragraph_id INTEGER NOT NULL,
    source_scene_id INTEGER,
    paragraph_content_hash VARCHAR(64) NOT NULL,
    start_offset INTEGER NOT NULL DEFAULT 0,
    end_offset INTEGER NOT NULL DEFAULT 0,
    evidence_role VARCHAR(32) NOT NULL DEFAULT 'support',
    evidence_label VARCHAR(500) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL,
    FOREIGN KEY(relation_version_id) REFERENCES narrative_relation_versions (id) ON DELETE CASCADE,
    FOREIGN KEY(book_snapshot_id) REFERENCES book_snapshots (id) ON DELETE CASCADE,
    FOREIGN KEY(snapshot_chapter_id) REFERENCES book_snapshot_chapters (id) ON DELETE CASCADE,
    FOREIGN KEY(snapshot_paragraph_id) REFERENCES book_snapshot_paragraphs (id) ON DELETE CASCADE,
    FOREIGN KEY(source_scene_id) REFERENCES scenes (id) ON DELETE SET NULL,
    CHECK (start_offset >= 0),
    CHECK (end_offset >= start_offset)
);
"""

SQL_010 = """
CREATE TABLE analysis_conflicts (
    id INTEGER NOT NULL PRIMARY KEY,
    book_id INTEGER NOT NULL,
    run_id INTEGER,
    book_snapshot_id INTEGER,
    conflict_type VARCHAR(64) NOT NULL,
    left_ref_type VARCHAR(64) NOT NULL,
    left_ref_id VARCHAR(64) NOT NULL,
    right_ref_type VARCHAR(64) NOT NULL,
    right_ref_id VARCHAR(64) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    severity VARCHAR(32) NOT NULL DEFAULT 'warning',
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    resolution_json TEXT NOT NULL DEFAULT '{}',
    resolved_by VARCHAR(64),
    resolved_at DATETIME,
    created_at DATETIME NOT NULL,
    FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE,
    FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE SET NULL,
    FOREIGN KEY(book_snapshot_id) REFERENCES book_snapshots (id) ON DELETE SET NULL
);
"""


def _exec_sql_script(engine: Engine, script: str) -> None:
    """Execute multi-statement DDL script (SQLite)."""
    statements = [part.strip() for part in script.split(";") if part.strip()]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_narrative_006_indexes(engine: Engine) -> None:
    """Idempotent indexes for Entity / Alias (safe after create_all or CREATE TABLE)."""
    with engine.begin() as connection:
        for statement in (
            "CREATE INDEX IF NOT EXISTS ix_narrative_entities_book_id "
            "ON narrative_entities (book_id)",
            "CREATE INDEX IF NOT EXISTS ix_narrative_entities_entity_type "
            "ON narrative_entities (entity_type)",
            "CREATE INDEX IF NOT EXISTS ix_narrative_entities_book_type "
            "ON narrative_entities (book_id, entity_type)",
            "CREATE INDEX IF NOT EXISTS ix_narrative_entities_book_normalized "
            "ON narrative_entities (book_id, normalized_name)",
            "CREATE INDEX IF NOT EXISTS ix_narrative_entities_superseded_by_entity_id "
            "ON narrative_entities (superseded_by_entity_id)",
            "CREATE INDEX IF NOT EXISTS ix_narrative_entity_aliases_entity_id "
            "ON narrative_entity_aliases (entity_id)",
            "CREATE INDEX IF NOT EXISTS ix_narrative_entity_aliases_normalized "
            "ON narrative_entity_aliases (normalized_alias)",
            "CREATE INDEX IF NOT EXISTS ix_narrative_entity_aliases_source_run_id "
            "ON narrative_entity_aliases (source_run_id)",
            "CREATE INDEX IF NOT EXISTS ix_narrative_entity_aliases_source_snapshot_id "
            "ON narrative_entity_aliases (source_snapshot_id)",
        ):
            connection.execute(text(statement))


def migrate_narrative_20260723_006_narrative_entities_aliases(engine: Engine) -> None:
    """Agent D: narrative_entities + narrative_entity_aliases.

    Idempotent: skips CREATE when tables already exist (e.g. Base.metadata.create_all),
    always ensures indexes, records ledger checksum only after successful DDL path.
    No historical character/entity backfill.
    """
    checksum = migration_checksum(SQL_006)
    names = _table_names(engine)
    try:
        if "narrative_entities" not in names or "narrative_entity_aliases" not in names:
            # Full script creates both tables; if only one missing, still safe —
            # CREATE TABLE will fail if the other already exists, so create missing
            # pieces individually when partially present.
            if "narrative_entities" not in names and "narrative_entity_aliases" not in names:
                _exec_sql_script(engine, SQL_006)
            else:
                with engine.begin() as connection:
                    if "narrative_entities" not in names:
                        connection.execute(
                            text(
                                """
                                CREATE TABLE narrative_entities (
                                    id INTEGER NOT NULL PRIMARY KEY,
                                    book_id INTEGER NOT NULL,
                                    entity_type VARCHAR(64) NOT NULL,
                                    canonical_name VARCHAR(500) NOT NULL,
                                    normalized_name VARCHAR(500) NOT NULL,
                                    lifecycle_status VARCHAR(32) NOT NULL DEFAULT 'active',
                                    is_locked INTEGER NOT NULL DEFAULT 0,
                                    locked_at DATETIME,
                                    superseded_by_entity_id INTEGER,
                                    created_by VARCHAR(64),
                                    created_at DATETIME NOT NULL,
                                    updated_at DATETIME NOT NULL,
                                    FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE,
                                    FOREIGN KEY(superseded_by_entity_id) REFERENCES narrative_entities (id) ON DELETE SET NULL
                                )
                                """
                            )
                        )
                    if "narrative_entity_aliases" not in names:
                        connection.execute(
                            text(
                                """
                                CREATE TABLE narrative_entity_aliases (
                                    id INTEGER NOT NULL PRIMARY KEY,
                                    entity_id INTEGER NOT NULL,
                                    alias_text VARCHAR(500) NOT NULL,
                                    normalized_alias VARCHAR(500) NOT NULL,
                                    alias_type VARCHAR(32) NOT NULL DEFAULT 'display',
                                    source_run_id INTEGER,
                                    source_snapshot_id INTEGER,
                                    review_status VARCHAR(32) NOT NULL DEFAULT 'candidate',
                                    is_locked INTEGER NOT NULL DEFAULT 0,
                                    created_at DATETIME NOT NULL,
                                    updated_at DATETIME NOT NULL,
                                    FOREIGN KEY(entity_id) REFERENCES narrative_entities (id) ON DELETE CASCADE,
                                    FOREIGN KEY(source_run_id) REFERENCES analysis_runs (id) ON DELETE SET NULL,
                                    FOREIGN KEY(source_snapshot_id) REFERENCES book_snapshots (id) ON DELETE SET NULL,
                                    UNIQUE (entity_id, normalized_alias)
                                )
                                """
                            )
                        )
        # Tables must exist before index / ledger success.
        names_after = _table_names(engine)
        if (
            "narrative_entities" not in names_after
            or "narrative_entity_aliases" not in names_after
        ):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.MIGRATION_BASELINE_INVALID,
                "006 failed: narrative_entities / narrative_entity_aliases missing after DDL",
            )
        required_entity_cols = {
            "id",
            "book_id",
            "entity_type",
            "canonical_name",
            "normalized_name",
            "lifecycle_status",
            "is_locked",
            "locked_at",
            "superseded_by_entity_id",
            "created_by",
            "created_at",
            "updated_at",
        }
        required_alias_cols = {
            "id",
            "entity_id",
            "alias_text",
            "normalized_alias",
            "alias_type",
            "source_run_id",
            "source_snapshot_id",
            "review_status",
            "is_locked",
            "created_at",
            "updated_at",
        }
        entity_cols = _column_names(engine, "narrative_entities")
        alias_cols = _column_names(engine, "narrative_entity_aliases")
        if "superseded_by_entity_id" not in entity_cols:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE narrative_entities "
                        "ADD COLUMN superseded_by_entity_id INTEGER"
                    )
                )
            entity_cols = _column_names(engine, "narrative_entities")
        if not required_entity_cols.issubset(entity_cols):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.MIGRATION_BASELINE_INVALID,
                f"006 entity columns incomplete: missing={sorted(required_entity_cols - entity_cols)}",
            )
        if not required_alias_cols.issubset(alias_cols):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.MIGRATION_BASELINE_INVALID,
                f"006 alias columns incomplete: missing={sorted(required_alias_cols - alias_cols)}",
            )
        _ensure_narrative_006_indexes(engine)
    except NarrativeCoreError:
        raise
    except Exception as exc:
        # Failure must not reach _record_applied.
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.MIGRATION_BASELINE_INVALID,
            f"006 narrative entities/aliases migration failed: {exc}",
        ) from exc

    _ensure_schema_migrations_table(engine)
    _record_applied(engine, MIGRATION_NARRATIVE_ENTITIES_ALIASES, checksum)


def migrate_narrative_20260723_007_narrative_assets_versions(engine: Engine) -> None:
    """Create narrative_assets / narrative_asset_versions + canonical partial unique index.

    Idempotent: skips CREATE TABLE when primary table already exists (e.g. after
    ``Base.metadata.create_all``), always ensures supporting indexes, then records
    the ledger only after successful DDL. SQL body checksum is stable.
    """
    checksum = migration_checksum(SQL_007)
    if "narrative_assets" not in _table_names(engine):
        _exec_sql_script(engine, SQL_007)
    # Ensure indexes even when tables came from create_all (SQL body skipped).
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_narrative_assets_book_id "
                "ON narrative_assets (book_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_narrative_assets_book_lifecycle "
                "ON narrative_assets (book_id, lifecycle_status)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_narrative_asset_versions_asset_id "
                "ON narrative_asset_versions (asset_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_narrative_asset_versions_asset_review "
                "ON narrative_asset_versions (asset_id, review_status)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_narrative_asset_versions_snapshot "
                "ON narrative_asset_versions (book_snapshot_id)"
            )
        )
        # Partial unique: at most one canonical version per asset.
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_narrative_asset_versions_one_canonical "
                "ON narrative_asset_versions (asset_id) WHERE is_canonical = 1"
            )
        )
    _ensure_schema_migrations_table(engine)
    _record_applied(engine, MIGRATION_NARRATIVE_ASSETS_VERSIONS, checksum)


def migrate_narrative_20260723_008_narrative_asset_evidence(engine: Engine) -> None:
    """Create narrative_asset_evidence. Idempotent; ledger only after success."""
    checksum = migration_checksum(SQL_008)
    if "narrative_asset_evidence" not in _table_names(engine):
        _exec_sql_script(engine, SQL_008)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_narrative_asset_evidence_version "
                "ON narrative_asset_evidence (asset_version_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_narrative_asset_evidence_snapshot "
                "ON narrative_asset_evidence (book_snapshot_id)"
            )
        )
    _ensure_schema_migrations_table(engine)
    _record_applied(engine, MIGRATION_NARRATIVE_ASSET_EVIDENCE, checksum)


def migrate_narrative_20260723_009_narrative_relations_versions_evidence(
    engine: Engine,
) -> None:
    """Agent F: narrative_relations / versions / evidence (idempotent, no backfill)."""
    checksum = migration_checksum(SQL_009)
    names = _table_names(engine)
    if "narrative_relations" not in names:
        _exec_sql_script(engine, SQL_009)
        with engine.begin() as connection:
            for statement in (
                "CREATE INDEX IF NOT EXISTS ix_narrative_relations_book_id "
                "ON narrative_relations (book_id)",
                "CREATE INDEX IF NOT EXISTS ix_narrative_relations_source "
                "ON narrative_relations (source_asset_id)",
                "CREATE INDEX IF NOT EXISTS ix_narrative_relations_target "
                "ON narrative_relations (target_asset_id)",
                "CREATE INDEX IF NOT EXISTS ix_narrative_relation_versions_relation_id "
                "ON narrative_relation_versions (relation_id)",
                "CREATE INDEX IF NOT EXISTS ix_narrative_relation_versions_rel_review "
                "ON narrative_relation_versions (relation_id, review_status)",
                "CREATE INDEX IF NOT EXISTS ix_narrative_relation_versions_snapshot "
                "ON narrative_relation_versions (book_snapshot_id)",
                "CREATE INDEX IF NOT EXISTS ix_narrative_relation_evidence_version "
                "ON narrative_relation_evidence (relation_version_id)",
                "CREATE INDEX IF NOT EXISTS ix_narrative_relation_evidence_snapshot "
                "ON narrative_relation_evidence (book_snapshot_id)",
            ):
                connection.execute(text(statement))
    _ensure_schema_migrations_table(engine)
    _record_applied(engine, MIGRATION_NARRATIVE_RELATIONS_VERSIONS_EVIDENCE, checksum)


def migrate_narrative_20260723_010_analysis_conflicts(engine: Engine) -> None:
    """Agent F: analysis_conflicts (idempotent, no auto-adjudication, no backfill)."""
    checksum = migration_checksum(SQL_010)
    if "analysis_conflicts" not in _table_names(engine):
        _exec_sql_script(engine, SQL_010)
        with engine.begin() as connection:
            for statement in (
                "CREATE INDEX IF NOT EXISTS ix_analysis_conflicts_book_status "
                "ON analysis_conflicts (book_id, status)",
                "CREATE INDEX IF NOT EXISTS ix_analysis_conflicts_run "
                "ON analysis_conflicts (run_id)",
                "CREATE INDEX IF NOT EXISTS ix_analysis_conflicts_book_id "
                "ON analysis_conflicts (book_id)",
                "CREATE INDEX IF NOT EXISTS ix_analysis_conflicts_conflict_type "
                "ON analysis_conflicts (conflict_type)",
                "CREATE INDEX IF NOT EXISTS ix_analysis_conflicts_status "
                "ON analysis_conflicts (status)",
            ):
                connection.execute(text(statement))
    _ensure_schema_migrations_table(engine)
    _record_applied(engine, MIGRATION_ANALYSIS_CONFLICTS, checksum)


SQL_011 = """
CREATE TABLE whole_book_run_windows (
    id INTEGER NOT NULL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    window_index INTEGER NOT NULL,
    start_paragraph_id VARCHAR(64) NOT NULL DEFAULT '',
    end_paragraph_id VARCHAR(64) NOT NULL DEFAULT '',
    start_chapter_id INTEGER,
    end_chapter_id INTEGER,
    input_hash VARCHAR(64) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    state_version_before INTEGER,
    state_version_after INTEGER,
    provider_attempt_id INTEGER,
    token_input INTEGER NOT NULL DEFAULT 0,
    token_output INTEGER NOT NULL DEFAULT 0,
    cost FLOAT NOT NULL DEFAULT 0,
    error_code VARCHAR(100),
    error_detail TEXT,
    checkpoint_json TEXT NOT NULL DEFAULT '{}',
    started_at DATETIME,
    completed_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE CASCADE,
    FOREIGN KEY(start_chapter_id) REFERENCES chapters (id) ON DELETE SET NULL,
    FOREIGN KEY(end_chapter_id) REFERENCES chapters (id) ON DELETE SET NULL,
    FOREIGN KEY(provider_attempt_id) REFERENCES model_invocations (id) ON DELETE SET NULL,
    UNIQUE (run_id, window_index),
    UNIQUE (run_id, input_hash)
);
CREATE TABLE whole_book_run_state_versions (
    id INTEGER NOT NULL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL,
    after_window_index INTEGER,
    state_json TEXT NOT NULL DEFAULT '{}',
    state_hash VARCHAR(64) NOT NULL DEFAULT '',
    source_stage_key VARCHAR(64),
    created_at DATETIME NOT NULL,
    FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE CASCADE,
    UNIQUE (run_id, version_number)
);
"""


def migrate_narrative_20260725_011_whole_book_overview_runtime(engine: Engine) -> None:
    """STEP 2.1: window execution + recoverable state versions (idempotent)."""
    checksum = migration_checksum(SQL_011)
    names = _table_names(engine)
    if "whole_book_run_windows" not in names or "whole_book_run_state_versions" not in names:
        # Partial apply: only create missing tables from SQL_011.
        with engine.begin() as connection:
            if "whole_book_run_windows" not in names:
                connection.execute(
                    text(
                        """
                        CREATE TABLE whole_book_run_windows (
                            id INTEGER NOT NULL PRIMARY KEY,
                            run_id INTEGER NOT NULL,
                            window_index INTEGER NOT NULL,
                            start_paragraph_id VARCHAR(64) NOT NULL DEFAULT '',
                            end_paragraph_id VARCHAR(64) NOT NULL DEFAULT '',
                            start_chapter_id INTEGER,
                            end_chapter_id INTEGER,
                            input_hash VARCHAR(64) NOT NULL DEFAULT '',
                            status VARCHAR(32) NOT NULL DEFAULT 'pending',
                            attempt_count INTEGER NOT NULL DEFAULT 0,
                            state_version_before INTEGER,
                            state_version_after INTEGER,
                            provider_attempt_id INTEGER,
                            token_input INTEGER NOT NULL DEFAULT 0,
                            token_output INTEGER NOT NULL DEFAULT 0,
                            cost FLOAT NOT NULL DEFAULT 0,
                            error_code VARCHAR(100),
                            error_detail TEXT,
                            checkpoint_json TEXT NOT NULL DEFAULT '{}',
                            started_at DATETIME,
                            completed_at DATETIME,
                            created_at DATETIME NOT NULL,
                            updated_at DATETIME NOT NULL,
                            FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE CASCADE,
                            FOREIGN KEY(start_chapter_id) REFERENCES chapters (id) ON DELETE SET NULL,
                            FOREIGN KEY(end_chapter_id) REFERENCES chapters (id) ON DELETE SET NULL,
                            FOREIGN KEY(provider_attempt_id) REFERENCES model_invocations (id) ON DELETE SET NULL,
                            UNIQUE (run_id, window_index),
                            UNIQUE (run_id, input_hash)
                        )
                        """
                    )
                )
            if "whole_book_run_state_versions" not in names:
                connection.execute(
                    text(
                        """
                        CREATE TABLE whole_book_run_state_versions (
                            id INTEGER NOT NULL PRIMARY KEY,
                            run_id INTEGER NOT NULL,
                            version_number INTEGER NOT NULL,
                            after_window_index INTEGER,
                            state_json TEXT NOT NULL DEFAULT '{}',
                            state_hash VARCHAR(64) NOT NULL DEFAULT '',
                            source_stage_key VARCHAR(64),
                            created_at DATETIME NOT NULL,
                            FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE CASCADE,
                            UNIQUE (run_id, version_number)
                        )
                        """
                    )
                )
    with engine.begin() as connection:
        for statement in (
            "CREATE INDEX IF NOT EXISTS ix_wb_run_windows_run_id "
            "ON whole_book_run_windows (run_id)",
            "CREATE INDEX IF NOT EXISTS ix_wb_run_windows_run_status "
            "ON whole_book_run_windows (run_id, status)",
            "CREATE INDEX IF NOT EXISTS ix_wb_run_windows_status "
            "ON whole_book_run_windows (status)",
            "CREATE INDEX IF NOT EXISTS ix_wb_run_state_versions_run_id "
            "ON whole_book_run_state_versions (run_id)",
        ):
            connection.execute(text(statement))
    _ensure_schema_migrations_table(engine)
    _record_applied(engine, MIGRATION_WHOLE_BOOK_OVERVIEW_RUNTIME, checksum)


def apply_narrative_phase1bp_migrations(engine: Engine) -> None:
    """Apply Phase 1B-P skeleton migrations 006–010 (after Phase 1P 001–005)."""
    apply_narrative_phase1p_migrations(engine)
    migrate_narrative_20260723_006_narrative_entities_aliases(engine)
    migrate_narrative_20260723_007_narrative_assets_versions(engine)
    migrate_narrative_20260723_008_narrative_asset_evidence(engine)
    migrate_narrative_20260723_009_narrative_relations_versions_evidence(engine)
    migrate_narrative_20260723_010_analysis_conflicts(engine)


def apply_narrative_overview_migrations(engine: Engine) -> None:
    """Apply STEP 2.1 overview runtime migration (after Phase 1B-P)."""
    apply_narrative_phase1bp_migrations(engine)
    migrate_narrative_20260725_011_whole_book_overview_runtime(engine)


def apply_narrative_migrations(engine: Engine) -> None:
    """Apply all frozen narrative migrations (Phase 1P + 1B-P + Overview + WB foundation)."""
    apply_narrative_overview_migrations(engine)
    migrate_narrative_20260728_012_whole_book_foundation_v1(engine)
    migrate_narrative_20260728_013_whole_book_snapshot_immutability(engine)


SQL_012 = """
ALTER TABLE book_snapshots ADD COLUMN snapshot_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE book_snapshots ADD COLUMN completed_at DATETIME;
ALTER TABLE book_snapshot_paragraphs ADD COLUMN global_paragraph_index INTEGER;
CREATE TABLE whole_book_cost_estimates (
    id INTEGER NOT NULL PRIMARY KEY,
    book_id INTEGER NOT NULL,
    book_revision_hash VARCHAR(64) NOT NULL,
    mode VARCHAR(64) NOT NULL,
    provider_config_id INTEGER NOT NULL,
    model_name VARCHAR(255) NOT NULL DEFAULT '',
    chapter_count INTEGER NOT NULL DEFAULT 0,
    paragraph_count INTEGER NOT NULL DEFAULT 0,
    character_count INTEGER NOT NULL DEFAULT 0,
    estimated_window_count INTEGER NOT NULL DEFAULT 0,
    estimated_provider_call_count INTEGER NOT NULL DEFAULT 0,
    estimated_input_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_output_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_min_cny NUMERIC(18, 6),
    estimated_cost_max_cny NUMERIC(18, 6),
    currency VARCHAR(8) NOT NULL DEFAULT 'CNY',
    pricing_status VARCHAR(32) NOT NULL DEFAULT 'unavailable',
    pricing_reason_code VARCHAR(64),
    contract_version VARCHAR(64) NOT NULL,
    estimate_version VARCHAR(64) NOT NULL,
    created_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE
);
CREATE TABLE whole_book_consents (
    id INTEGER NOT NULL PRIMARY KEY,
    book_id INTEGER NOT NULL,
    estimate_id INTEGER NOT NULL,
    book_revision_hash VARCHAR(64) NOT NULL,
    mode VARCHAR(64) NOT NULL,
    provider_config_id INTEGER NOT NULL,
    model_name VARCHAR(255) NOT NULL DEFAULT '',
    accepted_estimated_cost_max_cny NUMERIC(18, 6),
    user_budget_limit_cny NUMERIC(18, 6) NOT NULL DEFAULT 0,
    max_provider_calls INTEGER NOT NULL DEFAULT 0,
    max_input_tokens INTEGER NOT NULL DEFAULT 0,
    max_output_tokens INTEGER NOT NULL DEFAULT 0,
    auto_retry_enabled INTEGER NOT NULL DEFAULT 0,
    max_retries_per_unit INTEGER NOT NULL DEFAULT 0,
    accepted_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    revoked_at DATETIME,
    FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE,
    FOREIGN KEY(estimate_id) REFERENCES whole_book_cost_estimates (id) ON DELETE RESTRICT
);
CREATE TABLE whole_book_runs (
    id INTEGER NOT NULL PRIMARY KEY,
    book_id INTEGER NOT NULL,
    snapshot_id INTEGER,
    mode VARCHAR(64) NOT NULL DEFAULT 'whole_book_native',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    current_stage_code VARCHAR(64),
    idempotency_key VARCHAR(128) NOT NULL,
    engine_id VARCHAR(128) NOT NULL DEFAULT '',
    engine_version VARCHAR(64) NOT NULL DEFAULT '',
    contract_version VARCHAR(64) NOT NULL DEFAULT '',
    prompt_version VARCHAR(128),
    result_origin VARCHAR(32) NOT NULL DEFAULT 'formal',
    consent_id INTEGER,
    cost_policy_id INTEGER,
    created_at DATETIME NOT NULL,
    started_at DATETIME,
    paused_at DATETIME,
    completed_at DATETIME,
    failed_at DATETIME,
    cancelled_at DATETIME,
    failure_code VARCHAR(128),
    failure_message_safe VARCHAR(500),
    FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE,
    FOREIGN KEY(snapshot_id) REFERENCES book_snapshots (id) ON DELETE SET NULL,
    FOREIGN KEY(consent_id) REFERENCES whole_book_consents (id) ON DELETE SET NULL,
    CONSTRAINT uq_wb_runs_idempotency_key UNIQUE (idempotency_key)
);
CREATE TABLE whole_book_run_stages (
    id INTEGER NOT NULL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    stage_code VARCHAR(64) NOT NULL,
    sequence INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    progress_current INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    started_at DATETIME,
    completed_at DATETIME,
    last_error_code VARCHAR(128),
    last_error_message_safe VARCHAR(500),
    FOREIGN KEY(run_id) REFERENCES whole_book_runs (id) ON DELETE CASCADE,
    CONSTRAINT uq_wb_run_stages_run_code UNIQUE (run_id, stage_code)
);
CREATE TABLE whole_book_checkpoints (
    id INTEGER NOT NULL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    stage_code VARCHAR(64) NOT NULL,
    checkpoint_key VARCHAR(128) NOT NULL,
    sequence_no INTEGER NOT NULL DEFAULT 0,
    completed_unit_count INTEGER NOT NULL DEFAULT 0,
    last_completed_window_id INTEGER,
    payload_hash VARCHAR(64) NOT NULL DEFAULT '',
    checkpoint_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at DATETIME NOT NULL,
    FOREIGN KEY(run_id) REFERENCES whole_book_runs (id) ON DELETE CASCADE,
    CONSTRAINT uq_wb_checkpoints_run_stage_key UNIQUE (run_id, stage_code, checkpoint_key)
);
CREATE TABLE whole_book_windows (
    id INTEGER NOT NULL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    snapshot_id INTEGER,
    window_index INTEGER NOT NULL DEFAULT 0,
    first_global_paragraph_index INTEGER NOT NULL DEFAULT 0,
    last_global_paragraph_index INTEGER NOT NULL DEFAULT 0,
    chapter_start_index INTEGER NOT NULL DEFAULT 0,
    chapter_end_index INTEGER NOT NULL DEFAULT 0,
    paragraph_count INTEGER NOT NULL DEFAULT 0,
    character_count INTEGER NOT NULL DEFAULT 0,
    token_estimate INTEGER NOT NULL DEFAULT 0,
    overlap_before_paragraphs INTEGER NOT NULL DEFAULT 0,
    overlap_after_paragraphs INTEGER NOT NULL DEFAULT 0,
    window_hash VARCHAR(64) NOT NULL DEFAULT '',
    idempotency_key VARCHAR(128) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    FOREIGN KEY(run_id) REFERENCES whole_book_runs (id) ON DELETE CASCADE,
    FOREIGN KEY(snapshot_id) REFERENCES book_snapshots (id) ON DELETE SET NULL,
    CONSTRAINT uq_wb_windows_run_index UNIQUE (run_id, window_index)
);
CREATE TABLE whole_book_provider_units (
    id INTEGER NOT NULL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    stage_code VARCHAR(64) NOT NULL,
    unit_key VARCHAR(128) NOT NULL,
    unit_type VARCHAR(64) NOT NULL,
    window_id INTEGER,
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash VARCHAR(64) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    result_hash VARCHAR(64),
    last_error_code VARCHAR(128),
    created_at DATETIME NOT NULL,
    started_at DATETIME,
    completed_at DATETIME,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(run_id) REFERENCES whole_book_runs (id) ON DELETE CASCADE,
    FOREIGN KEY(window_id) REFERENCES whole_book_windows (id) ON DELETE SET NULL,
    CONSTRAINT uq_wb_provider_units_run_stage_key UNIQUE (run_id, stage_code, unit_key),
    CONSTRAINT uq_wb_provider_units_idempotency UNIQUE (idempotency_key)
);
CREATE TABLE whole_book_provider_attempts (
    id INTEGER NOT NULL PRIMARY KEY,
    provider_unit_id INTEGER NOT NULL,
    attempt_no INTEGER NOT NULL,
    provider_id VARCHAR(128) NOT NULL DEFAULT '',
    model_name VARCHAR(255) NOT NULL DEFAULT '',
    request_hash VARCHAR(64) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_cny NUMERIC(18, 6),
    error_code VARCHAR(128),
    error_message_safe VARCHAR(500),
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    FOREIGN KEY(provider_unit_id) REFERENCES whole_book_provider_units (id) ON DELETE CASCADE,
    CONSTRAINT uq_wb_provider_attempts_unit_attempt UNIQUE (provider_unit_id, attempt_no)
);
CREATE INDEX IF NOT EXISTS ix_book_snapshot_paragraphs_global_paragraph_index
    ON book_snapshot_paragraphs (global_paragraph_index);
CREATE INDEX IF NOT EXISTS ix_wb_cost_estimates_book_created
    ON whole_book_cost_estimates (book_id, created_at);
CREATE INDEX IF NOT EXISTS ix_whole_book_cost_estimates_book_id
    ON whole_book_cost_estimates (book_id);
CREATE INDEX IF NOT EXISTS ix_whole_book_cost_estimates_provider_config_id
    ON whole_book_cost_estimates (provider_config_id);
CREATE INDEX IF NOT EXISTS ix_wb_consents_book_accepted
    ON whole_book_consents (book_id, accepted_at);
CREATE INDEX IF NOT EXISTS ix_whole_book_consents_book_id ON whole_book_consents (book_id);
CREATE INDEX IF NOT EXISTS ix_whole_book_consents_estimate_id ON whole_book_consents (estimate_id);
CREATE INDEX IF NOT EXISTS ix_wb_runs_book_status ON whole_book_runs (book_id, status);
CREATE INDEX IF NOT EXISTS ix_wb_runs_snapshot ON whole_book_runs (snapshot_id);
CREATE INDEX IF NOT EXISTS ix_whole_book_runs_book_id ON whole_book_runs (book_id);
CREATE INDEX IF NOT EXISTS ix_whole_book_runs_consent_id ON whole_book_runs (consent_id);
CREATE INDEX IF NOT EXISTS ix_whole_book_runs_snapshot_id ON whole_book_runs (snapshot_id);
CREATE INDEX IF NOT EXISTS ix_whole_book_runs_status ON whole_book_runs (status);
CREATE INDEX IF NOT EXISTS ix_wb_run_stages_run_sequence
    ON whole_book_run_stages (run_id, sequence);
CREATE INDEX IF NOT EXISTS ix_whole_book_run_stages_run_id ON whole_book_run_stages (run_id);
CREATE INDEX IF NOT EXISTS ix_whole_book_checkpoints_run_id ON whole_book_checkpoints (run_id);
CREATE INDEX IF NOT EXISTS ix_wb_windows_run_status ON whole_book_windows (run_id, status);
CREATE INDEX IF NOT EXISTS ix_whole_book_windows_run_id ON whole_book_windows (run_id);
CREATE INDEX IF NOT EXISTS ix_wb_provider_units_run_status
    ON whole_book_provider_units (run_id, status);
CREATE INDEX IF NOT EXISTS ix_wb_provider_units_idempotency
    ON whole_book_provider_units (idempotency_key);
CREATE INDEX IF NOT EXISTS ix_whole_book_provider_units_run_id
    ON whole_book_provider_units (run_id);
CREATE INDEX IF NOT EXISTS ix_wb_provider_attempts_unit_attempt
    ON whole_book_provider_attempts (provider_unit_id, attempt_no);
CREATE INDEX IF NOT EXISTS ix_whole_book_provider_attempts_provider_unit_id
    ON whole_book_provider_attempts (provider_unit_id);
"""


_WB012_TABLES: tuple[str, ...] = (
    "whole_book_cost_estimates",
    "whole_book_consents",
    "whole_book_runs",
    "whole_book_run_stages",
    "whole_book_checkpoints",
    "whole_book_windows",
    "whole_book_provider_units",
    "whole_book_provider_attempts",
)


def _ensure_wb012_indexes(connection) -> None:  # noqa: ANN001
    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_book_snapshot_paragraphs_global_paragraph_index "
        "ON book_snapshot_paragraphs (global_paragraph_index)",
        "CREATE INDEX IF NOT EXISTS ix_wb_cost_estimates_book_created "
        "ON whole_book_cost_estimates (book_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_whole_book_cost_estimates_book_id "
        "ON whole_book_cost_estimates (book_id)",
        "CREATE INDEX IF NOT EXISTS ix_whole_book_cost_estimates_provider_config_id "
        "ON whole_book_cost_estimates (provider_config_id)",
        "CREATE INDEX IF NOT EXISTS ix_wb_consents_book_accepted "
        "ON whole_book_consents (book_id, accepted_at)",
        "CREATE INDEX IF NOT EXISTS ix_whole_book_consents_book_id "
        "ON whole_book_consents (book_id)",
        "CREATE INDEX IF NOT EXISTS ix_whole_book_consents_estimate_id "
        "ON whole_book_consents (estimate_id)",
        "CREATE INDEX IF NOT EXISTS ix_wb_runs_book_status "
        "ON whole_book_runs (book_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_wb_runs_snapshot ON whole_book_runs (snapshot_id)",
        "CREATE INDEX IF NOT EXISTS ix_whole_book_runs_book_id ON whole_book_runs (book_id)",
        "CREATE INDEX IF NOT EXISTS ix_whole_book_runs_consent_id ON whole_book_runs (consent_id)",
        "CREATE INDEX IF NOT EXISTS ix_whole_book_runs_snapshot_id "
        "ON whole_book_runs (snapshot_id)",
        "CREATE INDEX IF NOT EXISTS ix_whole_book_runs_status ON whole_book_runs (status)",
        "CREATE INDEX IF NOT EXISTS ix_wb_run_stages_run_sequence "
        "ON whole_book_run_stages (run_id, sequence)",
        "CREATE INDEX IF NOT EXISTS ix_whole_book_run_stages_run_id "
        "ON whole_book_run_stages (run_id)",
        "CREATE INDEX IF NOT EXISTS ix_whole_book_checkpoints_run_id "
        "ON whole_book_checkpoints (run_id)",
        "CREATE INDEX IF NOT EXISTS ix_wb_windows_run_status "
        "ON whole_book_windows (run_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_whole_book_windows_run_id ON whole_book_windows (run_id)",
        "CREATE INDEX IF NOT EXISTS ix_wb_provider_units_run_status "
        "ON whole_book_provider_units (run_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_wb_provider_units_idempotency "
        "ON whole_book_provider_units (idempotency_key)",
        "CREATE INDEX IF NOT EXISTS ix_whole_book_provider_units_run_id "
        "ON whole_book_provider_units (run_id)",
        "CREATE INDEX IF NOT EXISTS ix_wb_provider_attempts_unit_attempt "
        "ON whole_book_provider_attempts (provider_unit_id, attempt_no)",
        "CREATE INDEX IF NOT EXISTS ix_whole_book_provider_attempts_provider_unit_id "
        "ON whole_book_provider_attempts (provider_unit_id)",
    ):
        connection.execute(text(statement))


def migrate_narrative_20260728_012_whole_book_foundation_v1(engine: Engine) -> None:
    """WB-0.4: snapshot columns + whole-book foundation tables (idempotent)."""
    checksum = migration_checksum(SQL_012)
    names = _table_names(engine)
    if "book_snapshots" not in names:
        migrate_narrative_20260723_003_book_snapshots(engine)
        names = _table_names(engine)
    try:
        with engine.begin() as connection:
            if "book_snapshots" in names:
                snapshot_cols = {
                    row[1]
                    for row in connection.execute(text("PRAGMA table_info(book_snapshots)")).fetchall()
                }
                if "snapshot_version" not in snapshot_cols:
                    connection.execute(
                        text(
                            "ALTER TABLE book_snapshots "
                            "ADD COLUMN snapshot_version INTEGER NOT NULL DEFAULT 1"
                        )
                    )
                if "completed_at" not in snapshot_cols:
                    connection.execute(
                        text("ALTER TABLE book_snapshots ADD COLUMN completed_at DATETIME")
                    )
            if "book_snapshot_paragraphs" in names:
                paragraph_cols = {
                    row[1]
                    for row in connection.execute(
                        text("PRAGMA table_info(book_snapshot_paragraphs)")
                    ).fetchall()
                }
                if "global_paragraph_index" not in paragraph_cols:
                    connection.execute(
                        text(
                            "ALTER TABLE book_snapshot_paragraphs "
                            "ADD COLUMN global_paragraph_index INTEGER"
                        )
                    )
            if "whole_book_cost_estimates" not in names:
                connection.execute(
                    text(
                        """
                        CREATE TABLE whole_book_cost_estimates (
                            id INTEGER NOT NULL PRIMARY KEY,
                            book_id INTEGER NOT NULL,
                            book_revision_hash VARCHAR(64) NOT NULL,
                            mode VARCHAR(64) NOT NULL,
                            provider_config_id INTEGER NOT NULL,
                            model_name VARCHAR(255) NOT NULL DEFAULT '',
                            chapter_count INTEGER NOT NULL DEFAULT 0,
                            paragraph_count INTEGER NOT NULL DEFAULT 0,
                            character_count INTEGER NOT NULL DEFAULT 0,
                            estimated_window_count INTEGER NOT NULL DEFAULT 0,
                            estimated_provider_call_count INTEGER NOT NULL DEFAULT 0,
                            estimated_input_tokens INTEGER NOT NULL DEFAULT 0,
                            estimated_output_tokens INTEGER NOT NULL DEFAULT 0,
                            estimated_cost_min_cny NUMERIC(18, 6),
                            estimated_cost_max_cny NUMERIC(18, 6),
                            currency VARCHAR(8) NOT NULL DEFAULT 'CNY',
                            pricing_status VARCHAR(32) NOT NULL DEFAULT 'unavailable',
                            pricing_reason_code VARCHAR(64),
                            contract_version VARCHAR(64) NOT NULL,
                            estimate_version VARCHAR(64) NOT NULL,
                            created_at DATETIME NOT NULL,
                            expires_at DATETIME NOT NULL,
                            FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE
                        )
                        """
                    )
                )
            if "whole_book_consents" not in names:
                connection.execute(
                    text(
                        """
                        CREATE TABLE whole_book_consents (
                            id INTEGER NOT NULL PRIMARY KEY,
                            book_id INTEGER NOT NULL,
                            estimate_id INTEGER NOT NULL,
                            book_revision_hash VARCHAR(64) NOT NULL,
                            mode VARCHAR(64) NOT NULL,
                            provider_config_id INTEGER NOT NULL,
                            model_name VARCHAR(255) NOT NULL DEFAULT '',
                            accepted_estimated_cost_max_cny NUMERIC(18, 6),
                            user_budget_limit_cny NUMERIC(18, 6) NOT NULL DEFAULT 0,
                            max_provider_calls INTEGER NOT NULL DEFAULT 0,
                            max_input_tokens INTEGER NOT NULL DEFAULT 0,
                            max_output_tokens INTEGER NOT NULL DEFAULT 0,
                            auto_retry_enabled INTEGER NOT NULL DEFAULT 0,
                            max_retries_per_unit INTEGER NOT NULL DEFAULT 0,
                            accepted_at DATETIME NOT NULL,
                            expires_at DATETIME NOT NULL,
                            revoked_at DATETIME,
                            FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE,
                            FOREIGN KEY(estimate_id) REFERENCES whole_book_cost_estimates (id)
                                ON DELETE RESTRICT
                        )
                        """
                    )
                )
            if "whole_book_runs" not in names:
                connection.execute(
                    text(
                        """
                        CREATE TABLE whole_book_runs (
                            id INTEGER NOT NULL PRIMARY KEY,
                            book_id INTEGER NOT NULL,
                            snapshot_id INTEGER,
                            mode VARCHAR(64) NOT NULL DEFAULT 'whole_book_native',
                            status VARCHAR(32) NOT NULL DEFAULT 'pending',
                            current_stage_code VARCHAR(64),
                            idempotency_key VARCHAR(128) NOT NULL,
                            engine_id VARCHAR(128) NOT NULL DEFAULT '',
                            engine_version VARCHAR(64) NOT NULL DEFAULT '',
                            contract_version VARCHAR(64) NOT NULL DEFAULT '',
                            prompt_version VARCHAR(128),
                            result_origin VARCHAR(32) NOT NULL DEFAULT 'formal',
                            consent_id INTEGER,
                            cost_policy_id INTEGER,
                            created_at DATETIME NOT NULL,
                            started_at DATETIME,
                            paused_at DATETIME,
                            completed_at DATETIME,
                            failed_at DATETIME,
                            cancelled_at DATETIME,
                            failure_code VARCHAR(128),
                            failure_message_safe VARCHAR(500),
                            FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE,
                            FOREIGN KEY(snapshot_id) REFERENCES book_snapshots (id)
                                ON DELETE SET NULL,
                            FOREIGN KEY(consent_id) REFERENCES whole_book_consents (id)
                                ON DELETE SET NULL,
                            CONSTRAINT uq_wb_runs_idempotency_key UNIQUE (idempotency_key)
                        )
                        """
                    )
                )
            if "whole_book_run_stages" not in names:
                connection.execute(
                    text(
                        """
                        CREATE TABLE whole_book_run_stages (
                            id INTEGER NOT NULL PRIMARY KEY,
                            run_id INTEGER NOT NULL,
                            stage_code VARCHAR(64) NOT NULL,
                            sequence INTEGER NOT NULL DEFAULT 0,
                            status VARCHAR(32) NOT NULL DEFAULT 'pending',
                            progress_current INTEGER NOT NULL DEFAULT 0,
                            progress_total INTEGER NOT NULL DEFAULT 0,
                            started_at DATETIME,
                            completed_at DATETIME,
                            last_error_code VARCHAR(128),
                            last_error_message_safe VARCHAR(500),
                            FOREIGN KEY(run_id) REFERENCES whole_book_runs (id) ON DELETE CASCADE,
                            CONSTRAINT uq_wb_run_stages_run_code UNIQUE (run_id, stage_code)
                        )
                        """
                    )
                )
            if "whole_book_checkpoints" not in names:
                connection.execute(
                    text(
                        """
                        CREATE TABLE whole_book_checkpoints (
                            id INTEGER NOT NULL PRIMARY KEY,
                            run_id INTEGER NOT NULL,
                            stage_code VARCHAR(64) NOT NULL,
                            checkpoint_key VARCHAR(128) NOT NULL,
                            sequence_no INTEGER NOT NULL DEFAULT 0,
                            completed_unit_count INTEGER NOT NULL DEFAULT 0,
                            last_completed_window_id INTEGER,
                            payload_hash VARCHAR(64) NOT NULL DEFAULT '',
                            checkpoint_payload_json TEXT NOT NULL DEFAULT '{}',
                            created_at DATETIME NOT NULL,
                            FOREIGN KEY(run_id) REFERENCES whole_book_runs (id) ON DELETE CASCADE,
                            CONSTRAINT uq_wb_checkpoints_run_stage_key
                                UNIQUE (run_id, stage_code, checkpoint_key)
                        )
                        """
                    )
                )
            if "whole_book_windows" not in names:
                connection.execute(
                    text(
                        """
                        CREATE TABLE whole_book_windows (
                            id INTEGER NOT NULL PRIMARY KEY,
                            run_id INTEGER NOT NULL,
                            snapshot_id INTEGER,
                            window_index INTEGER NOT NULL DEFAULT 0,
                            first_global_paragraph_index INTEGER NOT NULL DEFAULT 0,
                            last_global_paragraph_index INTEGER NOT NULL DEFAULT 0,
                            chapter_start_index INTEGER NOT NULL DEFAULT 0,
                            chapter_end_index INTEGER NOT NULL DEFAULT 0,
                            paragraph_count INTEGER NOT NULL DEFAULT 0,
                            character_count INTEGER NOT NULL DEFAULT 0,
                            token_estimate INTEGER NOT NULL DEFAULT 0,
                            overlap_before_paragraphs INTEGER NOT NULL DEFAULT 0,
                            overlap_after_paragraphs INTEGER NOT NULL DEFAULT 0,
                            window_hash VARCHAR(64) NOT NULL DEFAULT '',
                            idempotency_key VARCHAR(128) NOT NULL DEFAULT '',
                            status VARCHAR(32) NOT NULL DEFAULT 'pending',
                            FOREIGN KEY(run_id) REFERENCES whole_book_runs (id) ON DELETE CASCADE,
                            FOREIGN KEY(snapshot_id) REFERENCES book_snapshots (id)
                                ON DELETE SET NULL,
                            CONSTRAINT uq_wb_windows_run_index UNIQUE (run_id, window_index)
                        )
                        """
                    )
                )
            if "whole_book_provider_units" not in names:
                connection.execute(
                    text(
                        """
                        CREATE TABLE whole_book_provider_units (
                            id INTEGER NOT NULL PRIMARY KEY,
                            run_id INTEGER NOT NULL,
                            stage_code VARCHAR(64) NOT NULL,
                            unit_key VARCHAR(128) NOT NULL,
                            unit_type VARCHAR(64) NOT NULL,
                            window_id INTEGER,
                            idempotency_key VARCHAR(128) NOT NULL,
                            request_hash VARCHAR(64) NOT NULL DEFAULT '',
                            status VARCHAR(32) NOT NULL DEFAULT 'pending',
                            attempt_count INTEGER NOT NULL DEFAULT 0,
                            result_hash VARCHAR(64),
                            last_error_code VARCHAR(128),
                            created_at DATETIME NOT NULL,
                            started_at DATETIME,
                            completed_at DATETIME,
                            updated_at DATETIME NOT NULL,
                            FOREIGN KEY(run_id) REFERENCES whole_book_runs (id) ON DELETE CASCADE,
                            FOREIGN KEY(window_id) REFERENCES whole_book_windows (id)
                                ON DELETE SET NULL,
                            CONSTRAINT uq_wb_provider_units_run_stage_key
                                UNIQUE (run_id, stage_code, unit_key),
                            CONSTRAINT uq_wb_provider_units_idempotency UNIQUE (idempotency_key)
                        )
                        """
                    )
                )
            if "whole_book_provider_attempts" not in names:
                connection.execute(
                    text(
                        """
                        CREATE TABLE whole_book_provider_attempts (
                            id INTEGER NOT NULL PRIMARY KEY,
                            provider_unit_id INTEGER NOT NULL,
                            attempt_no INTEGER NOT NULL,
                            provider_id VARCHAR(128) NOT NULL DEFAULT '',
                            model_name VARCHAR(255) NOT NULL DEFAULT '',
                            request_hash VARCHAR(64) NOT NULL DEFAULT '',
                            status VARCHAR(32) NOT NULL DEFAULT 'running',
                            input_tokens INTEGER,
                            output_tokens INTEGER,
                            cost_cny NUMERIC(18, 6),
                            error_code VARCHAR(128),
                            error_message_safe VARCHAR(500),
                            started_at DATETIME NOT NULL,
                            completed_at DATETIME,
                            FOREIGN KEY(provider_unit_id) REFERENCES whole_book_provider_units (id)
                                ON DELETE CASCADE,
                            CONSTRAINT uq_wb_provider_attempts_unit_attempt
                                UNIQUE (provider_unit_id, attempt_no)
                        )
                        """
                    )
                )
            _ensure_wb012_indexes(connection)
        names_after = _table_names(engine)
        missing = [table for table in _WB012_TABLES if table not in names_after]
        if missing:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.MIGRATION_BASELINE_INVALID,
                f"012 failed: missing tables after DDL: {missing}",
            )
        if "book_snapshots" in names_after:
            required_snapshot_cols = {"snapshot_version", "completed_at"}
            if not required_snapshot_cols.issubset(_column_names(engine, "book_snapshots")):
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.MIGRATION_BASELINE_INVALID,
                    "012 failed: book_snapshots columns incomplete",
                )
        if "book_snapshot_paragraphs" in names_after:
            if "global_paragraph_index" not in _column_names(engine, "book_snapshot_paragraphs"):
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.MIGRATION_BASELINE_INVALID,
                    "012 failed: book_snapshot_paragraphs.global_paragraph_index missing",
                )
    except NarrativeCoreError:
        raise
    except Exception as exc:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.MIGRATION_BASELINE_INVALID,
            f"012 whole-book foundation migration failed: {exc}",
        ) from exc

    _ensure_schema_migrations_table(engine)
    _record_applied(engine, MIGRATION_WHOLE_BOOK_FOUNDATION_V1, checksum)


SQL_013 = """
CREATE TRIGGER IF NOT EXISTS trg_book_snapshots_no_update_completed
BEFORE UPDATE ON book_snapshots
FOR EACH ROW
WHEN OLD.snapshot_status = 'completed'
BEGIN
    SELECT RAISE(ABORT, 'update_completed_forbidden');
END;
CREATE TRIGGER IF NOT EXISTS trg_book_snapshot_chapters_no_update_completed
BEFORE UPDATE ON book_snapshot_chapters
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM book_snapshots s
    WHERE s.id = OLD.snapshot_id AND s.snapshot_status = 'completed'
)
BEGIN
    SELECT RAISE(ABORT, 'update_completed_forbidden');
END;
CREATE TRIGGER IF NOT EXISTS trg_book_snapshot_paragraphs_no_update_completed
BEFORE UPDATE ON book_snapshot_paragraphs
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM book_snapshots s
    WHERE s.id = OLD.snapshot_id AND s.snapshot_status = 'completed'
)
BEGIN
    SELECT RAISE(ABORT, 'update_completed_forbidden');
END;
"""


def migrate_narrative_20260728_013_whole_book_snapshot_immutability(engine: Engine) -> None:
    """WB-1.2: SQLite triggers blocking UPDATE on completed snapshots (idempotent)."""
    checksum = migration_checksum(SQL_013)
    names = _table_names(engine)
    if "book_snapshots" not in names:
        migrate_narrative_20260728_012_whole_book_foundation_v1(engine)
    with engine.begin() as connection:
        for statement in (
            """
            CREATE TRIGGER IF NOT EXISTS trg_book_snapshots_no_update_completed
            BEFORE UPDATE ON book_snapshots
            FOR EACH ROW
            WHEN OLD.snapshot_status = 'completed'
            BEGIN
                SELECT RAISE(ABORT, 'update_completed_forbidden');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_book_snapshot_chapters_no_update_completed
            BEFORE UPDATE ON book_snapshot_chapters
            FOR EACH ROW
            WHEN EXISTS (
                SELECT 1 FROM book_snapshots s
                WHERE s.id = OLD.snapshot_id AND s.snapshot_status = 'completed'
            )
            BEGIN
                SELECT RAISE(ABORT, 'update_completed_forbidden');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_book_snapshot_paragraphs_no_update_completed
            BEFORE UPDATE ON book_snapshot_paragraphs
            FOR EACH ROW
            WHEN EXISTS (
                SELECT 1 FROM book_snapshots s
                WHERE s.id = OLD.snapshot_id AND s.snapshot_status = 'completed'
            )
            BEGIN
                SELECT RAISE(ABORT, 'update_completed_forbidden');
            END
            """,
        ):
            connection.execute(text(statement))
    _ensure_schema_migrations_table(engine)
    _record_applied(engine, MIGRATION_WHOLE_BOOK_SNAPSHOT_IMMUTABILITY, checksum)
