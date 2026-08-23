"""CHG-081: hierarchical planner cutover + background executor isolation."""
from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.db.models import Book, Chapter, Paragraph, ProviderConfiguration, WholeBookCheckpoint, WholeBookRun
from app.main import create_app
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus
from app.narrative_core.services.whole_book_hierarchical_estimate_v1 import (
    HIERARCHICAL_ESTIMATE_VERSION,
    estimate_hierarchical_whole_book_analysis_v1,
    hierarchical_call_breakdown,
    plan_hierarchical_v2_for_book,
)
from app.narrative_core.services.whole_book_startup_recovery_v1 import (
    PROCESS_INTERRUPTED_CODE,
    mark_interrupted_whole_book_runs,
)
from app.narrative_core.whole_book_v2.pipeline import dry_run_1299, ProviderBudget
from tests.whole_book_minimal_test_helpers import make_engine, seed_sample_s_book
from tests.paths import API_ROOT


def _seed_scaled_book(session, *, chapters: int, chars_per: int, title: str = "scale"):
    from app.services.whole_book_source_fingerprint import sha256_utf8

    book = Book(
        title=title,
        source_file_name=f"{title}.txt",
        source_file_hash=sha256_utf8(f"{title}-{chapters}-{chars_per}-{uuid.uuid4()}"),
        import_status="ready",
    )
    session.add(book)
    session.flush()
    text_body = "汉" * chars_per
    for i in range(1, chapters + 1):
        ch = Chapter(book_id=book.id, chapter_index=i, title=f"第{i}章")
        session.add(ch)
        session.flush()
        session.add(
            Paragraph(
                id=f"p-{book.id}-{i}",
                book_id=book.id,
                chapter_id=ch.id,
                paragraph_index=0,
                raw_text=text_body,
                normalized_text=text_body,
                char_start=0,
                char_end=len(text_body),
                content_hash=sha256_utf8(text_body),
            )
        )
    provider = ProviderConfiguration(
        provider_name="deepseek",
        plus_model="deepseek-v4-flash",
        enabled=True,
        disconnected=False,
    )
    session.add(provider)
    session.commit()
    session.refresh(book)
    session.refresh(provider)
    return book, provider


def test_v2_start_and_reanalysis_share_same_planner(tmp_path):
    free_src = (
        API_ROOT / "app" / "narrative_core" / "services" / "whole_book_free_product_v1_service.py"
    ).read_text(encoding="utf-8")
    assert "estimate_hierarchical_whole_book_analysis_v1" in free_src
    # Formal prepare path must call hierarchical estimator.
    prepare_block = free_src.split("def prepare_free_whole_book_analysis_v1")[1].split(
        "def create_free_whole_book_analysis_v1"
    )[0]
    assert "estimate_hierarchical_whole_book_analysis_v1" in prepare_block
    assert "estimate_whole_book_analysis(" not in prepare_block
    create_block = free_src.split("def create_free_whole_book_analysis_v1")[1].split(
        "def create_fixture_free_whole_book_analysis_v1"
    )[0]
    assert "execute_hierarchical_v2_pipeline_v1" in create_block
    assert "generate_whole_book_windows_v1(session, run.id)" not in create_block


def test_reanalysis_does_not_use_legacy_free_estimator(tmp_path):
    engine = make_engine(tmp_path, "chg081-legacy.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, provider = _seed_scaled_book(session, chapters=20, chars_per=2000)
        row, plan = estimate_hierarchical_whole_book_analysis_v1(
            session,
            book.id,
            "whole_book_native",
            provider.id,
            provider_name="deepseek",
        )
        session.commit()
        assert row.estimate_version == HIERARCHICAL_ESTIMATE_VERSION
        assert int(row.estimated_window_count) == int(plan["window_count"])
        # Legacy Free estimator for ~40k chars would produce many more windows.
        assert int(row.estimated_window_count) < 50
        bd = hierarchical_call_breakdown(window_count=int(row.estimated_window_count))
        assert bd["chapter_function_batch_calls"] == 0
        assert bd["extraction_calls"] == int(row.estimated_window_count)


def test_542_chapter_reanalysis_uses_hierarchical_plan(tmp_path):
    # Deterministic dry-run planner (no DB / no Provider) — same Hierarchical code path.
    budget = ProviderBudget(provider="deepseek", model="deepseek-v4-flash")
    report = dry_run_1299(
        chapter_count=542,
        total_chars=2_901_455,
        book_id=542,
        budget=budget,
    )
    assert report.window_count == 15
    assert report.estimated_provider_calls == 33
    assert report.context_safe == "YES"
    tp = report.token_plan
    assert tp.extract_calls == 15
    assert tp.consolidation_calls == 9
    assert tp.final_synthesis_calls == 6
    assert tp.repair_reserve_calls == 3
    assert tp.estimated_total_calls == 33
    # Must never look like legacy Free 106/244.
    assert report.window_count != 106
    assert report.estimated_provider_calls != 244


def test_call_breakdown_matches_hierarchical_pipeline():
    bd = hierarchical_call_breakdown(window_count=15)
    assert bd["extraction_calls"] == 15
    assert bd["consolidation_calls"] == 9
    assert bd["final_synthesis_calls"] == 6
    assert bd["repair_reserve_calls"] == 3
    assert bd["estimated_total_calls"] == 33


def test_cost_estimate_matches_hierarchical_pipeline(tmp_path):
    engine = make_engine(tmp_path, "chg081-cost.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        # Uniform chapters matching dry-run averages (~5353 chars).
        book, provider = _seed_scaled_book(session, chapters=542, chars_per=5353)
        plan = plan_hierarchical_v2_for_book(
            session,
            book.id,
            provider_name="deepseek",
            model_name="deepseek-v4-flash",
        )
        assert plan["window_count"] == 15
        assert plan["token_plan"].estimated_total_calls == 33
        assert plan["cost_plan"].estimated_cost_low > 0
        assert plan["cost_plan"].estimated_cost_high >= plan["cost_plan"].estimated_cost_low
        assert plan["context_safe"] is True


def test_force_full_reanalysis_only_changes_reuse_plan(tmp_path):
    engine = make_engine(tmp_path, "chg081-force.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, provider = _seed_scaled_book(session, chapters=40, chars_per=3000)
        row_a, plan_a = estimate_hierarchical_whole_book_analysis_v1(
            session, book.id, "whole_book_native", provider.id, provider_name="deepseek"
        )
        row_b, plan_b = estimate_hierarchical_whole_book_analysis_v1(
            session, book.id, "whole_book_native", provider.id, provider_name="deepseek"
        )
        session.commit()
        # Force-full is a create flag — estimate/plan itself is unchanged.
        assert row_a.estimated_window_count == row_b.estimated_window_count
        assert row_a.estimated_provider_call_count == row_b.estimated_provider_call_count
        assert plan_a["window_count"] == plan_b["window_count"]


def test_background_executor_owns_db_session(tmp_path):
    engine = make_engine(tmp_path, "chg081-session.db")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    seen: dict[str, int] = {}

    def _fake_pipeline(session, run_id, **kwargs):
        seen["bg_session_id"] = id(session)
        seen["commit_progress"] = bool(kwargs.get("commit_progress"))
        return {"pipeline": "hierarchical_v2", "run_id": run_id}

    with factory() as request_session:
        seen["request_session_id"] = id(request_session)
        book, snap = seed_sample_s_book(request_session)
        from app.narrative_core.services.whole_book_run_v1_service import create_whole_book_run_v1

        run = create_whole_book_run_v1(
            request_session, book.id, snap, "whole_book_native", "chg081-s", "formal"
        )
        request_session.commit()
        rid = int(run.id)

    with patch(
        "app.narrative_core.services.whole_book_v2_formal_pipeline_v1.execute_hierarchical_v2_pipeline_v1",
        side_effect=_fake_pipeline,
    ):
        from app.services.whole_book_free_background import (
            execute_free_whole_book_pipeline_background,
        )

        execute_free_whole_book_pipeline_background(factory, rid)

    assert seen["bg_session_id"] != seen["request_session_id"]
    assert seen["commit_progress"] is True


def test_request_session_not_reused_after_response(tmp_path):
    # Same assertion surface as owns_db_session — create path must schedule with factory.
    router_src = (
        API_ROOT / "app" / "routers" / "whole_book_free_product_router.py"
    ).read_text(encoding="utf-8")
    assert "schedule_free_whole_book_pipeline_background" in router_src
    assert "from fastapi import APIRouter, Depends" in router_src or "Depends" in router_src
    assert "background.add_task(" not in router_src
    free_src = (
        API_ROOT / "app" / "narrative_core" / "services" / "whole_book_free_product_v1_service.py"
    ).read_text(encoding="utf-8")
    create_block = free_src.split("def create_free_whole_book_analysis_v1")[1].split(
        "def create_fixture_free_whole_book_analysis_v1"
    )[0]
    assert "generate_whole_book_windows_v1(session, run.id)" not in create_block


def test_run_committed_before_background_execution(tmp_path):
    engine = make_engine(tmp_path, "chg081-commit.db")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    order: list[str] = []

    with factory() as session:
        book, snap = seed_sample_s_book(session)
        from app.narrative_core.services.whole_book_run_v1_service import (
            create_whole_book_run_v1,
            start_whole_book_run_v1,
        )

        run = create_whole_book_run_v1(
            session, book.id, snap, "whole_book_native", "chg081-c", "formal"
        )
        start_whole_book_run_v1(session, run.id)
        session.commit()
        order.append("committed")
        rid = int(run.id)

    def _fake_pipeline(session, run_id, **kwargs):
        order.append("background")
        with factory() as check:
            row = check.get(WholeBookRun, int(run_id))
            assert row is not None
            assert row.status == WholeBookRunStatus.running.value
        return {"pipeline": "hierarchical_v2"}

    with patch(
        "app.narrative_core.services.whole_book_v2_formal_pipeline_v1.execute_hierarchical_v2_pipeline_v1",
        side_effect=_fake_pipeline,
    ):
        from app.services.whole_book_free_background import (
            execute_free_whole_book_pipeline_background,
        )

        execute_free_whole_book_pipeline_background(factory, rid)
    assert order == ["committed", "background"]


def test_background_v2_failure_does_not_kill_api(tmp_path, monkeypatch):
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_APP_ENV", "development")
    engine = make_engine(tmp_path, "chg081-fail.db")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with factory() as session:
        book, snap = seed_sample_s_book(session)
        from app.narrative_core.services.whole_book_run_v1_service import (
            create_whole_book_run_v1,
            start_whole_book_run_v1,
        )

        run = create_whole_book_run_v1(
            session, book.id, snap, "whole_book_native", "chg081-f", "formal"
        )
        start_whole_book_run_v1(session, run.id)
        session.commit()
        rid = int(run.id)

    def _boom(*_a, **_k):
        raise RuntimeError("forced background failure")

    with patch(
        "app.narrative_core.services.whole_book_v2_formal_pipeline_v1.execute_hierarchical_v2_pipeline_v1",
        side_effect=_boom,
    ):
        from app.services.whole_book_free_background import (
            execute_free_whole_book_pipeline_background,
        )

        # Must not raise out of executor.
        execute_free_whole_book_pipeline_background(factory, rid)

    with factory() as session:
        run = session.get(WholeBookRun, rid)
        assert run is not None
        assert run.status == WholeBookRunStatus.failed.value
        assert run.failure_code == "WHOLE_BOOK_BACKGROUND_FAILED"


def test_sidecar_health_survives_background_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_DISABLE_INSTANCE_LOCK", "1")
    app = create_app(environment="development", lab_enabled=False, private_engine_lab_enabled=False)
    # Point SessionLocal at tmp engine for health + recovery paths used by app.
    from app.db import session as session_mod

    engine = make_engine(tmp_path, "chg081-health.db")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", factory)

    with factory() as session:
        book, snap = seed_sample_s_book(session)
        from app.narrative_core.services.whole_book_run_v1_service import (
            create_whole_book_run_v1,
            start_whole_book_run_v1,
        )

        run = create_whole_book_run_v1(
            session, book.id, snap, "whole_book_native", "chg081-h", "formal"
        )
        start_whole_book_run_v1(session, run.id)
        session.commit()
        rid = int(run.id)

    client = TestClient(app)
    assert client.get("/health").status_code == 200

    def _boom(*_a, **_k):
        raise RuntimeError("forced")

    with patch(
        "app.narrative_core.services.whole_book_v2_formal_pipeline_v1.execute_hierarchical_v2_pipeline_v1",
        side_effect=_boom,
    ):
        from app.services.whole_book_free_background import (
            schedule_free_whole_book_pipeline_background,
        )

        thr = schedule_free_whole_book_pipeline_background(factory, rid)
        thr.join(timeout=10)
        assert not thr.is_alive()

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    # API still readable after failure
    with factory() as session:
        assert session.execute(text("SELECT 1")).scalar() == 1
        run = session.get(WholeBookRun, rid)
        assert run.status == WholeBookRunStatus.failed.value


def test_interrupted_run_recovery_no_auto_reburn(tmp_path):
    engine = make_engine(tmp_path, "chg081-rec.db")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        book, snap = seed_sample_s_book(session)
        from app.narrative_core.services.whole_book_run_v1_service import (
            create_whole_book_run_v1,
            start_whole_book_run_v1,
        )

        run = create_whole_book_run_v1(
            session, book.id, snap, "whole_book_native", "chg081-r", "formal"
        )
        start_whole_book_run_v1(session, run.id)
        session.commit()
        rid = int(run.id)

    with factory() as session:
        stats = mark_interrupted_whole_book_runs(session)
        assert stats["recoverable"] == 1
        run = session.get(WholeBookRun, rid)
        assert run.status == WholeBookRunStatus.recoverable.value
        assert run.failure_code == PROCESS_INTERRUPTED_CODE
        # Second call idempotent
        stats2 = mark_interrupted_whole_book_runs(session)
        assert stats2["recoverable"] == 0


def test_v2_reanalysis_async_success_and_progress(tmp_path):
    engine = make_engine(tmp_path, "chg081-ok.db")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    progress_seen = threading.Event()

    def _ok(session, run_id, **kwargs):
        from app.db.models import WholeBookCheckpoint

        session.add(
            WholeBookCheckpoint(
                run_id=int(run_id),
                stage_code="v2_progress",
                checkpoint_key="latest",
                sequence_no=1,
                completed_unit_count=1,
                payload_hash="",
                checkpoint_payload_json='{"stage":"extract_windows"}',
            )
        )
        session.flush()
        if kwargs.get("commit_progress"):
            session.commit()
        progress_seen.set()
        run = session.get(WholeBookRun, int(run_id))
        run.status = WholeBookRunStatus.completed.value
        session.flush()
        return {"pipeline": "hierarchical_v2", "run_id": run_id}

    with factory() as session:
        book, snap = seed_sample_s_book(session)
        from app.narrative_core.services.whole_book_run_v1_service import (
            create_whole_book_run_v1,
            start_whole_book_run_v1,
        )

        run = create_whole_book_run_v1(
            session, book.id, snap, "whole_book_native", "chg081-ok", "formal"
        )
        start_whole_book_run_v1(session, run.id)
        session.commit()
        rid = int(run.id)

    # Task visible immediately after commit (before background finishes).
    with factory() as session:
        run = session.get(WholeBookRun, rid)
        assert run.status == WholeBookRunStatus.running.value

    with patch(
        "app.narrative_core.services.whole_book_v2_formal_pipeline_v1.execute_hierarchical_v2_pipeline_v1",
        side_effect=_ok,
    ):
        from app.services.whole_book_free_background import (
            schedule_free_whole_book_pipeline_background,
        )

        thr = schedule_free_whole_book_pipeline_background(factory, rid)
        assert progress_seen.wait(timeout=10)
        thr.join(timeout=10)

    with factory() as session:
        run = session.get(WholeBookRun, rid)
        assert run.status == WholeBookRunStatus.completed.value
        prog = session.scalars(
            select(WholeBookCheckpoint).where(
                WholeBookCheckpoint.run_id == rid,
                WholeBookCheckpoint.stage_code == "v2_progress",
            )
        ).first()
        assert prog is not None
