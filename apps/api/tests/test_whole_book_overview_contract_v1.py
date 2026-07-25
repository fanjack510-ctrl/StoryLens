"""STEP 2.1 — Native Whole-Book Overview contract / migration freeze tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisRun,
    Base,
    Book,
    WholeBookRunStateVersion,
    WholeBookRunWindow,
)
from app.narrative_core.contracts.whole_book_overview_errors import (
    WHOLE_BOOK_OVERVIEW_ERROR_META,
    WholeBookOverviewErrorCode,
    overview_error_payload,
)
from app.narrative_core.contracts.whole_book_overview_fixture_hash import (
    CONTRACT_VERSION as FIXTURE_CONTRACT_VERSION,
    default_public_fixture_dir,
    verify_fixture_manifest,
)
from app.narrative_core.contracts.whole_book_overview_state_machine import (
    is_allowed_overview_run_transition,
    is_allowed_overview_stage_transition,
    is_allowed_window_transition,
    validate_overview_run_transition,
    validate_overview_stage_transition,
    validate_window_transition,
)
from app.narrative_core.contracts.whole_book_overview_v1 import (
    CONTRACT_VERSION,
    CreateRunRequest,
    CreateRunResponse,
    ErrorEnvelope,
    OverviewApiResponse,
    PreflightResponse,
    RunStatusResponse,
    WholeBookOverviewProjectionCandidateV1,
    WholeBookOverviewSynthesisInputV1,
    WholeBookOverviewWindowInputV1,
    WholeBookOverviewWindowResultV1,
)
from app.narrative_core.enums import (
    OverviewFieldStatus,
    OverviewProductionStageKey,
    RunStatus,
    StageStatus,
    WindowStatus,
)
from app.narrative_core.migrations import (
    MIGRATION_WHOLE_BOOK_OVERVIEW_RUNTIME,
    NARRATIVE_MIGRATION_ORDER,
    assert_unique_migration_ids,
)
from app.narrative_core.migrations.runner import (
    apply_narrative_migrations,
    apply_narrative_overview_migrations,
    migrate_narrative_20260725_011_whole_book_overview_runtime,
)


FIXTURE_DIR = default_public_fixture_dir()

DTO_FIXTURE_MAP = {
    "preflight_response.json": PreflightResponse,
    "create_run_request.json": CreateRunRequest,
    "create_run_response.json": CreateRunResponse,
    "run_status_analyzing.json": RunStatusResponse,
    "run_status_failed.json": RunStatusResponse,
    "window_input.json": WholeBookOverviewWindowInputV1,
    "window_result.json": WholeBookOverviewWindowResultV1,
    "synthesis_input.json": WholeBookOverviewSynthesisInputV1,
    "projection_candidate.json": WholeBookOverviewProjectionCandidateV1,
    "overview_api_response.json": OverviewApiResponse,
}


def _fk_engine(url: str):
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_migration_order_includes_011() -> None:
    assert_unique_migration_ids()
    assert len(NARRATIVE_MIGRATION_ORDER) == 11
    assert NARRATIVE_MIGRATION_ORDER[-1] == MIGRATION_WHOLE_BOOK_OVERVIEW_RUNTIME
    assert NARRATIVE_MIGRATION_ORDER[9] == "20260723_010_analysis_conflicts"


def test_fixture_manifest_hashes() -> None:
    manifest = verify_fixture_manifest(FIXTURE_DIR)
    assert manifest["contract_version"] == FIXTURE_CONTRACT_VERSION
    assert manifest["contract_version"] == CONTRACT_VERSION
    assert "combined_sha256" in manifest
    for required in DTO_FIXTURE_MAP:
        assert required in manifest["files"]
    assert "error_cases.json" in manifest["files"]
    assert "invalid_evidence.json" in manifest["files"]


@pytest.mark.parametrize("filename,model", sorted(DTO_FIXTURE_MAP.items()))
def test_dto_round_trip_from_fixtures(filename: str, model) -> None:
    payload = _load_fixture(filename)
    parsed = model.model_validate(payload)
    dumped = parsed.model_dump(mode="json")
    again = model.model_validate(dumped)
    assert again.model_dump(mode="json") == dumped


def test_error_schema_and_meta_complete() -> None:
    assert len(WholeBookOverviewErrorCode) == 28
    assert set(WHOLE_BOOK_OVERVIEW_ERROR_META) == set(WholeBookOverviewErrorCode)

    cases = _load_fixture("error_cases.json")["cases"]
    for case in cases:
        envelope = ErrorEnvelope.model_validate(case)
        code = envelope.error.code
        meta = WHOLE_BOOK_OVERVIEW_ERROR_META[code]
        assert envelope.error.retryable == meta["retryable"]
        built = overview_error_payload(
            code,
            run_id=envelope.error.run_id,
            stage_key=envelope.error.stage_key,
            window_index=envelope.error.window_index,
            details=envelope.error.details,
        )
        ErrorEnvelope.model_validate(built)


def test_run_stage_window_transitions_allow_deny() -> None:
    assert is_allowed_overview_run_transition(RunStatus.PENDING, RunStatus.PREPARING)
    assert is_allowed_overview_run_transition(RunStatus.MATERIALIZING, RunStatus.ANALYZING)
    assert is_allowed_overview_run_transition(RunStatus.SYNTHESIZING, RunStatus.COMPLETED)
    assert not is_allowed_overview_run_transition(RunStatus.COMPLETED, RunStatus.ANALYZING)
    assert not is_allowed_overview_run_transition(RunStatus.FAILED, RunStatus.COMPLETED)
    with pytest.raises(ValueError):
        validate_overview_run_transition(RunStatus.COMPLETED, RunStatus.FAILED)

    assert is_allowed_overview_stage_transition(StageStatus.PENDING, StageStatus.RUNNING)
    assert is_allowed_overview_stage_transition(StageStatus.FAILED, StageStatus.RUNNING)
    assert not is_allowed_overview_stage_transition(StageStatus.COMPLETED, StageStatus.RUNNING)
    with pytest.raises(ValueError):
        validate_overview_stage_transition(StageStatus.COMPLETED, StageStatus.FAILED)

    assert is_allowed_window_transition(WindowStatus.PENDING, WindowStatus.RUNNING)
    assert is_allowed_window_transition(WindowStatus.FAILED, WindowStatus.RUNNING)
    assert not is_allowed_window_transition(WindowStatus.COMPLETED, WindowStatus.RUNNING)
    with pytest.raises(ValueError):
        validate_window_transition(WindowStatus.COMPLETED, WindowStatus.FAILED)

    assert list(OverviewProductionStageKey)[0] == OverviewProductionStageKey.SNAPSHOT_PREFLIGHT
    assert OverviewFieldStatus.SUPPORTED.value == "supported"


def test_window_unique_run_id_window_index(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'win.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_overview_migrations(engine)
    with Session(engine) as session:
        book = Book(title="t", source_file_name="x.txt", source_file_hash="hash-book-win")
        session.add(book)
        session.flush()
        run = AnalysisRun(
            provider="p",
            model="m",
            prompt_version="1",
            schema_version="1",
            input_hash="h",
            book_id=book.id,
            status=RunStatus.PENDING.value,
        )
        session.add(run)
        session.flush()
        session.add(
            WholeBookRunWindow(
                run_id=run.id,
                window_index=0,
                input_hash="hash-a",
                status=WindowStatus.PENDING.value,
            )
        )
        session.commit()
        session.add(
            WholeBookRunWindow(
                run_id=run.id,
                window_index=0,
                input_hash="hash-b",
                status=WindowStatus.PENDING.value,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_state_version_unique_run_id_version_number(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'sv.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_overview_migrations(engine)
    with Session(engine) as session:
        book = Book(title="t", source_file_name="y.txt", source_file_hash="hash-book-sv")
        session.add(book)
        session.flush()
        run = AnalysisRun(
            provider="p",
            model="m",
            prompt_version="1",
            schema_version="1",
            input_hash="h",
            book_id=book.id,
            status=RunStatus.ANALYZING.value,
        )
        session.add(run)
        session.flush()
        session.add(
            WholeBookRunStateVersion(
                run_id=run.id,
                version_number=1,
                state_json="{}",
                state_hash="s1",
            )
        )
        session.commit()
        session.add(
            WholeBookRunStateVersion(
                run_id=run.id,
                version_number=1,
                state_json="{}",
                state_hash="s2",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_empty_db_create_all_and_migrations_create_tables(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_migrations(engine)
    names = set(inspect(engine).get_table_names())
    assert "whole_book_run_windows" in names
    assert "whole_book_run_state_versions" in names
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT migration_id FROM schema_migrations WHERE migration_id = :mid"),
            {"mid": MIGRATION_WHOLE_BOOK_OVERVIEW_RUNTIME},
        ).fetchall()
    assert len(rows) == 1


def test_migration_011_idempotent_reapply(tmp_path) -> None:
    engine = _fk_engine(f"sqlite:///{tmp_path / 'idem.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_overview_migrations(engine)
    migrate_narrative_20260725_011_whole_book_overview_runtime(engine)
    migrate_narrative_20260725_011_whole_book_overview_runtime(engine)
    apply_narrative_migrations(engine)
    names = set(inspect(engine).get_table_names())
    assert "whole_book_run_windows" in names
    assert "whole_book_run_state_versions" in names


def test_minimal_1_0_5_like_upgrade_preserves_counts(tmp_path) -> None:
    """Simulate Free-like core tables, then apply narrative migrations."""
    engine = _fk_engine(f"sqlite:///{tmp_path / 'upgrade.db'}")
    # Minimal 1.0.5-like core only (no narrative tables yet).
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE books (
                    id INTEGER NOT NULL PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    author VARCHAR(255),
                    source_type VARCHAR(32) NOT NULL,
                    source_path VARCHAR(1000) NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE chapters (
                    id INTEGER NOT NULL PRIMARY KEY,
                    book_id INTEGER NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    raw_text TEXT NOT NULL,
                    FOREIGN KEY(book_id) REFERENCES books (id) ON DELETE CASCADE
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE paragraphs (
                    id VARCHAR(32) NOT NULL PRIMARY KEY,
                    chapter_id INTEGER NOT NULL,
                    paragraph_index INTEGER NOT NULL,
                    raw_text TEXT NOT NULL,
                    normalized_text TEXT NOT NULL,
                    char_start INTEGER NOT NULL,
                    char_end INTEGER NOT NULL,
                    FOREIGN KEY(chapter_id) REFERENCES chapters (id) ON DELETE CASCADE
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE analysis_runs (
                    id INTEGER NOT NULL PRIMARY KEY,
                    task_type VARCHAR(100) NOT NULL DEFAULT 'scene_pipeline',
                    subject_type VARCHAR(50) NOT NULL DEFAULT 'chapter',
                    subject_id VARCHAR(100) NOT NULL DEFAULT '',
                    provider VARCHAR(100) NOT NULL,
                    model VARCHAR(255) NOT NULL,
                    prompt_version VARCHAR(50) NOT NULL,
                    schema_version VARCHAR(50) NOT NULL,
                    input_hash VARCHAR(64) NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'queued',
                    created_at DATETIME NOT NULL,
                    started_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO books (id, title, author, source_type, source_path, "
                "created_at, updated_at) VALUES (1, 'Free Book', NULL, 'txt', "
                "'a.txt', '2026-01-01', '2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO chapters (id, book_id, chapter_index, title, raw_text) "
                "VALUES (1, 1, 0, 'Ch1', 'hello')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO paragraphs (id, chapter_id, paragraph_index, raw_text, "
                "normalized_text, char_start, char_end) "
                "VALUES ('p1', 1, 0, 'hello', 'hello', 0, 5)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO analysis_runs (id, provider, model, prompt_version, "
                "schema_version, input_hash, status, created_at, started_at) "
                "VALUES (1, 'local', 'm', '1', '1', 'abc', 'completed', "
                "'2026-01-01', '2026-01-01')"
            )
        )

    before = {}
    with engine.connect() as connection:
        for table in ("books", "chapters", "paragraphs", "analysis_runs"):
            before[table] = connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()

    # Bring ORM columns into sync for create_all of new tables, then migrate.
    Base.metadata.create_all(engine)
    apply_narrative_migrations(engine)
    apply_narrative_migrations(engine)

    with engine.connect() as connection:
        after = {
            table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            for table in ("books", "chapters", "paragraphs", "analysis_runs")
        }
        assert after == before
        names = set(inspect(engine).get_table_names())
        assert "whole_book_run_windows" in names
        assert "whole_book_run_state_versions" in names
        # Old Free run still readable.
        status = connection.execute(
            text("SELECT status FROM analysis_runs WHERE id = 1")
        ).scalar()
        assert status == "completed"


def test_invalid_evidence_fixture_rejected() -> None:
    payload = _load_fixture("invalid_evidence.json")
    with pytest.raises(ValidationError):
        WholeBookOverviewWindowResultV1.model_validate(payload)


def test_high_confidence_field_without_evidence_rejected() -> None:
    from app.narrative_core.contracts.whole_book_overview_v1 import OverviewField

    with pytest.raises(ValidationError):
        OverviewField.model_validate(
            {
                "value": "x",
                "confidence": 0.95,
                "evidence_refs": [],
                "status": "supported",
            }
        )
