"""Phase 2B-R1 CHG-053 — Live engine provenance and status aggregation."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

if "keyring" not in sys.modules:
    _keyring = ModuleType("keyring")
    _keyring.get_password = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    _keyring.set_password = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    _keyring.delete_password = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    _keyring.get_keyring = lambda: SimpleNamespace(priority=1)  # type: ignore[attr-defined]
    _errors = ModuleType("keyring.errors")

    class KeyringError(Exception):
        pass

    class PasswordDeleteError(KeyringError):
        pass

    _errors.KeyringError = KeyringError  # type: ignore[attr-defined]
    _errors.PasswordDeleteError = PasswordDeleteError  # type: ignore[attr-defined]
    sys.modules["keyring.errors"] = _errors
    sys.modules["keyring"] = _keyring

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AnalysisRun, AnalysisRunStage, Base, Book, BookSnapshotParagraph, Chapter, Paragraph
from app.narrative_core.enums import StageStatus, WholeBookAnalysisMode, WholeBookModuleKey, WholeBookStageKey
from app.narrative_core.migrations.runner import (
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)
from app.narrative_core.product_contract.enums import WholeBookModuleStatus
from app.narrative_core.run_shell_contract.private_engine_lab import PrivateEngineLabDenyReason
from app.narrative_core.services.live_engine_kind import LiveEngineKind, classify_live_engine_kind
from app.narrative_core.services.private_engine_lab_run_service import PrivateWholeBookLabRunError
from app.narrative_core.services.private_engine_signature import is_fake_or_test_engine_id
from app.narrative_core.services.private_lab_run_executor import PrivateLabRunExecutor
from app.narrative_core.services.private_whole_book_analysis_runtime import (
    create_lab_private_whole_book_analysis_runtime,
    try_load_first_four_private_runners,
)
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_result_projection import (
    aggregate_module_status,
    module_status_stage_dependencies,
)


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture
def sqlite_env(tmp_path):
    db = _fk_engine(f"sqlite:///{tmp_path / 'chg053.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    session = factory()
    book = Book(
        title="CHG053",
        source_file_name="chg053.txt",
        source_file_hash="a" * 64,
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title="第一章",
        display_title="第一章",
        chapter_title="第一章",
        source_title_line="第一章",
        word_count=4,
    )
    session.add(chapter)
    session.flush()
    session.add(
        Paragraph(
            id=f"B{book.id:04d}-C0001-P0001",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=1,
            raw_text="天亮了。",
            normalized_text="天亮了。",
            char_start=0,
            char_end=4,
        )
    )
    session.commit()
    snap = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    yield {"session": session, "book": book, "snap": snap}
    session.close()


def test_live_factory_fails_closed_without_private_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.narrative_core.services.private_whole_book_analysis_runtime.try_load_first_four_private_runners",
        lambda **kwargs: None,
    )
    with pytest.raises(RuntimeError, match="LIVE_PRIVATE_ENGINE_PACKAGE_MISSING"):
        create_lab_private_whole_book_analysis_runtime(
            require_private_real=True,
            lab_dry_run=False,
            fallback_to_fake=False,
        )


def test_live_factory_with_private_package_bound(sqlite_env, monkeypatch: pytest.MonkeyPatch) -> None:
    private = try_load_first_four_private_runners()
    if private is None:
        pytest.skip("storylens_private_engine not installed")
    runtime = create_lab_private_whole_book_analysis_runtime(
        session=sqlite_env["session"],
        book_id=int(sqlite_env["book"].id),
        use_phase1b_persistence=True,
        lab_dry_run=False,
        fallback_to_fake=False,
        require_private_real=True,
    )
    assert runtime.private_modules_bound is True
    private = runtime.private_runners or {}
    bound_id = next(
        str(getattr(r, "engine_id", "") or "")
        for r in private.values()
        if getattr(r, "engine_id", None)
    )
    assert not is_fake_or_test_engine_id(bound_id)


def test_dry_lab_still_allows_fallback_fake(sqlite_env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.narrative_core.services.private_whole_book_analysis_runtime.try_load_first_four_private_runners",
        lambda **kwargs: None,
    )
    runtime = create_lab_private_whole_book_analysis_runtime(
        session=sqlite_env["session"],
        book_id=int(sqlite_env["book"].id),
        lab_dry_run=True,
        fallback_to_fake=True,
        require_private_real=False,
    )
    assert runtime.private_modules_bound is False
    assert runtime.synthetic is True


def test_aggregate_module_status_producer_failed_with_scaffold_complete() -> None:
    deps = module_status_stage_dependencies(WholeBookModuleKey.BOOK_OVERVIEW)
    stage_status = {d.value: StageStatus.COMPLETED for d in deps}
    stage_status[WholeBookStageKey.ANALYZE_STRUCTURE.value] = StageStatus.FAILED
    status = aggregate_module_status(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        requested={WholeBookModuleKey.BOOK_OVERVIEW},
        stage_status=stage_status,
        has_usable_output=False,
        stale=False,
        blocking_conflict=False,
    )
    assert status == WholeBookModuleStatus.FAILED


def test_aggregate_module_status_all_complete_without_output_is_failed() -> None:
    deps = module_status_stage_dependencies(WholeBookModuleKey.BOOK_OVERVIEW)
    stage_status = {d.value: StageStatus.COMPLETED for d in deps}
    status = aggregate_module_status(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        requested={WholeBookModuleKey.BOOK_OVERVIEW},
        stage_status=stage_status,
        has_usable_output=False,
        stale=False,
        blocking_conflict=False,
    )
    assert status == WholeBookModuleStatus.FAILED


def test_classify_live_engine_kind() -> None:
    assert (
        classify_live_engine_kind(
            engine_id="fake.signed.private_engine",
            private_modules_bound=True,
            synthetic=False,
        )
        == LiveEngineKind.TEST_FAKE
    )
    assert (
        classify_live_engine_kind(
            engine_id="storylens.private.whole_book.dev",
            private_modules_bound=False,
            synthetic=False,
        )
        == LiveEngineKind.CONTRACT_STUB
    )
    assert (
        classify_live_engine_kind(
            engine_id="storylens.private.whole_book.dev",
            private_modules_bound=True,
            synthetic=False,
        )
        == LiveEngineKind.PRIVATE_REAL
    )


@pytest.mark.skip(reason="Legacy Private Lab unit fixture predates mandatory formal V2 snapshot context resolution")
def test_provider_attempt_checkpoint_written_before_live_assert_fails() -> None:
    checkpoints: list[dict[str, Any]] = []

    class _StageSvc:
        def write_checkpoint(self, run_id, stage_key, payload, **accumulate):  # noqa: ANN001
            checkpoints.append({"payload": dict(payload), "accumulate": dict(accumulate)})

    class _Prov:
        def execute_module(self, **kwargs):  # noqa: ANN003
            return SimpleNamespace(
                status="success",
                output_fingerprint="fp-1",
                structured_output={"overview": "x", "evidence_candidates": []},
                usage={
                    "transport_kind": "FAKE_HTTP_TEST",
                    "provider_request_id": "req-053",
                    "http_status": 200,
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "live_request_confirmed": True,
                    "synthetic_success": False,
                },
            )

        def cancel(self, ref: str) -> None:
            return None

    class _Run:
        id = 1
        book_id = 1
        book_snapshot_id = 1

    class _Stage:
        id = 2
        stage_key = "analyze_structure"
        attempt_count = 0

    def _factory(**kwargs):  # noqa: ANN003
        rt = MagicMock()
        rt.private_modules_bound = True
        rt.synthetic = False
        rt.fake_engine = SimpleNamespace(engine_id="storylens.private.whole_book.dev")
        rt.build_native_context_bundle.side_effect = RuntimeError("pipeline boom")
        return rt

    ex = PrivateLabRunExecutor(
        SimpleNamespace(get=lambda *_a, **_k: None, commit=lambda: None),  # type: ignore[arg-type]
        stage_service=_StageSvc(),  # type: ignore[arg-type]
        provider_port=_Prov(),  # type: ignore[arg-type]
        runtime_factory=_factory,
    )
    with pytest.raises(PrivateWholeBookLabRunError) as ei:
        ex._execute_module(
            run=_Run(),  # type: ignore[arg-type]
            meta={"dry_run": False},
            stage=_Stage(),
            module_key="book_overview",
            cancellation_ref=None,
        )
    assert ei.value.detail_code is not None
    assert checkpoints
    assert checkpoints[0]["payload"].get("checkpoint_kind") == "provider_attempt"
    assert checkpoints[0]["payload"].get("provider_request_id") == "req-053"


def test_live_product_path_private_real_with_fake_http(sqlite_env) -> None:
    private = try_load_first_four_private_runners()
    if private is None:
        pytest.skip("storylens_private_engine not installed")
    session: Session = sqlite_env["session"]
    sp = session.scalars(
        select(BookSnapshotParagraph).where(
            BookSnapshotParagraph.snapshot_id == sqlite_env["snap"].id
        )
    ).first()
    assert sp is not None
    structured = {
        "logline": "Live overview",
        "premise": "premise",
        "primary_conflict": "conflict",
        "central_question": "what happens next",
        "structure_summary": "summary",
        "ending_state": "unknown",
        "partial": False,
        "synthetic": False,
        "evidence_candidates": [
            {
                "candidate_id": "ev-1",
                "snapshot_chapter_id": int(sp.snapshot_chapter_id),
                "snapshot_paragraph_id": int(sp.id),
                "stable_paragraph_id": str(sp.stable_paragraph_id),
                "paragraph_content_hash": str(sp.content_hash),
                "start_offset": 0,
                "end_offset": 4,
                "evidence_role": "support",
                "target_output_ref": "book_overview.out",
                "book_snapshot_id": int(sqlite_env["snap"].id),
                "book_id": int(sqlite_env["book"].id),
            }
        ],
    }
    run = AnalysisRun(
        book_id=sqlite_env["book"].id,
        analysis_type="whole_book_native",
        scope_type="book",
        subject_type="book",
        subject_id=str(sqlite_env["book"].id),
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="0.0.1",
        schema_version="1.0.0",
        input_hash="b" * 64,
        status="running",
        book_snapshot_id=sqlite_env["snap"].id,
        task_type="whole_book_pipeline",
    )
    session.add(run)
    session.flush()
    stage = AnalysisRunStage(
        run_id=run.id,
        stage_key="analyze_structure",
        status="running",
        stage_order=0,
        attempt_count=1,
    )
    session.add(stage)
    session.commit()

    runtime = create_lab_private_whole_book_analysis_runtime(
        session=session,
        book_id=int(sqlite_env["book"].id),
        use_phase1b_persistence=True,
        lab_dry_run=False,
        fallback_to_fake=False,
        require_private_real=True,
    )
    runtime.bind_session(session)
    _wb, contract = runtime.build_native_context_bundle(
        book_id=int(sqlite_env["book"].id),
        book_snapshot_id=int(sqlite_env["snap"].id),
        module_keys=("book_overview",),
    )
    from app.narrative_core.private_engine_contract.context import make_context_bundle_ref

    ref = make_context_bundle_ref(contract.bundle_hash)
    pipeline = runtime.execute_module_pipeline(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        book_id=int(sqlite_env["book"].id),
        book_snapshot_id=int(sqlite_env["snap"].id),
        run_id=int(run.id),
        run_stage_id=int(stage.id),
        context_bundle_ref=ref,
        configuration_fingerprint_value="cfg-053",
        provider_policy={
            "provider_kind": "aliyun_qwen_plus",
            "model_route": "lab-route",
            "synthetic_output": structured,
            "evidence_candidates": structured["evidence_candidates"],
        },
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        persist=True,
    )
    engine_id = str(getattr(pipeline.engine_result, "engine_id", "") or "")
    assert not is_fake_or_test_engine_id(engine_id)
    assert pipeline.synthetic is False
    assert classify_live_engine_kind(
        engine_id=engine_id,
        private_modules_bound=True,
        synthetic=bool(pipeline.synthetic),
    ) == LiveEngineKind.PRIVATE_REAL
    persist = dict((pipeline.candidate_summary or {}).get("persist") or {})
    assert persist.get("orm_written") is True
    assert persist.get("persistence_complete") is True
    assert len(pipeline.engine_result.evidence_candidates) >= 1


def test_failure_projection_business_stage_failed(sqlite_env) -> None:
    deps = module_status_stage_dependencies(WholeBookModuleKey.BOOK_OVERVIEW)
    stage_status = {d.value: StageStatus.COMPLETED for d in deps}
    stage_status[WholeBookStageKey.ANALYZE_STRUCTURE.value] = StageStatus.FAILED
    status = aggregate_module_status(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        requested={WholeBookModuleKey.BOOK_OVERVIEW},
        stage_status=stage_status,
        has_usable_output=False,
        stale=False,
        blocking_conflict=False,
    )
    assert status == WholeBookModuleStatus.FAILED
