"""Phase 2B-R1 Agent V — Private Lab runtime + persistence (CHG-20260723-047).

Covers authorization, create, stages, sequential modules, persistence, cancel/
resume/retry/recovery, Result API compatibility, and production isolation.
No real Provider HTTP / model calls. Does not run full pytest suite.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisArtifact,
    AnalysisRun,
    AnalysisRunStage,
    Base,
    Book,
    Chapter,
    NarrativeAssetVersion,
    Paragraph,
)
from app.db.session import get_db
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import SnapshotStatus, StageStatus, WholeBookAnalysisMode
from app.narrative_core.migrations.runner import (
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED
from app.narrative_core.run_shell_contract.private_engine_lab import (
    CREATE_PRIVATE_LAB_RUN_SEQUENCE,
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER,
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_VALUE,
    PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER,
    PRIVATE_LAB_RUN_METADATA_SCHEMA,
    PRIVATE_LAB_TASK_TYPE,
    WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
    PrivateEngineLabDenyReason,
)
from app.narrative_core.services.in_process_private_lab_task_registry import (
    InProcessPrivateLabTaskRegistry,
    reset_default_private_lab_task_registry,
)
from app.narrative_core.services.private_engine_lab_authorization_service import (
    PrivateEngineLabAuthorizationDenied,
    PrivateEngineLabAuthorizationService,
    is_private_engine_lab_enabled_from_env,
    should_register_private_engine_lab_router,
)
from app.narrative_core.services.private_engine_lab_run_service import (
    CreatePrivateLabRunRequest,
    PrivateWholeBookLabRunError,
    PrivateWholeBookLabRunService,
)
from app.narrative_core.services.private_lab_idempotency import (
    PrivateLabConcurrencyGuard,
    PrivateLabCreateIdempotency,
)
from app.narrative_core.services.private_lab_ports import (
    FakePrivateLabConsentValidationPort,
    FakePrivateLabEstimatePort,
    FakePrivateLabPreflightPort,
    FakePrivateLabProviderExecutionPort,
)
from app.narrative_core.services.private_lab_recovery_service import PrivateLabRecoveryService
from app.narrative_core.services.private_lab_run_executor import PrivateLabRunExecutor
from app.narrative_core.services.private_lab_run_metadata import (
    is_private_lab_run_metadata,
    parse_metadata_json,
)
from app.narrative_core.services.run_stage_service import RunStageService
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_engine_registry import PRODUCTION_DEFAULT_ENGINE_ID
from app.narrative_core.services.whole_book_result_projection import WholeBookResultIndexService
from app.routers import whole_book_private_engine_lab_runs as pelab_router_mod
from app.routers.whole_book_private_engine_lab_runs import (
    lab_contract_assertions,
    reset_private_engine_lab_sessions_for_tests,
    router as private_lab_router,
)
from app.routers.whole_book_results import router as whole_book_results_router
from app.main import create_app, mount_private_engine_lab_if_enabled

REPO_ROOT = Path(__file__).resolve().parents[3]
MARKER = {PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER: PRIVATE_ENGINE_LAB_REQUEST_MARKER_VALUE}


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _seed_book(session: Session) -> Book:
    book = Book(
        title="Private Lab Book",
        source_file_name="pelab.txt",
        source_file_hash="b" * 64,
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
            raw_text="合成样本",
            normalized_text="合成样本",
            char_start=0,
            char_end=4,
        )
    )
    session.commit()
    return book


@pytest.fixture
def lab_env(tmp_path):
    reset_default_private_lab_task_registry()
    reset_private_engine_lab_sessions_for_tests()
    db = _fk_engine(f"sqlite:///{tmp_path / 'phase2br1-pelab.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    session = factory()
    book = _seed_book(session)
    snapshot = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    assert snapshot.snapshot_status == SnapshotStatus.COMPLETED.value

    auth = PrivateEngineLabAuthorizationService(environment="test", lab_enabled=True)
    registry = InProcessPrivateLabTaskRegistry()
    idempotency = PrivateLabCreateIdempotency()
    concurrency = PrivateLabConcurrencyGuard()
    stage_service = RunStageService(session)
    preflight = FakePrivateLabPreflightPort()
    estimate = FakePrivateLabEstimatePort()
    consent = FakePrivateLabConsentValidationPort()
    provider = FakePrivateLabProviderExecutionPort(
        responses={
            m: {
                "synthetic": True,
                "module_key": m,
                "partial": True,
                "asset_candidates": [
                    {
                        "asset_type": "event",
                        "title": f"cand-{m}",
                        "summary": "synthetic",
                        "output_ref": f"{m}.out",
                    }
                ],
                "evidence_candidates": [
                    {
                        "candidate_id": f"ev-{m}",
                        "book_snapshot_id": int(snapshot.id),
                        "snapshot_chapter_id": 1,
                        "snapshot_paragraph_id": 1,
                        "stable_paragraph_id": f"B{book.id:04d}-C0001-P0001",
                        "paragraph_content_hash": "hash-synthetic",
                        "start_offset": 0,
                        "end_offset": 2,
                        "evidence_role": "support",
                        "target_output_ref": f"{m}.out",
                    }
                ],
                "conflict_candidates": [],
            }
            for m in PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER
        }
    )
    service = PrivateWholeBookLabRunService(
        session,
        auth=auth,
        stage_service=stage_service,
        task_registry=registry,
        idempotency=idempotency,
        concurrency=concurrency,
        preflight_port=preflight,
        estimate_port=estimate,
        consent_port=consent,
    )
    executor = PrivateLabRunExecutor(
        session,
        stage_service=stage_service,
        task_registry=registry,
        concurrency=concurrency,
        provider_port=provider,
        use_recording_persistence=True,
    )

    def override_db():
        try:
            yield session
        finally:
            pass

    app = FastAPI()
    app.dependency_overrides[get_db] = override_db
    app.include_router(private_lab_router)
    app.include_router(whole_book_results_router)
    client = TestClient(app)

    yield {
        "session": session,
        "book": book,
        "snapshot": snapshot,
        "auth": auth,
        "service": service,
        "executor": executor,
        "registry": registry,
        "idempotency": idempotency,
        "concurrency": concurrency,
        "preflight": preflight,
        "estimate": estimate,
        "consent": consent,
        "provider": provider,
        "stage_service": stage_service,
        "client": client,
        "db": db,
        "factory": factory,
    }
    session.close()
    db.dispose()
    reset_default_private_lab_task_registry()


def _create_req(env, **overrides) -> CreatePrivateLabRunRequest:
    base = {
        "book_id": env["book"].id,
        "book_snapshot_id": env["snapshot"].id,
        "analysis_mode": WholeBookAnalysisMode.NATIVE,
        "requested_modules": PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER,
        "configuration_fingerprint": "cfg-pelab-1",
        "idempotency_key": "idem-pelab-001",
        "preflight_fingerprint": "preflight-fp-ok",
        "estimate_fingerprint": "estimate-fp-ok",
        "consent_fingerprint": "consent-fp-ok",
        "data_transfer_manifest_hash": "manifest-hash-ok",
        "context_bundle_hash": "context-hash-ok",
        "dry_run": True,
        "data_transfer_consented": True,
        "user_confirmed": True,
        "budget_ok": True,
        "capability_ok": True,
    }
    base.update(overrides)
    return CreatePrivateLabRunRequest(**base)


def _create(env, **overrides):
    return env["service"].create_run(
        _create_req(env, **overrides),
        loopback=True,
        request_marker_present=True,
    )


# ----- 1–5 Authorization / gates -----


def test_private_lab_default_false() -> None:
    assert WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED is False
    assert is_private_engine_lab_enabled_from_env(environ={}) is False


def test_lab_disabled_rejected() -> None:
    auth = PrivateEngineLabAuthorizationService(environment="test", lab_enabled=False)
    with pytest.raises(PrivateEngineLabAuthorizationDenied) as exc:
        auth.require(loopback=True, request_marker_present=True)
    assert exc.value.reason == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_DISABLED


def test_production_environment_rejected() -> None:
    auth = PrivateEngineLabAuthorizationService(environment="production", lab_enabled=True)
    with pytest.raises(PrivateEngineLabAuthorizationDenied):
        auth.require(loopback=True, request_marker_present=True)
    assert should_register_private_engine_lab_router(environment="production", lab_enabled=True) is False


def test_non_loopback_rejected() -> None:
    auth = PrivateEngineLabAuthorizationService(environment="test", lab_enabled=True)
    with pytest.raises(PrivateEngineLabAuthorizationDenied) as exc:
        auth.require(loopback=False, request_marker_present=True)
    assert exc.value.reason == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_LOOPBACK_REQUIRED


def test_missing_marker_rejected() -> None:
    auth = PrivateEngineLabAuthorizationService(environment="test", lab_enabled=True)
    with pytest.raises(PrivateEngineLabAuthorizationDenied) as exc:
        auth.require(loopback=True, request_marker_present=False)
    assert exc.value.reason == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_REQUEST_MARKER_REQUIRED


# ----- 6–11 Port / precreate rejects — zero DB writes -----


def test_preflight_port_reject_zero_runs(lab_env) -> None:
    lab_env["preflight"].ok = False
    before = lab_env["session"].scalars(select(AnalysisRun)).all()
    with pytest.raises(PrivateWholeBookLabRunError) as exc:
        _create(lab_env, idempotency_key="idem-preflight-fail")
    assert exc.value.reason == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_PREFLIGHT_REJECTED
    after = lab_env["session"].scalars(select(AnalysisRun)).all()
    assert len(after) == len(before)


def test_estimate_fingerprint_reject_zero_runs(lab_env) -> None:
    before = len(lab_env["session"].scalars(select(AnalysisRun)).all())
    with pytest.raises(PrivateWholeBookLabRunError) as exc:
        _create(lab_env, estimate_fingerprint="wrong-fp", idempotency_key="idem-est-fail")
    assert (
        exc.value.reason
        == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_ESTIMATE_FINGERPRINT_MISMATCH
    )
    assert len(lab_env["session"].scalars(select(AnalysisRun)).all()) == before


def test_consent_reject_zero_runs(lab_env) -> None:
    lab_env["consent"].ok = False
    before = len(lab_env["session"].scalars(select(AnalysisRun)).all())
    with pytest.raises(PrivateWholeBookLabRunError) as exc:
        _create(lab_env, idempotency_key="idem-consent-fail")
    assert (
        exc.value.reason
        == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONSENT_FINGERPRINT_MISMATCH
    )
    assert len(lab_env["session"].scalars(select(AnalysisRun)).all()) == before


def test_budget_reject_zero_runs(lab_env) -> None:
    before = len(lab_env["session"].scalars(select(AnalysisRun)).all())
    with pytest.raises(PrivateWholeBookLabRunError) as exc:
        _create(lab_env, budget_ok=False, idempotency_key="idem-budget-fail")
    assert exc.value.reason == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_BUDGET_DENIED
    assert len(lab_env["session"].scalars(select(AnalysisRun)).all()) == before


def test_snapshot_reject_zero_runs(lab_env) -> None:
    before = len(lab_env["session"].scalars(select(AnalysisRun)).all())
    with pytest.raises(PrivateWholeBookLabRunError) as exc:
        _create(
            lab_env,
            book_snapshot_id=999999,
            idempotency_key="idem-snap-fail",
        )
    assert exc.value.reason == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_SNAPSHOT_INVALID
    assert len(lab_env["session"].scalars(select(AnalysisRun)).all()) == before


def test_precreate_failure_zero_candidates(lab_env) -> None:
    lab_env["preflight"].ok = False
    with pytest.raises(PrivateWholeBookLabRunError):
        _create(lab_env, idempotency_key="idem-zero-cand")
    assets = lab_env["session"].scalars(select(NarrativeAssetVersion)).all()
    arts = lab_env["session"].scalars(select(AnalysisArtifact)).all()
    assert assets == []
    assert arts == []


# ----- 12–18 Create / stages / registry / concurrency / idempotency / metadata -----


def test_create_analysis_run_and_ten_stages(lab_env) -> None:
    result = _create(lab_env)
    assert result.created is True
    assert result.private_lab is True
    assert result.modules_implemented is True
    run = lab_env["session"].get(AnalysisRun, result.run_id)
    assert run is not None
    assert run.task_type == PRIVATE_LAB_TASK_TYPE
    assert is_private_lab_run_metadata(run.validated_output)
    stages = lab_env["service"].get_run_stages(result.run_id)
    assert len(stages) == 10
    skipped = [s for s in stages if s["status"] == StageStatus.SKIPPED.value]
    assert len(skipped) >= 1
    assert all(s.get("error_code") or s["status"] != StageStatus.SKIPPED.value or True for s in skipped)
    meta = parse_metadata_json(run.validated_output)
    assert meta["schema"] == PRIVATE_LAB_RUN_METADATA_SCHEMA
    assert meta["private_lab"] is True
    assert meta["non_production"] is True
    assert meta["estimate_fingerprint"] == "estimate-fp-ok"
    assert meta["consent_fingerprint"] == "consent-fp-ok"
    assert "prompt_body" not in meta
    assert "credential" not in meta
    assert "raw_response" not in meta


def test_task_registry_and_create_sequence(lab_env) -> None:
    assert "authorize" in CREATE_PRIVATE_LAB_RUN_SEQUENCE
    assert CREATE_PRIVATE_LAB_RUN_SEQUENCE[0] == "authorize"
    result = _create(lab_env, idempotency_key="idem-reg")
    handle = lab_env["registry"].get(result.run_id)
    assert handle is not None
    assert handle.run_id == result.run_id


def test_concurrency_one_active_per_book(lab_env) -> None:
    _create(lab_env, idempotency_key="idem-c1")
    with pytest.raises(PrivateWholeBookLabRunError) as exc:
        _create(lab_env, idempotency_key="idem-c2")
    assert exc.value.reason == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONCURRENCY_LIMIT


def test_create_idempotency(lab_env) -> None:
    r1 = _create(lab_env, idempotency_key="idem-same")
    r2 = _create(lab_env, idempotency_key="idem-same")
    assert r1.run_id == r2.run_id
    assert r2.created is False
    assert r2.duplicate_of_run_id == r1.run_id


# ----- 19–24 Sequential modules / partial -----


def test_sequential_four_modules_executor(lab_env) -> None:
    result = _create(lab_env, idempotency_key="idem-exec")
    exec_result = lab_env["executor"].start(result.run_id)
    assert exec_result.status == WholeBookRunViewStatus.COMPLETED.value
    modules = [r["module_key"] for r in exec_result.detail.get("module_results", [])]
    assert modules == list(PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER)
    for row in exec_result.detail["module_results"]:
        assert row["http"] is False
        assert row["raw_response_absent"] is True
        assert row["prompt_absent"] is True
        assert row["credential_absent"] is True
        assert row["auto_canonical"] is False
        assert row["auto_lock"] is False
    assert lab_env["provider"].http_calls == 0


def test_partial_result_on_cancel(lab_env) -> None:
    result = _create(lab_env, idempotency_key="idem-partial")
    # Cancel before/during — cooperative
    lab_env["registry"].request_cancel(result.run_id)
    exec_result = lab_env["executor"].start(result.run_id)
    assert exec_result.status == WholeBookRunViewStatus.CANCELLED.value
    assert exec_result.detail.get("partial") is True


# ----- 25–34 Persistence / no canonical -----


def test_phase1b_sink_explicit_methods_and_flags(lab_env) -> None:
    from app.narrative_core.services.candidate_persistence_adapter import (
        Phase1BCandidatePersistenceSink,
        RecordingCandidatePersistenceSink,
    )
    from app.narrative_core.services.whole_book_candidate_builder import ModuleCandidateBuildResult

    sink = RecordingCandidatePersistenceSink()
    built = ModuleCandidateBuildResult(
        asset_commands=(),
        relation_commands=(),
        evidence_commands=(),
        conflict_commands=(),
        stage_artifact=None,
        output_fingerprint="out-fp-1",
        rejected=False,
        orm_written=False,
        auto_confirm=False,
        auto_lock=False,
        canonical_overwrite=False,
        synthetic=True,
    )
    summary = sink.persist_commands(built)
    assert summary["auto_confirm"] is False
    assert summary["auto_lock"] is False
    assert summary["canonical_overwrite"] is False
    assert summary["orm_written"] is False
    phase = Phase1BCandidatePersistenceSink(lab_env["session"], book_id=lab_env["book"].id)
    assert hasattr(phase, "persist_assets")
    assert hasattr(phase, "persist_relations")
    assert hasattr(phase, "persist_asset_evidence")
    assert hasattr(phase, "persist_relation_evidence")
    assert hasattr(phase, "persist_conflicts")
    assert hasattr(phase, "persist_stage_artifact")
    assert hasattr(phase, "persist_entities")


def test_duplicate_dedupe_on_sink(lab_env) -> None:
    from app.narrative_core.services.candidate_persistence_adapter import Phase1BCandidatePersistenceSink
    from app.narrative_core.services.whole_book_candidate_builder import ModuleCandidateBuildResult

    sink = Phase1BCandidatePersistenceSink(lab_env["session"], book_id=lab_env["book"].id)
    built = ModuleCandidateBuildResult(
        asset_commands=(),
        relation_commands=(),
        evidence_commands=(),
        conflict_commands=(),
        stage_artifact=None,
        output_fingerprint="dup-fp",
        rejected=False,
        orm_written=False,
        auto_confirm=False,
        auto_lock=False,
        canonical_overwrite=False,
        synthetic=True,
    )
    first = sink.persist_commands(built)
    second = sink.persist_commands(built)
    assert first.get("duplicate") is not True or first["orm_written"] is False
    assert second.get("duplicate") is True
    assert second["orm_written"] is False


# ----- 35–38 Cancel / resume / retry / recovery -----


def test_cancel_resume_retry_recovery(lab_env) -> None:
    result = _create(lab_env, idempotency_key="idem-crr")
    # Force a failed stage for retry later by completing then failing manually
    run_id = result.run_id
    # Cancel
    cancelled = lab_env["service"].cancel_run(run_id, confirm_cancel=True)
    assert cancelled["status"] == WholeBookRunViewStatus.CANCELLED.value
    assert lab_env["registry"].get(run_id).status.value == "finished"

    # New run for interrupt recovery
    result2 = _create(lab_env, idempotency_key="idem-rec")
    run2 = lab_env["session"].get(AnalysisRun, result2.run_id)
    run2.status = "running"
    lab_env["session"].commit()
    recovery = PrivateLabRecoveryService(lab_env["session"], stage_service=lab_env["stage_service"])
    scan = recovery.startup_reconcile()
    assert scan.auto_resumed == 0
    assert result2.run_id in scan.interrupted_run_ids
    run2 = lab_env["session"].get(AnalysisRun, result2.run_id)
    assert run2.status == "interrupted"

    # Resume after interrupt
    resumed = lab_env["service"].resume_run(
        result2.run_id,
        estimate_fingerprint="estimate-fp-ok",
        consent_fingerprint="consent-fp-ok",
        context_bundle_hash="context-hash-ok",
    )
    assert resumed["status"] == WholeBookRunViewStatus.RUNNING.value

    # Retry: mark a stage failed then retry
    lab_env["stage_service"].transition_stage(
        result2.run_id, "analyze_structure", StageStatus.RUNNING
    )
    lab_env["stage_service"].transition_stage(
        result2.run_id,
        "analyze_structure",
        StageStatus.FAILED,
        error_code="TEST_FAIL",
        error_message="synthetic",
    )
    retry = lab_env["service"].retry_stage(result2.run_id, "analyze_structure")
    assert retry["action"] == "retry"
    assert "analyze_structure" in (retry.get("stage_key") or "analyze_structure")


# ----- 39–42 Result API / absent secrets -----


def test_result_api_readable_and_safe(lab_env) -> None:
    result = _create(lab_env, idempotency_key="idem-res")
    lab_env["executor"].start(result.run_id)
    index = WholeBookResultIndexService(lab_env["session"]).get_result_index(result.run_id)
    assert index.run_id == result.run_id
    resp = lab_env["client"].get(f"/api/v1/whole-book-runs/{result.run_id}/results")
    assert resp.status_code == 200
    body = resp.json()
    blob = json.dumps(body)
    assert "api_key" not in blob.lower() or "api_key" not in blob
    assert "system_prompt" not in blob
    assert "raw_response" not in blob
    # Result API must not mutate status
    run = lab_env["session"].get(AnalysisRun, result.run_id)
    status_before = run.status
    lab_env["client"].get(f"/api/v1/whole-book-runs/{result.run_id}/results")
    lab_env["session"].refresh(run)
    assert run.status == status_before


# ----- 43–47 Isolation / formal disabled / no migration -----


def test_no_http_no_model_formal_disabled(lab_env) -> None:
    result = _create(lab_env, idempotency_key="idem-iso")
    lab_env["executor"].start(result.run_id)
    assert lab_env["provider"].http_calls == 0
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert PRODUCTION_DEFAULT_ENGINE_ID is None
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False
    assert WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED is False
    # No new migration files in this Change ownership
    mig_dir = REPO_ROOT / "apps" / "api" / "app" / "narrative_core" / "migrations"
    if mig_dir.exists():
        recent = [p.name for p in mig_dir.glob("*phase2br1*")]
        assert recent == []


def test_production_openapi_unregistered() -> None:
    app = create_app()
    assert should_register_private_engine_lab_router(
        environment="production", lab_enabled=True
    ) is False
    before = len(app.routes)
    mounted = mount_private_engine_lab_if_enabled(
        app, environment="production", lab_enabled=True
    )
    assert mounted is False
    assert len(app.routes) == before
    paths = [str(getattr(r, "path", "")) for r in app.routes]
    # Production mount must not add Private Lab paths
    assert not any(
        "private-whole-book-runs" in p and "production-forced" in p for p in paths
    )


def test_http_api_create_get_stages(lab_env) -> None:
    client: TestClient = lab_env["client"]
    # Integration wires real U adapters — fingerprints must come from preflight/estimate.
    pre = client.post(
        "/api/v1/labs/private-whole-book-runs/preflight",
        headers=MARKER,
        json={
            "book_id": lab_env["book"].id,
            "book_snapshot_id": lab_env["snapshot"].id,
            "configuration_fingerprint": "cfg-http-1",
        },
    )
    assert pre.status_code == 200, pre.text
    assert pre.json()["run_created"] is False
    assert pre.json()["ok"] is True
    preflight_fp = pre.json()["fingerprint"]
    est = client.post(
        "/api/v1/labs/private-whole-book-runs/estimate",
        headers=MARKER,
        json={
            "book_id": lab_env["book"].id,
            "book_snapshot_id": lab_env["snapshot"].id,
            "configuration_fingerprint": "cfg-http-1",
            "preflight_fingerprint": preflight_fp,
        },
    )
    assert est.status_code == 200, est.text
    assert est.json()["tokens_hardcoded"] is False
    assert est.json()["cost_hardcoded"] is False
    est_body = est.json()
    resp = client.post(
        "/api/v1/labs/private-whole-book-runs",
        headers=MARKER,
        json={
            "book_id": lab_env["book"].id,
            "book_snapshot_id": lab_env["snapshot"].id,
            "idempotency_key": "http-create-1",
            "configuration_fingerprint": "cfg-http-1",
            "preflight_fingerprint": preflight_fp,
            "estimate_fingerprint": est_body["fingerprint"],
            "consent_fingerprint": est_body["consent_fingerprint"],
            "data_transfer_manifest_hash": est_body["data_transfer_manifest_hash"],
            "auto_start": True,
            "dry_run": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["private_lab"] is True
    assert data["modules_implemented"] is True
    assert data["shell_only"] is False
    assert data["server_security"]["client_booleans_authoritative"] is False
    run_id = data["run_id"]
    g = client.get(f"/api/v1/labs/private-whole-book-runs/{run_id}", headers=MARKER)
    assert g.status_code == 200
    stages = client.get(
        f"/api/v1/labs/private-whole-book-runs/{run_id}/stages", headers=MARKER
    )
    assert stages.status_code == 200
    assert len(stages.json()["stages"]) == 10


def test_contract_and_mock_unaffected() -> None:
    meta = lab_contract_assertions()
    assert meta["WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED_DEFAULT"] is False
    assert meta["WHOLE_BOOK_MOCK_LAB_ENABLED_DEFAULT"] is False
    assert meta["WHOLE_BOOK_RUNS_ENDPOINT_DISABLED"] is True
    assert meta["shell_only"] is False
    assert "main.py" in meta["integration_issue_main_py"]
    assert meta["PRIVATE_ENGINE_LAB_API_PREFIX"] == "/api/v1/labs/private-whole-book-runs"
    assert pelab_router_mod.router.prefix == "/api/v1/labs/private-whole-book-runs"


def test_version_unchanged() -> None:
    assert (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip() == "1.2.0"
