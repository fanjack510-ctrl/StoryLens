from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import Base


settings = get_settings()


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    raw = database_url.removeprefix("sqlite:///")
    # sqlite:///C:/... or sqlite:///./data/... or sqlite:////absolute
    if raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
        # sqlite:////C:/path → /C:/path
        raw = raw[1:]
    path = Path(raw)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"DATABASE_OPEN_FAILED: 无法创建数据库目录 {path.parent}: {exc}"
        ) from exc


_ensure_sqlite_parent(settings.database_url)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _) -> None:
    module = dbapi_connection.__class__.__module__
    if module.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL allows concurrent readers while one writer owns AnalysisRun tasks.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_db() -> None:
    migrate_phase_1b(engine)
    migrate_phase_2a1(engine)
    migrate_phase_2b1(engine)
    migrate_phase_2b2(engine)
    migrate_phase_1c_a(engine)
    migrate_phase_1c_a3(engine)
    migrate_phase_1c_a4(engine)
    migrate_phase_1c_a7(engine)
    migrate_phase_1c_c1(engine)
    migrate_phase_1d_c1_uat05(engine)
    migrate_phase_license_v1(engine)
    Base.metadata.create_all(bind=engine)


def migrate_phase_license_v1(target_engine) -> None:
    """StoryLens Pro offline license table (idempotent)."""
    inspector = inspect(target_engine)
    if "local_licenses" in inspector.get_table_names():
        return
    with target_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE local_licenses (
                    id INTEGER NOT NULL PRIMARY KEY,
                    license_id VARCHAR(64) NOT NULL,
                    product_code VARCHAR(64) NOT NULL,
                    edition VARCHAR(32) NOT NULL DEFAULT 'pro',
                    major_version INTEGER NOT NULL,
                    license_status VARCHAR(32) NOT NULL DEFAULT 'active',
                    signed_license TEXT NOT NULL,
                    activated_at DATETIME,
                    last_validated_at DATETIME,
                    key_id VARCHAR(64) NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    UNIQUE (license_id)
                )
                """
            )
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_local_licenses_status ON local_licenses (license_status)")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_local_licenses_product ON local_licenses (product_code)"
            )
        )


def migrate_phase_1d_c1_uat05(target_engine) -> None:
    """DEFECT-UAT-003: reservation remaining/consumed/released ledger columns."""
    inspector = inspect(target_engine)
    if "cloud_budget_reservations" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("cloud_budget_reservations")}
    additions = {
        "remaining_requests": "INTEGER NOT NULL DEFAULT 0",
        "consumed_requests": "INTEGER NOT NULL DEFAULT 0",
        "released_requests": "INTEGER NOT NULL DEFAULT 0",
        "remaining_tokens": "INTEGER NOT NULL DEFAULT 0",
        "consumed_tokens": "INTEGER NOT NULL DEFAULT 0",
        "released_tokens": "INTEGER NOT NULL DEFAULT 0",
        "remaining_cost": "FLOAT NOT NULL DEFAULT 0",
        "consumed_cost": "FLOAT NOT NULL DEFAULT 0",
        "released_cost": "FLOAT NOT NULL DEFAULT 0",
    }
    with target_engine.begin() as connection:
        for name, definition in additions.items():
            if name not in existing:
                connection.execute(
                    text(f"ALTER TABLE cloud_budget_reservations ADD COLUMN {name} {definition}")
                )
        # Backfill once: active → remaining=initial; released → released=initial.
        # Do not rewrite historical consumed amounts for already-released rows.
        connection.execute(
            text(
                """
                UPDATE cloud_budget_reservations
                SET
                    remaining_requests = CASE
                        WHEN status = 'active' THEN reserved_requests ELSE 0 END,
                    remaining_tokens = CASE
                        WHEN status = 'active' THEN reserved_tokens ELSE 0 END,
                    remaining_cost = CASE
                        WHEN status = 'active' THEN reserved_cost ELSE 0 END,
                    released_requests = CASE
                        WHEN status = 'active' THEN 0 ELSE reserved_requests END,
                    released_tokens = CASE
                        WHEN status = 'active' THEN 0 ELSE reserved_tokens END,
                    released_cost = CASE
                        WHEN status = 'active' THEN 0 ELSE reserved_cost END,
                    consumed_requests = 0,
                    consumed_tokens = 0,
                    consumed_cost = 0
                WHERE remaining_requests = 0
                  AND consumed_requests = 0
                  AND released_requests = 0
                  AND remaining_tokens = 0
                  AND consumed_tokens = 0
                  AND released_tokens = 0
                  AND remaining_cost = 0
                  AND consumed_cost = 0
                  AND released_cost = 0
                """
            )
        )


def migrate_phase_1c_c1(target_engine) -> None:
    """Reader Journey Engine tables — idempotent via create_all fallback."""
    inspector = inspect(target_engine)
    tables = inspector.get_table_names()
    indexes = [
        ("reader_journey_runs", "ix_reader_journey_runs_status", "status"),
        ("reader_journey_runs", "ix_reader_journey_runs_analysis_run", "analysis_run_id"),
        ("scene_reader_journey_profiles", "ix_srjp_run_scene", "reader_journey_run_id, scene_id"),
    ]
    with target_engine.begin() as connection:
        for table, index_name, columns in indexes:
            if table in tables:
                connection.execute(
                    text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({columns})")
                )
        if "reader_journey_runs" in tables:
            existing = {
                column["name"] for column in inspector.get_columns("reader_journey_runs")
            }
            additions = {
                "planner_version": "VARCHAR(32) NOT NULL DEFAULT '1.0'",
                "failure_details_json": "TEXT NOT NULL DEFAULT '{}'",
            }
            for name, definition in additions.items():
                if name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE reader_journey_runs ADD COLUMN {name} {definition}")
                    )


def migrate_phase_1c_a7(target_engine) -> None:
    """Add recovery lineage and review-conflict audit columns idempotently."""
    inspector = inspect(target_engine)
    tables = inspector.get_table_names()
    additions_by_table = {
        "analysis_runs": {
            "recovered_from_run_id": "INTEGER",
        },
        "boundary_review_decisions": {
            "semantic_conflict": "BOOLEAN NOT NULL DEFAULT 0",
            "conflict_code": "VARCHAR(100)",
            "deterministic_legal": "BOOLEAN",
            "deterministic_reason": "VARCHAR(64)",
            "model_boundary_candidate": "BOOLEAN",
            "enum_snapshot_json": "TEXT NOT NULL DEFAULT '{}'",
            "source_batch_index": "INTEGER",
            "manual_reason_type": "VARCHAR(64)",
        },
        "boundary_detection_batch_checkpoints": {
            "transition_map_json": "TEXT NOT NULL DEFAULT '{}'",
            "source_run_id": "INTEGER",
            "window_index": "INTEGER NOT NULL DEFAULT 0",
        },
    }
    with target_engine.begin() as connection:
        for table, additions in additions_by_table.items():
            if table not in tables:
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in additions.items():
                if name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
                    )
        if "analysis_runs" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_analysis_runs_recovered_from_run_id "
                    "ON analysis_runs (recovered_from_run_id)"
                )
            )
        if "boundary_review_decisions" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_boundary_review_decisions_semantic_conflict "
                    "ON boundary_review_decisions (semantic_conflict)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_boundary_review_decisions_conflict_code "
                    "ON boundary_review_decisions (conflict_code)"
                )
            )


def migrate_phase_1c_a4(target_engine) -> None:
    """Add staged reservation columns and drop run_id uniqueness (Stage1+Stage2)."""
    inspector = inspect(target_engine)
    if "cloud_budget_reservations" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("cloud_budget_reservations")}
    with target_engine.begin() as connection:
        additions = {
            "stage": "VARCHAR(64) NOT NULL DEFAULT 'legacy'",
            "expected_requests": "INTEGER NOT NULL DEFAULT 0",
            "worst_case_requests": "INTEGER NOT NULL DEFAULT 0",
            "released_at": "DATETIME",
        }
        for name, definition in additions.items():
            if name not in existing:
                connection.execute(
                    text(f"ALTER TABLE cloud_budget_reservations ADD COLUMN {name} {definition}")
                )
        # Rebuild only when a unique index still binds run_id alone.
        indexes = inspector.get_indexes("cloud_budget_reservations")
        unique_on_run = any(
            index.get("unique") and index.get("column_names") == ["run_id"] for index in indexes
        )
        # SQLite also stores UniqueConstraint as unique index sometimes named
        # sqlite_autoindex_cloud_budget_reservations_1
        uniques = inspector.get_unique_constraints("cloud_budget_reservations")
        unique_on_run = unique_on_run or any(
            constraint.get("column_names") == ["run_id"] for constraint in uniques
        )
        if unique_on_run:
            connection.execute(
                text(
                    """
                    CREATE TABLE cloud_budget_reservations_1c_a4 (
                        id INTEGER NOT NULL PRIMARY KEY,
                        run_id INTEGER,
                        stage VARCHAR(64) NOT NULL DEFAULT 'legacy',
                        reserved_requests INTEGER NOT NULL,
                        reserved_tokens INTEGER NOT NULL,
                        reserved_cost FLOAT NOT NULL,
                        expected_requests INTEGER NOT NULL DEFAULT 0,
                        worst_case_requests INTEGER NOT NULL DEFAULT 0,
                        status VARCHAR(32) NOT NULL,
                        expires_at DATETIME NOT NULL,
                        released_at DATETIME,
                        created_at DATETIME NOT NULL,
                        FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE CASCADE
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO cloud_budget_reservations_1c_a4 (
                        id, run_id, stage, reserved_requests, reserved_tokens, reserved_cost,
                        expected_requests, worst_case_requests, status, expires_at,
                        released_at, created_at
                    )
                    SELECT
                        id, run_id,
                        COALESCE(stage, 'legacy'),
                        reserved_requests, reserved_tokens, reserved_cost,
                        COALESCE(expected_requests, reserved_requests),
                        COALESCE(worst_case_requests, reserved_requests),
                        status, expires_at, released_at, created_at
                    FROM cloud_budget_reservations
                    """
                )
            )
            connection.execute(text("DROP TABLE cloud_budget_reservations"))
            connection.execute(
                text("ALTER TABLE cloud_budget_reservations_1c_a4 RENAME TO cloud_budget_reservations")
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_cloud_budget_reservations_run_id "
                    "ON cloud_budget_reservations (run_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_cloud_budget_reservations_stage "
                    "ON cloud_budget_reservations (stage)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_cloud_budget_reservations_status "
                    "ON cloud_budget_reservations (status)"
                )
            )


def migrate_phase_1c_a3(target_engine) -> None:
    inspector = inspect(target_engine)
    if "analysis_runs" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("analysis_runs")}
    if "client_request_id" not in existing:
        with target_engine.begin() as connection:
            connection.execute(text("ALTER TABLE analysis_runs ADD COLUMN client_request_id VARCHAR(64)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_analysis_runs_client_request_id ON analysis_runs (client_request_id)"))


def migrate_phase_1c_a(target_engine) -> None:
    inspector = inspect(target_engine)
    if "scenes" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("scenes")}
    additions = {
        "boundary_revision_id": "INTEGER",
        "boundary_source": "VARCHAR(32)",
    }
    with target_engine.begin() as connection:
        for name, definition in additions.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE scenes ADD COLUMN {name} {definition}"))


def migrate_phase_2b2(target_engine) -> None:
    inspector = inspect(target_engine)
    tables = inspector.get_table_names()
    additions_by_table = {
        "books": {
            "fixture_name": "VARCHAR(100)",
            "fixture_version": "VARCHAR(50)",
        },
        "model_invocations": {
            "requested_output_tokens": "INTEGER",
            "actual_output_tokens": "INTEGER",
            "provider_parameter_name": "VARCHAR(64)",
            "finish_reason": "VARCHAR(64)",
            "candidate_transition_count": "INTEGER",
            "selected_transition_ids_json": "TEXT",
            "mapped_after_paragraph_ids_json": "TEXT",
            "rejected_transition_ids_json": "TEXT",
            "rejected_transition_classifications_json": "TEXT",
            "transition_contract_version": "VARCHAR(32)",
            "canonical_schema_hash": "VARCHAR(64)",
        },
    }
    with target_engine.begin() as connection:
        for table, additions in additions_by_table.items():
            if table not in tables:
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
        if "model_invocations" in tables:
            connection.execute(
                text(
                    "UPDATE model_invocations SET http_request_sent=0, "
                    "audit_type='pre_send_failure', sent_at=NULL "
                    "WHERE http_status_code IS NULL AND input_tokens IS NULL "
                    "AND output_tokens IS NULL AND error_message LIKE '%database is locked%'"
                )
            )


def migrate_phase_2b1(target_engine) -> None:
    inspector = inspect(target_engine)
    if "model_invocations" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("model_invocations")}
    additions = {
        "http_request_sent": "BOOLEAN NOT NULL DEFAULT 1",
        "audit_type": "VARCHAR(32) NOT NULL DEFAULT 'provider_invocation'",
        "sent_at": "DATETIME",
    }
    with target_engine.begin() as connection:
        for name, definition in additions.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE model_invocations ADD COLUMN {name} {definition}"))
        connection.execute(text("UPDATE model_invocations SET http_request_sent=1 WHERE http_request_sent IS NULL"))
        connection.execute(text(
            "UPDATE model_invocations SET http_request_sent=0, audit_type='gate_blocked' "
            "WHERE http_status_code IS NULL AND input_tokens IS NULL AND output_tokens IS NULL "
            "AND (error_code LIKE '%BUDGET%' OR error_message LIKE '%BUDGET%')"
        ))


def migrate_phase_2a1(target_engine) -> None:
    inspector = inspect(target_engine)
    tables = inspector.get_table_names()
    additions_by_table = {
        "books": {
            "source_content": "BLOB",
            "import_diagnostics_json": "TEXT NOT NULL DEFAULT '{}'",
            "import_warning": "VARCHAR(100)",
            "revision_of_book_id": "INTEGER",
            "revision_number": "INTEGER NOT NULL DEFAULT 1",
        },
        "chapters": {
            "section_type": "VARCHAR(32) NOT NULL DEFAULT 'chapter'",
            "chapter_number_raw": "VARCHAR(64)",
            "chapter_number_normalized": "INTEGER",
            "chapter_unit": "VARCHAR(16)",
            "chapter_title": "VARCHAR(500) NOT NULL DEFAULT ''",
            "display_title": "VARCHAR(600) NOT NULL DEFAULT ''",
            "source_title_line": "VARCHAR(600) NOT NULL DEFAULT ''",
        },
        "analysis_runs": {
            "root_error_code": "VARCHAR(100)",
            "root_error_message": "TEXT",
            "failed_stage": "VARCHAR(100)",
            "failed_invocation_id": "INTEGER",
            "provider_health_at_failure": "TEXT",
            "retryable": "BOOLEAN NOT NULL DEFAULT 0",
            "user_action_hint": "TEXT",
            "analysis_mode": "VARCHAR(40) NOT NULL DEFAULT 'automatic'",
        },
    }
    with target_engine.begin() as connection:
        for table, additions in additions_by_table.items():
            if table not in tables:
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
        if "chapters" in tables:
            connection.execute(text("UPDATE chapters SET section_type='front_matter', display_title='前置内容', chapter_title='前置内容', source_title_line=title WHERE title='正文'"))
            connection.execute(text("UPDATE chapters SET display_title=title, chapter_title=title, source_title_line=title WHERE display_title=''"))


def migrate_phase_1b(target_engine) -> None:
    inspector = inspect(target_engine)
    if "analysis_runs" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("analysis_runs")}
    additions = {
        "subject_type": "VARCHAR(50) NOT NULL DEFAULT 'chapter'",
        "subject_id": "VARCHAR(100) NOT NULL DEFAULT ''",
        "prompt_hash": "VARCHAR(64) NOT NULL DEFAULT ''",
        "progress_current": "INTEGER NOT NULL DEFAULT 0",
        "progress_total": "INTEGER NOT NULL DEFAULT 0",
        "error_code": "VARCHAR(100)",
        "retry_of_run_id": "INTEGER",
        "created_at": "DATETIME",
        "queued_at": "DATETIME",
        "run_started_at": "DATETIME",
        "execution_mode": "VARCHAR(16) NOT NULL DEFAULT 'local'",
        "cloud_consent": "BOOLEAN NOT NULL DEFAULT 0",
        "cloud_consent_at": "DATETIME",
        "sends_content_to_cloud": "BOOLEAN NOT NULL DEFAULT 0",
        "content_hash": "VARCHAR(64)",
    }
    with target_engine.begin() as connection:
        for name, definition in additions.items():
            if name not in existing:
                connection.execute(
                    text(f"ALTER TABLE analysis_runs ADD COLUMN {name} {definition}")
                )
        connection.execute(
            text(
                "UPDATE analysis_runs SET created_at=COALESCE(created_at, started_at), "
                "queued_at=COALESCE(queued_at, started_at), "
                "run_started_at=CASE WHEN status='queued' THEN NULL "
                "ELSE COALESCE(run_started_at, started_at) END"
            )
        )
    scene_columns = (
        {column["name"] for column in inspect(target_engine).get_columns("scenes")}
        if "scenes" in inspect(target_engine).get_table_names()
        else set()
    )
    if scene_columns and "boundary_detected" not in scene_columns:
        with target_engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE scenes ADD COLUMN boundary_detected BOOLEAN NOT NULL DEFAULT 0")
            )
    invocation_columns = (
        {column["name"] for column in inspect(target_engine).get_columns("model_invocations")}
        if "model_invocations" in inspect(target_engine).get_table_names()
        else set()
    )
    invocation_additions = {
        "invocation_kind": "VARCHAR(32) NOT NULL DEFAULT 'initial'",
        "http_status_code": "INTEGER",
        "response_model_name": "VARCHAR(255)",
        "structured_output_mode": "VARCHAR(32)",
        "schema_hash": "VARCHAR(64)",
        "grammar_hash": "VARCHAR(64)",
        "thinking_enabled": "BOOLEAN NOT NULL DEFAULT 0",
        "thinking_control_method": "VARCHAR(100)",
        "request_parameters_json": "TEXT",
        "is_cloud": "BOOLEAN NOT NULL DEFAULT 0",
        "cloud_provider": "VARCHAR(64)",
        "cloud_region": "VARCHAR(32)",
        "sends_content_to_cloud": "BOOLEAN NOT NULL DEFAULT 0",
        "input_tokens": "INTEGER",
        "output_tokens": "INTEGER",
        "total_tokens": "INTEGER",
        "cached_tokens": "INTEGER",
        "request_id": "VARCHAR(255)",
        "estimated_cost": "FLOAT",
        "currency": "VARCHAR(16)",
        "pricing_version": "VARCHAR(64)",
        "raw_logging_enabled": "BOOLEAN NOT NULL DEFAULT 0",
        "content_hash": "VARCHAR(64)",
    }
    if invocation_columns:
        with target_engine.begin() as connection:
            for name, definition in invocation_additions.items():
                if name not in invocation_columns:
                    connection.execute(
                        text(f"ALTER TABLE model_invocations ADD COLUMN {name} {definition}")
                    )


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def get_session_factory() -> sessionmaker[Session]:
    return SessionLocal
