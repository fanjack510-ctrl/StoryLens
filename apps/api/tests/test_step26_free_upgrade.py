"""STEP 2.6 — 1.0.5-like upgrade via formal create_db / narrative migration path.

Uses a temporary SQLite file only. No Live Provider. No user database.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AnalysisRun, Base, Book, Chapter, Paragraph, ReaderJourneyRun
from app.narrative_core.migrations.runner import apply_narrative_migrations


def _fk_engine(url: str):
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _counts(connection) -> dict[str, int]:
    out: dict[str, int] = {}
    for table in (
        "books",
        "chapters",
        "paragraphs",
        "analysis_runs",
        "reader_journey_runs",
        "scenes",
    ):
        names = set(inspect(connection.engine).get_table_names())
        if table not in names:
            out[table] = 0
            continue
        out[table] = int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
    return out


def test_step26_create_all_then_migrations_repeat_startup(tmp_path: Path):
    """Formal path: create_all + apply_narrative_migrations twice (repeat startup)."""

    db = tmp_path / "step26_upgrade.db"
    engine = _fk_engine(f"sqlite:///{db}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with factory() as session:
        book = Book(
            title="Free回归书",
            source_file_name="free.txt",
            source_file_hash="hash-step26-upgrade",
            import_status="ready",
        )
        session.add(book)
        session.flush()
        chapter = Chapter(
            book_id=book.id,
            chapter_index=1,
            title="第一章",
            chapter_title="第一章",
            display_title="第一章",
            section_type="chapter",
        )
        session.add(chapter)
        session.flush()
        para = Paragraph(
            id=f"B{book.id:04d}-C0001-P0001",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=1,
            raw_text="旧段落正文。",
            normalized_text="旧段落正文。",
            char_start=0,
            char_end=6,
        )
        session.add(para)
        run = AnalysisRun(
            task_type="scene_pipeline",
            subject_type="chapter",
            subject_id=str(chapter.id),
            provider="aliyun_qwen_plus",
            model="qwen3.7-plus",
            prompt_version="v1",
            schema_version="1",
            input_hash="old-run",
            status="succeeded",
        )
        session.add(run)
        session.flush()
        session.add(
            ReaderJourneyRun(
                analysis_run_id=run.id,
                book_id=book.id,
                chapter_id=chapter.id,
                status="succeeded",
                provider_name="aliyun_qwen_plus",
                model_name="qwen3.7-plus",
                client_request_id="step26-rj-1",
            )
        )
        session.commit()
        before = {
            "books": int(session.execute(text("SELECT COUNT(*) FROM books")).scalar() or 0),
            "chapters": int(session.execute(text("SELECT COUNT(*) FROM chapters")).scalar() or 0),
            "paragraphs": int(
                session.execute(text("SELECT COUNT(*) FROM paragraphs")).scalar() or 0
            ),
            "analysis_runs": int(
                session.execute(text("SELECT COUNT(*) FROM analysis_runs")).scalar() or 0
            ),
            "reader_journey_runs": int(
                session.execute(text("SELECT COUNT(*) FROM reader_journey_runs")).scalar() or 0
            ),
        }

    apply_narrative_migrations(engine)
    apply_narrative_migrations(engine)  # repeat startup

    names = set(inspect(engine).get_table_names())
    assert "whole_book_run_windows" in names
    assert "whole_book_run_state_versions" in names

    with engine.connect() as connection:
        after = {
            "books": connection.execute(text("SELECT COUNT(*) FROM books")).scalar(),
            "chapters": connection.execute(text("SELECT COUNT(*) FROM chapters")).scalar(),
            "paragraphs": connection.execute(text("SELECT COUNT(*) FROM paragraphs")).scalar(),
            "analysis_runs": connection.execute(
                text("SELECT COUNT(*) FROM analysis_runs")
            ).scalar(),
            "reader_journey_runs": connection.execute(
                text("SELECT COUNT(*) FROM reader_journey_runs")
            ).scalar(),
        }
        assert after == before
        status = connection.execute(
            text("SELECT status FROM analysis_runs LIMIT 1")
        ).scalar()
        assert status == "succeeded"
        journey = connection.execute(
            text("SELECT status FROM reader_journey_runs LIMIT 1")
        ).scalar()
        assert journey == "succeeded"

    # Ensure only one sqlite file (no second DB created by migrations).
    siblings = list(tmp_path.glob("*.db"))
    assert siblings == [db]


def test_step26_simulated_1_0_5_core_upgrade_preserves_counts(tmp_path: Path):
    """Reuse contract upgrade simulation as STEP 2.6 directed gate."""

    from tests.test_whole_book_overview_contract_v1 import (
        test_minimal_1_0_5_like_upgrade_preserves_counts,
    )

    test_minimal_1_0_5_like_upgrade_preserves_counts(tmp_path)
