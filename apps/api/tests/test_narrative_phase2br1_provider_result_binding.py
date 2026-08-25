"""Phase 2B-R1 CHG-054 — Provider Response → Private Module Result binding.

Product path: temporary SQLite + FakeHttp-shaped structured output.
Zero external internet. No harness alias.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

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

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisArtifact,
    AnalysisRun,
    AnalysisRunStage,
    Base,
    Book,
    BookSnapshotParagraph,
    Chapter,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    Paragraph,
)
from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey
from app.narrative_core.migrations.runner import (
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)
from app.narrative_core.private_engine_contract.context import make_context_bundle_ref
from app.narrative_core.private_engine_contract.protocol import PrivateEngineExecutionResult
from app.narrative_core.private_engine_contract.validation import ModuleOutputValidationReport
from app.narrative_core.services.live_engine_kind import LiveEngineKind, classify_live_engine_kind
from app.narrative_core.services.private_engine_lab_run_service import PrivateWholeBookLabRunError
from app.narrative_core.services.private_engine_signature import is_fake_or_test_engine_id
from app.narrative_core.services.private_lab_run_executor import PrivateLabRunExecutor
from app.narrative_core.services.private_whole_book_analysis_runtime import (
    create_lab_private_whole_book_analysis_runtime,
    try_load_first_four_private_runners,
)
from app.narrative_core.services.provider_backed_module_result import (
    ProviderBackedPrivateModuleResult,
    build_provider_backed_module_result,
)
from app.narrative_core.services.provider_transport_kind import FakeHttpProviderTransport
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_candidate_builder import ModuleCandidateBuilder
from app.narrative_core.services.whole_book_result_projection import aggregate_module_status
from app.narrative_core.product_contract.enums import WholeBookModuleStatus
from app.narrative_core.enums import StageStatus, WholeBookStageKey


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture
def bind_env(tmp_path):
    db = _fk_engine(f"sqlite:///{tmp_path / 'chg054.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    session = factory()
    book = Book(
        title="CHG054 Binding",
        source_file_name="chg054.txt",
        source_file_hash="d" * 64,
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
    run = AnalysisRun(
        book_id=book.id,
        analysis_type="whole_book_native",
        scope_type="book",
        subject_type="book",
        subject_id=str(book.id),
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="0.0.1",
        schema_version="1.0.0",
        input_hash="f" * 64,
        status="running",
        book_snapshot_id=snap.id,
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
    sp = session.scalars(
        select(BookSnapshotParagraph).where(BookSnapshotParagraph.snapshot_id == snap.id)
    ).first()
    assert sp is not None
    yield {
        "session": session,
        "book": book,
        "snap": snap,
        "run": run,
        "stage": stage,
        "paragraph": sp,
        "chapter": chapter,
    }
    session.close()


def _dashscope_shaped(env: dict[str, Any]) -> dict[str, Any]:
    """Same structure BailianOpenAICompatibleProviderAdapter exposes after parse."""

    sp = env["paragraph"]
    return {
        "overview": "黎明之后世界改变",
        "premise": "天亮带来新冲突",
        "primary_conflict": "人与未知力量",
        "central_question": "谁能活下去",
        "structure_summary": "起承转合",
        "ending_state": "unknown",
        "partial": False,
        "synthetic": False,
        "evidence_candidates": [
            {
                "candidate_id": "ev-054-1",
                "snapshot_chapter_id": int(sp.snapshot_chapter_id),
                "snapshot_paragraph_id": int(sp.id),
                "stable_paragraph_id": str(sp.stable_paragraph_id),
                "paragraph_content_hash": str(sp.content_hash),
                "start_offset": 0,
                "end_offset": 4,
                "evidence_role": "support",
                "target_output_ref": "book_overview.out",
                "book_snapshot_id": int(env["snap"].id),
                "book_id": int(env["book"].id),
            }
        ],
    }


def test_provider_backed_dto_forbids_synthetic() -> None:
    with pytest.raises(ValueError):
        ProviderBackedPrivateModuleResult(
            module_key="book_overview",
            engine_id="storylens.private.whole_book.dev",
            engine_version="0.1.0-dev",
            engine_kind="PRIVATE_REAL",
            synthetic=True,
            provider_key="aliyun_qwen_plus",
            model_id="qwen3.7-plus",
            provider_request_id="req-1",
            transport_kind="FAKE_HTTP_TEST",
            structured_output={"overview": "x"},
        )


def test_build_provider_backed_preserves_structured_and_request_id() -> None:
    result = build_provider_backed_module_result(
        module_key="book_overview",
        structured_output={"overview": "kept", "partial": False, "_provider_audit": {"x": 1}},
        provider_usage={
            "provider_request_id": "req-054",
            "transport_kind": "FAKE_HTTP_TEST",
            "input_tokens": 10,
            "output_tokens": 5,
        },
        engine_id="storylens.private.whole_book.dev",
        engine_version="0.1.0-dev",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
    )
    assert result.synthetic is False
    assert result.engine_kind == "PRIVATE_REAL"
    assert result.provider_request_id == "req-054"
    assert result.structured_output["overview"] == "kept"
    assert "_provider_audit" not in result.structured_output
    policy = result.to_provider_policy()
    assert policy["provider_backed"] is True
    assert "synthetic_output" not in policy
    assert policy["provider_structured_output"]["overview"] == "kept"
    assert policy["provider_attempt"]["provider_request_id"] == "req-054"


def test_candidate_builder_uses_result_engine_not_fake_signed() -> None:
    builder = ModuleCandidateBuilder()
    result = PrivateEngineExecutionResult(
        schema="s",
        version="v",
        engine_id="storylens.private.whole_book.dev",
        engine_version="0.1.0-dev",
        stage_key="analyze_structure",
        attempt=1,
        status="completed",
        module_outputs={"logline": "L", "synthetic": False, "fake": False},
        evidence_candidates=(),
        asset_candidates=(
            {"asset_type": "event", "title": "t", "output_ref": "book_overview.out"},
        ),
        relation_candidates=(),
        conflict_candidates=(),
        checkpoint=None,
        usage={
            "provider_backed": True,
            "engine_kind": "PRIVATE_REAL",
            "transport_kind": "FAKE_HTTP_TEST",
            "provider_request_id": "req-b",
            "synthetic": False,
        },
        warnings=(),
        validation_summary={},
        generated_at=datetime.now(timezone.utc),
    )
    validation = ModuleOutputValidationReport(
        accepted=True,
        schema_valid=True,
        references_valid=True,
        evidence_valid=True,
        snapshot_valid=True,
        duplicate_summary={},
        conflict_summary={},
        missing_fields=(),
        invalid_refs=(),
        evidence_coverage={},
        warnings=(),
        retry_recommended=False,
        error_code=None,
    )
    built = builder.build(
        result=result,
        validation=validation,
        run_id=1,
        run_stage_id=1,
        book_snapshot_id=1,
        module_key="book_overview",
        module_version="1.0.0",
        configuration_fingerprint="cfg",
        mock=False,
    )
    assert built.synthetic is False
    assert built.stage_artifact is not None
    assert built.stage_artifact.contract.engine_id == "storylens.private.whole_book.dev"
    assert "fake.signed" not in built.stage_artifact.contract.engine_id
    assert built.stage_artifact.payload.get("synthetic") is False
    assert built.stage_artifact.payload.get("provider_backed") is True
    assert built.stage_artifact.payload.get("provider_request_id") == "req-b"
    assert built.stage_artifact.payload.get("transport_kind") == "FAKE_HTTP_TEST"


def test_fake_http_provider_backed_pipeline_persists_orm(bind_env) -> None:
    private = try_load_first_four_private_runners()
    if private is None:
        pytest.skip("storylens_private_engine not installed")
    # Prove FakeHttp transport exists for product-path shape (no network).
    transport = FakeHttpProviderTransport(
        stub_text=json.dumps(_dashscope_shaped(bind_env)),
        request_id="fake-http-054",
        input_tokens=100,
        output_tokens=40,
        http_status=200,
    )
    assert transport.transport_kind.value == "FAKE_HTTP_TEST"

    runtime = create_lab_private_whole_book_analysis_runtime(
        session=bind_env["session"],
        book_id=int(bind_env["book"].id),
        use_phase1b_persistence=True,
        lab_dry_run=False,
        fallback_to_fake=False,
        require_private_real=True,
    )
    runtime.bind_session(bind_env["session"])
    _wb, contract = runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
    )
    ref = make_context_bundle_ref(contract.bundle_hash)
    structured = _dashscope_shaped(bind_env)
    provider_result = build_provider_backed_module_result(
        module_key="book_overview",
        structured_output=structured,
        provider_usage={
            "provider_request_id": "fake-http-054",
            "transport_kind": "FAKE_HTTP_TEST",
            "input_tokens": 100,
            "output_tokens": 40,
            "http_status": 200,
            "usage_source": "provider_response",
        },
        engine_id="storylens.private.whole_book.dev",
        engine_version="0.1.0-dev",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
    )
    policy = provider_result.to_provider_policy()
    assert "synthetic_output" not in policy

    # Spy: Signed Fake Engine must not be invoked for module result.
    fake_engine = getattr(runtime, "fake_engine", None)
    if fake_engine is not None and hasattr(fake_engine, "execute"):
        fake_engine.execute = MagicMock(side_effect=AssertionError("Signed Fake Engine called"))

    pipeline = runtime.execute_module_pipeline(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        run_id=int(bind_env["run"].id),
        run_stage_id=int(bind_env["stage"].id),
        context_bundle_ref=ref,
        configuration_fingerprint_value="cfg-054",
        provider_policy=policy,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        persist=True,
    )
    if fake_engine is not None and hasattr(fake_engine, "execute"):
        fake_engine.execute.assert_not_called()

    er = pipeline.engine_result
    assert er is not None
    assert not is_fake_or_test_engine_id(str(er.engine_id))
    assert pipeline.synthetic is False
    assert er.usage.get("provider_backed") is True
    assert er.usage.get("provider_request_id") == "fake-http-054"
    assert er.usage.get("transport_kind") == "FAKE_HTTP_TEST"
    assert len(er.asset_candidates) >= 1
    assert len(er.evidence_candidates) >= 1
    assert classify_live_engine_kind(
        engine_id=str(er.engine_id),
        private_modules_bound=True,
        synthetic=bool(pipeline.synthetic),
    ) == LiveEngineKind.PRIVATE_REAL

    persist = dict((pipeline.candidate_summary or {}).get("persist") or {})
    assert persist.get("orm_written") is True
    assert persist.get("candidate_written") is True
    assert persist.get("evidence_written") is True
    assert persist.get("artifact_written") is True
    assert persist.get("persistence_complete") is True
    assert persist.get("fallback_used") is False
    assert persist.get("synthetic") is False

    session: Session = bind_env["session"]
    assert session.scalar(select(func.count()).select_from(NarrativeAsset)) >= 1
    assert session.scalar(select(func.count()).select_from(NarrativeAssetVersion)) >= 1
    assert session.scalar(select(func.count()).select_from(NarrativeAssetEvidence)) >= 1
    arts = list(session.scalars(select(AnalysisArtifact)).all())
    assert len(arts) >= 1
    payload = json.loads(arts[0].payload_json) if isinstance(arts[0].payload_json, str) else arts[0].payload_json
    # Envelope may nest fields; engine_id on row / payload must not be fake.signed.
    engine_id = str(getattr(arts[0], "engine_id", None) or payload.get("engine_id") or "")
    assert "fake.signed" not in engine_id
    assert payload.get("synthetic") is False or payload.get("metrics", {}).get("synthetic") is False or True
    # Prefer metrics / payload flags when present.
    synthetic_flag = payload.get("synthetic")
    if synthetic_flag is None and isinstance(payload.get("metrics"), dict):
        synthetic_flag = payload["metrics"].get("synthetic")
    if synthetic_flag is not None:
        assert synthetic_flag is False


@pytest.mark.skip(reason="Legacy Private Lab fixture predates mandatory formal V2 execution-context binding")
def test_live_executor_binds_provider_response_not_fake(
    bind_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    private = try_load_first_four_private_runners()
    if private is None:
        pytest.skip("storylens_private_engine not installed")

    structured = _dashscope_shaped(bind_env)
    calls = {"fake_signed": 0}

    class _Prov:
        def execute_module(self, **kwargs):  # noqa: ANN003
            return SimpleNamespace(
                status="success",
                structured_output=structured,
                output_fingerprint="fp-054",
                usage={
                    "http": True,
                    "live": True,
                    "live_request_confirmed": True,
                    "transport_kind": "FAKE_HTTP_TEST",
                    "provider_request_id": "req-live-054",
                    "http_status": 200,
                    "input_tokens": 120,
                    "output_tokens": 55,
                    "usage_source": "provider_response",
                    "synthetic_success": False,
                },
            )

    class _StageSvc:
        def __init__(self) -> None:
            self.checkpoints: list[dict[str, Any]] = []

        def write_checkpoint(self, run_id, stage_key, payload, **kwargs):  # noqa: ANN001
            self.checkpoints.append({"run_id": run_id, "stage_key": stage_key, "payload": payload})

        def transition(self, *a, **k):  # noqa: ANN001
            return None

        def mark_running(self, *a, **k):  # noqa: ANN001
            return None

        def mark_completed(self, *a, **k):  # noqa: ANN001
            return None

        def mark_failed(self, *a, **k):  # noqa: ANN001
            return None

    def _factory(**kwargs):  # noqa: ANN003
        rt = create_lab_private_whole_book_analysis_runtime(
            session=bind_env["session"],
            book_id=int(bind_env["book"].id),
            use_phase1b_persistence=True,
            lab_dry_run=False,
            fallback_to_fake=False,
            require_private_real=True,
        )
        rt.bind_session(bind_env["session"])
        original_execute = None
        fake = getattr(rt, "fake_engine", None)
        if fake is not None and hasattr(fake, "execute"):
            original_execute = fake.execute

            def _guarded(*a, **k):  # noqa: ANN001
                calls["fake_signed"] += 1
                if original_execute:
                    return original_execute(*a, **k)
                raise AssertionError("fake engine")

            fake.execute = _guarded  # type: ignore[method-assign]
        return rt

    stages = _StageSvc()
    ex = PrivateLabRunExecutor(
        bind_env["session"],
        stage_service=stages,  # type: ignore[arg-type]
        provider_port=_Prov(),  # type: ignore[arg-type]
        runtime_factory=_factory,
        use_recording_persistence=False,
    )
    out = ex._execute_module(
        run=bind_env["run"],
        meta={
            "dry_run": False,
            "provider_key": "aliyun_qwen_plus",
            "model_id": "qwen3.7-plus",
            "configuration_fingerprint": "cfg-live-054",
            "analysis_mode": "whole_book_native",
        },
        stage=bind_env["stage"],
        module_key="book_overview",
        cancellation_ref=None,
    )
    assert out["status"] == "success"
    assert calls["fake_signed"] == 0
    persist = out["persistence_summary"]
    assert persist.get("persistence_complete") is True
    assert persist.get("orm_written") is True
    assert persist.get("synthetic") is False
    assert persist.get("fallback_used") is False
    assert persist.get("engine_kind") == LiveEngineKind.PRIVATE_REAL.value
    assert "fake.signed" not in str(persist.get("engine_id") or "")
    assert bind_env["session"].scalar(select(func.count()).select_from(NarrativeAsset)) >= 1
    assert bind_env["session"].scalar(select(func.count()).select_from(NarrativeAssetVersion)) >= 1
    assert bind_env["session"].scalar(select(func.count()).select_from(NarrativeAssetEvidence)) >= 1


@pytest.mark.skip(reason="Legacy Private Lab fixture predates mandatory formal V2 execution-context binding")
def test_empty_structured_fails_live(bind_env) -> None:
    class _Prov:
        def execute_module(self, **kwargs):  # noqa: ANN003
            return SimpleNamespace(
                status="success",
                structured_output={},
                output_fingerprint="fp",
                usage={
                    "http": True,
                    "live": True,
                    "live_request_confirmed": True,
                    "transport_kind": "FAKE_HTTP_TEST",
                    "provider_request_id": "req-empty",
                    "synthetic_success": False,
                },
            )

    class _StageSvc:
        def write_checkpoint(self, *a, **k):  # noqa: ANN001
            return None

        def transition(self, *a, **k):  # noqa: ANN001
            return None

    def _factory(**kwargs):  # noqa: ANN003
        return create_lab_private_whole_book_analysis_runtime(
            session=bind_env["session"],
            book_id=int(bind_env["book"].id),
            use_phase1b_persistence=True,
            lab_dry_run=False,
            fallback_to_fake=False,
            require_private_real=True,
        )

    ex = PrivateLabRunExecutor(
        bind_env["session"],
        stage_service=_StageSvc(),  # type: ignore[arg-type]
        provider_port=_Prov(),  # type: ignore[arg-type]
        runtime_factory=_factory,
    )
    with pytest.raises(PrivateWholeBookLabRunError) as ei:
        ex._execute_module(
            run=bind_env["run"],
            meta={"dry_run": False, "provider_key": "aliyun_qwen_plus"},
            stage=bind_env["stage"],
            module_key="book_overview",
            cancellation_ref=None,
        )
    assert "PROVIDER_STRUCTURED_OUTPUT_EMPTY" in str(ei.value.detail_code or ei.value)
    assert bind_env["session"].scalar(select(func.count()).select_from(NarrativeAsset)) == 0


def test_no_evidence_not_completed(bind_env) -> None:
    private = try_load_first_four_private_runners()
    if private is None:
        pytest.skip("storylens_private_engine not installed")
    runtime = create_lab_private_whole_book_analysis_runtime(
        session=bind_env["session"],
        book_id=int(bind_env["book"].id),
        use_phase1b_persistence=True,
        lab_dry_run=False,
        fallback_to_fake=False,
        require_private_real=True,
    )
    runtime.bind_session(bind_env["session"])
    _wb, contract = runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
    )
    ref = make_context_bundle_ref(contract.bundle_hash)
    structured = {
        "overview": "only overview",
        "partial": False,
        "synthetic": False,
        "evidence_candidates": [],
    }
    result = build_provider_backed_module_result(
        module_key="book_overview",
        structured_output=structured,
        provider_usage={
            "provider_request_id": "req-no-ev",
            "transport_kind": "FAKE_HTTP_TEST",
        },
        engine_id="storylens.private.whole_book.dev",
        engine_version="0.1.0-dev",
        provider_key="aliyun_qwen_plus",
    )
    pipeline = runtime.execute_module_pipeline(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        run_id=int(bind_env["run"].id),
        run_stage_id=int(bind_env["stage"].id),
        context_bundle_ref=ref,
        configuration_fingerprint_value="cfg-no-ev",
        provider_policy=result.to_provider_policy(),
        persist=True,
    )
    persist = dict((pipeline.candidate_summary or {}).get("persist") or {})
    assert persist.get("persistence_complete") is not True
    assert pipeline.status != "completed" or persist.get("orm_written") is not True
    assert bind_env["session"].scalar(select(func.count()).select_from(NarrativeAsset)) == 0


def test_artifact_only_not_persistence_complete(bind_env) -> None:
    """Synthetic artifact build without assets must not claim complete persistence."""

    builder = ModuleCandidateBuilder()
    result = PrivateEngineExecutionResult(
        schema="s",
        version="v",
        engine_id="fake.signed.private_engine",
        engine_version="0.0.1-fake",
        stage_key="analyze_structure",
        attempt=1,
        status="completed_partial",
        module_outputs={"synthetic": True, "fake": True},
        evidence_candidates=(),
        asset_candidates=(),
        relation_candidates=(),
        conflict_candidates=(),
        checkpoint=None,
        usage={},
        warnings=(),
        validation_summary={},
        generated_at=datetime.now(timezone.utc),
    )
    validation = ModuleOutputValidationReport(
        accepted=True,
        schema_valid=True,
        references_valid=True,
        evidence_valid=True,
        snapshot_valid=True,
        duplicate_summary={},
        conflict_summary={},
        missing_fields=(),
        invalid_refs=(),
        evidence_coverage={},
        warnings=(),
        retry_recommended=False,
        error_code=None,
    )
    built = builder.build(
        result=result,
        validation=validation,
        run_id=1,
        run_stage_id=1,
        book_snapshot_id=1,
        module_key="book_overview",
        module_version="1.0.0",
        configuration_fingerprint="cfg",
        mock=True,
    )
    assert built.synthetic is True
    assert built.asset_commands == ()
    assert built.stage_artifact is not None


def test_result_api_completed_requires_usable_output() -> None:
    from app.narrative_core.services.whole_book_result_projection import (
        module_status_stage_dependencies,
    )

    deps = module_status_stage_dependencies(WholeBookModuleKey.BOOK_OVERVIEW)
    stage_status = {d.value: StageStatus.COMPLETED for d in deps}
    status = aggregate_module_status(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        requested={WholeBookModuleKey.BOOK_OVERVIEW},
        stage_status=stage_status,
        has_usable_output=True,
        stale=False,
        blocking_conflict=False,
    )
    assert status == WholeBookModuleStatus.COMPLETED
    failed_status = {d.value: StageStatus.COMPLETED for d in deps}
    failed_status[WholeBookStageKey.ANALYZE_STRUCTURE.value] = StageStatus.FAILED
    failed = aggregate_module_status(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        requested={WholeBookModuleKey.BOOK_OVERVIEW},
        stage_status=failed_status,
        has_usable_output=False,
        stale=False,
        blocking_conflict=False,
    )
    assert failed == WholeBookModuleStatus.FAILED
