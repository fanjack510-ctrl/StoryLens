"""WB-0.4 — whole_book_foundation_v1 migration tests (isolated tmp_path only)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine

from app.db.models import Base
from app.narrative_core.errors import NarrativeCoreError
from app.narrative_core.migrations import MIGRATION_WHOLE_BOOK_FOUNDATION_V1, migration_checksum
from app.narrative_core.migrations.runner import (
    SQL_012,
    apply_narrative_migrations,
    migrate_narrative_20260728_012_whole_book_foundation_v1,
)

_WB012_TABLES = (
    "whole_book_cost_estimates",
    "whole_book_consents",
    "whole_book_runs",
    "whole_book_run_stages",
    "whole_book_checkpoints",
    "whole_book_windows",
    "whole_book_provider_units",
    "whole_book_provider_attempts",
)

_REQUIRED_INDEXES: dict[str, tuple[str, ...]] = {
    "whole_book_cost_estimates": (
        "ix_wb_cost_estimates_book_created",
        "ix_whole_book_cost_estimates_book_id",
    ),
    "whole_book_consents": (
        "ix_wb_consents_book_accepted",
        "ix_whole_book_consents_book_id",
    ),
    "whole_book_runs": (
        "ix_wb_runs_book_status",
        "ix_wb_runs_snapshot",
    ),
    "whole_book_run_stages": ("ix_wb_run_stages_run_sequence",),
    "whole_book_windows": ("ix_wb_windows_run_status",),
    "whole_book_provider_units": (
        "ix_wb_provider_units_run_status",
        "ix_wb_provider_units_idempotency",
    ),
    "whole_book_provider_attempts": ("ix_wb_provider_attempts_unit_attempt",),
    "book_snapshot_paragraphs": ("ix_book_snapshot_paragraphs_global_paragraph_index",),
}

_REQUIRED_UNIQUE_COLUMNS: dict[str, tuple[tuple[str, ...], ...]] = {
    "whole_book_runs": (("idempotency_key",),),
    "whole_book_run_stages": (("run_id", "stage_code"),),
    "whole_book_checkpoints": (("run_id", "stage_code", "checkpoint_key"),),
    "whole_book_windows": (("run_id", "window_index"),),
    "whole_book_provider_units": (
        ("run_id", "stage_code", "unit_key"),
        ("idempotency_key",),
    ),
    "whole_book_provider_attempts": (("provider_unit_id", "attempt_no"),),
}


def _fk_engine(database_url: str) -> Engine:
    engine = create_engine(database_url)

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _index_names(engine: Engine, table: str) -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(text(f"PRAGMA index_list({table!r})")).fetchall()
    return {str(row[1]) for row in rows}


def _unique_column_sets(engine: Engine, table: str) -> set[tuple[str, ...]]:
    uniques: set[tuple[str, ...]] = set()
    with engine.connect() as connection:
        for row in connection.execute(text(f"PRAGMA index_list({table!r})")).fetchall():
            if int(row[2]) != 1:
                continue
            index_name = str(row[1])
            info = connection.execute(text(f"PRAGMA index_info({index_name!r})")).fetchall()
            columns = tuple(str(part[2]) for part in sorted(info, key=lambda item: item[1]))
            uniques.add(columns)
    return uniques


def _migration_row(engine: Engine, migration_id: str) -> tuple[str, str] | None:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT migration_id, checksum FROM schema_migrations "
                "WHERE migration_id = :migration_id"
            ),
            {"migration_id": migration_id},
        ).fetchone()
    if row is None:
        return None
    return str(row[0]), str(row[1])


def test_empty_db_apply_narrative_migrations_creates_wb012(tmp_path) -> None:
    db_path = tmp_path / "fresh.db"
    engine = _fk_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    apply_narrative_migrations(engine)

    names = set(inspect(engine).get_table_names())
    for table in _WB012_TABLES:
        assert table in names

    snapshot_cols = {c["name"] for c in inspect(engine).get_columns("book_snapshots")}
    assert {"snapshot_version", "completed_at"} <= snapshot_cols
    paragraph_cols = {c["name"] for c in inspect(engine).get_columns("book_snapshot_paragraphs")}
    assert "global_paragraph_index" in paragraph_cols

    row = _migration_row(engine, MIGRATION_WHOLE_BOOK_FOUNDATION_V1)
    assert row is not None
    assert row[1] == migration_checksum(SQL_012)
    engine.dispose()


def test_second_upgrade_is_no_op(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'idem.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_migrations(engine)
    tables_first = sorted(inspect(engine).get_table_names())
    row_first = _migration_row(engine, MIGRATION_WHOLE_BOOK_FOUNDATION_V1)

    apply_narrative_migrations(engine)
    migrate_narrative_20260728_012_whole_book_foundation_v1(engine)

    tables_second = sorted(inspect(engine).get_table_names())
    row_second = _migration_row(engine, MIGRATION_WHOLE_BOOK_FOUNDATION_V1)
    assert tables_first == tables_second
    assert row_first == row_second
    engine.dispose()


def test_failure_injection_rolls_back_ddl_and_skips_ledger(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'fail.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for table in reversed(_WB012_TABLES):
            connection.execute(text(f"DROP TABLE IF EXISTS {table}"))

    @event.listens_for(engine, "before_cursor_execute")
    def _inject_failure(
        _conn, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        if "CREATE TABLE whole_book_cost_estimates" in statement:
            raise RuntimeError("injected wb012 failure")

    try:
        with pytest.raises(NarrativeCoreError):
            migrate_narrative_20260728_012_whole_book_foundation_v1(engine)
    finally:
        event.remove(engine, "before_cursor_execute", _inject_failure)

    inspect(engine).clear_cache()
    names = set(inspect(engine).get_table_names())
    for table in _WB012_TABLES:
        assert table not in names
    assert _migration_row(engine, MIGRATION_WHOLE_BOOK_FOUNDATION_V1) is None
    engine.dispose()


def test_target_tables_indexes_and_uniques_exist(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'idx.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for table in reversed(_WB012_TABLES):
            connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
    apply_narrative_migrations(engine)

    for table, required in _REQUIRED_INDEXES.items():
        present = _index_names(engine, table)
        for index_name in required:
            assert index_name in present, f"{table} missing index {index_name}"

    for table, required_uniques in _REQUIRED_UNIQUE_COLUMNS.items():
        present_uniques = _unique_column_sets(engine, table)
        for columns in required_uniques:
            assert columns in present_uniques, f"{table} missing unique on {columns}"

    engine.dispose()


def test_uses_tmp_path_not_formal_appdata(tmp_path, monkeypatch) -> None:
    """Guard: migration tests must not touch production AppData paths."""
    formal = tmp_path / "would_be_appdata"
    formal.mkdir()
    monkeypatch.setenv("STORYLENS_DATABASE_URL", f"sqlite:///{formal / 'must_not_be_used.db'}")
    # Explicit tmp_path engine only — no session.create_db().
    isolated = tmp_path / "isolated_wb012.db"
    engine = _fk_engine(f"sqlite:///{isolated}")
    Base.metadata.create_all(engine)
    apply_narrative_migrations(engine)
    assert isolated.exists()
    assert not (formal / "must_not_be_used.db").exists()
    engine.dispose()
