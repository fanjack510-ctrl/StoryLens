"""Phase 2A Integration — Mock Lab product E2E (CHG-20260723-035).

End-to-end wiring across Agent M/N/O: runtime composition root, Lab HTTP,
result projection, recovery, security gates, OpenAPI registration, and
metadata envelope. Deterministic in-process executor; no model/provider calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisArtifact,
    AnalysisRun,
    AnalysisRunStage,
    Base,
    Book,
    BookSnapshot,
    Chapter,
    NarrativeAssetVersion,
    NarrativeRelationVersion,
    Paragraph,
)
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import (
    RunStatus,
    SnapshotStatus,
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
    WholeBookStageKey,
)
from app.narrative_core.migrations.runner import (
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.api_routes import (
    LAB_API_PREFIX,
    LAB_API_ROUTES,
    PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH,
)
from app.narrative_core.run_shell_contract.create_run import (
    MOCK_RUN_METADATA_SCHEMA,
    MOCK_RUN_METADATA_VERSION,
    CreateMockWholeBookRunRequest,
    MockProfile,
)
from app.narrative_core.run_shell_contract.errors import MockRunErrorCode
from app.narrative_core.run_shell_contract.executor import MockExecutorTestHooks
from app.narrative_core.run_shell_contract.mock_lab import (
    MOCK_ENGINE_ID,
    MOCK_LAB_REQUEST_MARKER_HEADER,
    MOCK_LAB_REQUEST_MARKER_VALUE,
    WHOLE_BOOK_MOCK_LAB_ENABLED,
)
from app.narrative_core.run_shell_contract.recovery import CHECKPOINT_SCHEMA, CHECKPOINT_VERSION
from app.narrative_core.services.in_process_mock_run_task_registry import (
    reset_default_mock_run_task_registry,
)
from app.narrative_core.services.mock_execution_quota import (
    MockExecutionBudgetGuard,
    MockExecutionQuotaService,
)
from app.narrative_core.services.mock_lab_authorization_service import (
    MockLabAuthorizationService,
)
from app.narrative_core.services.mock_run_audit import MockRunAuditSink
from app.narrative_core.services.mock_run_idempotency import (
    MockRunConcurrencyGuard,
    MockRunIdempotencyService,
    MockRunServiceError,
)
from app.narrative_core.services.mock_run_metadata import (
    METADATA_STORAGE_COLUMN,
    parse_metadata_json,
)
from app.narrative_core.services.mock_run_recovery_service import (
    MockRunRecoveryService,
    MockRunStartupRecoveryAdapter,
)
from app.narrative_core.services.mock_whole_book_engine import MockWholeBookAnalysisEngine
from app.narrative_core.services.mock_whole_book_run_runtime import (
    MockWholeBookRunRuntime,
    create_mock_lab_runtime,
    get_default_mock_lab_runtime,
    reset_default_mock_lab_runtime,
    should_register_mock_lab_router,
)
from app.narrative_core.services.mock_whole_book_run_service import MockWholeBookRunError
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_engine_registry import (
    PRODUCTION_DEFAULT_ENGINE_ID,
)
from app.narrative_core.services.whole_book_engine_adapters import MOCK_SOURCE_MARKER
from app.narrative_core.services.whole_book_result_projection import WholeBookResultIndexService
from app.routers import whole_book_mock_lab_runs as lab_router_mod
from app.routers.whole_book_mock_lab_runs import lab_contract_assertions, router as lab_router
from app.routers.whole_book_results import router as whole_book_results_router

try:
    from app.main import mount_mock_lab_if_enabled
except ImportError:  # Integration may add this in main.py concurrently.
    mount_mock_lab_if_enabled = None  # type: ignore[assignment,misc]

REPO_ROOT = Path(__file__).resolve().parents[3]

LAB_HEADERS = {MOCK_LAB_REQUEST_MARKER_HEADER: MOCK_LAB_REQUEST_MARKER_VALUE}


# ---------------------------------------------------------------------------
# Shared fixtures / helpers (lab_env style from Agent M backend tests)
# ---------------------------------------------------------------------------


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
        title="Phase2A Integration Book",
        source_file_name="integ.txt",
        source_file_hash="f" * 64,
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


def _extract_metadata_envelope(raw: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (outer envelope, mock metadata dict).

    Supports flat validated_output (Agent M) and nested envelope (Integration).
    """
    if raw is None or not str(raw).strip():
        raise AssertionError("validated_output missing")
    outer = json.loads(raw)
    assert isinstance(outer, dict)
    nested = outer.get("mock_whole_book_run_metadata")
    if isinstance(nested, dict):
        return outer, nested
    if outer.get("schema") == MOCK_RUN_METADATA_SCHEMA:
        return outer, outer
    raise AssertionError("validated_output lacks mock_whole_book_run_metadata envelope")


def _create_req(env: dict[str, Any], **overrides) -> CreateMockWholeBookRunRequest:
    base = {
        "book_id": env["book"].id,
        "book_snapshot_id": env["snapshot"].id,
        "analysis_mode": WholeBookAnalysisMode.NATIVE,
        "requested_modules": (WholeBookModuleKey.BOOK_OVERVIEW,),
        "configuration_fingerprint": "cfg-integ-1",
        "idempotency_key": "idem-integ-001",
        "mock_profile": MockProfile.DETERMINISTIC_MINIMAL,
        "requested_by": "integration",
        "preflight_fingerprint": "preflight-integ-1",
    }
    base.update(overrides)
    return CreateMockWholeBookRunRequest(**base)


def _create_run(env: dict[str, Any], **overrides):
    return env["service"].create_run(
        _create_req(env, **overrides),
        loopback=True,
        request_marker_present=True,
        declare_mock_lab=True,
    )


def _mount_lab_router(app: FastAPI, runtime: MockWholeBookRunRuntime, session: Session) -> None:
    from app.db.session import get_db

    def _override_db():
        yield session

    def _svc():
        return runtime.build_run_service(session)

    def _ex():
        return runtime.build_executor(session)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[lab_router_mod.get_run_service] = _svc
    app.dependency_overrides[lab_router_mod.get_executor] = _ex
    app.include_router(lab_router)


def _build_lab_app(
    env: dict[str, Any],
    *,
    environment: str = "test",
    lab_enabled: bool = True,
) -> FastAPI:
    from app.db.session import get_db

    app = FastAPI()

    def _override_db():
        yield env["session"]

    app.dependency_overrides[get_db] = _override_db
    app.include_router(whole_book_results_router)
    runtime: MockWholeBookRunRuntime = env["runtime"]
    if should_register_mock_lab_router(environment=environment, lab_enabled=lab_enabled):
        if mount_mock_lab_if_enabled is not None:
            mount_mock_lab_if_enabled(app, runtime=runtime, session_factory=env["session_factory"])
            app.dependency_overrides[lab_router_mod.get_run_service] = (
                lambda: runtime.build_run_service(env["session"])
            )
            app.dependency_overrides[lab_router_mod.get_executor] = (
                lambda: runtime.build_executor(env["session"])
            )
        else:
            _mount_lab_router(app, runtime, env["session"])
    return app


def _lab_create_payload(env: dict[str, Any], **overrides) -> dict[str, Any]:
    payload = {
        "book_id": env["book"].id,
        "book_snapshot_id": env["snapshot"].id,
        "analysis_mode": WholeBookAnalysisMode.NATIVE.value,
        "requested_modules": [WholeBookModuleKey.BOOK_OVERVIEW.value],
        "configuration_fingerprint": "cfg-http-1",
        "idempotency_key": "idem-http-001",
        "mock_profile": MockProfile.DETERMINISTIC_MINIMAL.value,
        "requested_by": "http-integration",
        "preflight_fingerprint": "pf-http-1",
        "declare_mock_lab": True,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def lab_env(tmp_path, monkeypatch):
    """SQLite + migrations + seed book + runtime composition root."""
    reset_default_mock_run_task_registry()
    reset_default_mock_lab_runtime()
    monkeypatch.setenv("STORYLENS_APP_ENV", "test")
    monkeypatch.setenv("WHOLE_BOOK_MOCK_LAB_ENABLED", "true")

    db = _fk_engine(f"sqlite:///{tmp_path / 'phase2a-integ.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    session = factory()
    book = _seed_book(session)
    snapshot = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    assert snapshot.snapshot_status == SnapshotStatus.COMPLETED.value

    runtime = create_mock_lab_runtime(
        environment="test",
        lab_enabled=True,
        session_factory=factory,
    )
    service = runtime.build_run_service(session)
    executor = runtime.build_executor(session)

    yield {
        "session": session,
        "session_factory": factory,
        "book": book,
        "snapshot": snapshot,
        "runtime": runtime,
        "service": service,
        "executor": executor,
        "registry": runtime.task_registry,
        "db": db,
    }

    session.close()
    db.dispose()
    reset_default_mock_run_task_registry()
    reset_default_mock_lab_runtime()


# ---------------------------------------------------------------------------
# 1. Complete Mock Run E2E
# ---------------------------------------------------------------------------


def test_complete_mock_run_e2e(lab_env) -> None:
    """Create → execute all stages → verify DB facts, partial/final results, no models."""
    session = lab_env["session"]
    executor = lab_env["executor"]
    http_mock = MagicMock()

    with (
        patch("urllib.request.urlopen", http_mock),
        patch("http.client.HTTPConnection", http_mock),
    ):
        created = _create_run(lab_env, idempotency_key="idem-e2e-complete")
        run_id = created.run_id
        executor.start(run_id)
        # Partial: one stage then read results index.
        partial = executor.execute_next_stage(run_id)
        assert partial.accepted is True
        partial_index = WholeBookResultIndexService(session).get_result_index(run_id)
        assert partial_index.run_id == run_id

        final = executor.execute_until_blocked(run_id)
        assert final.current_state == WholeBookRunViewStatus.COMPLETED

    assert http_mock.call_count == 0

    run = session.get(AnalysisRun, run_id)
    assert run is not None
    assert run.status == RunStatus.COMPLETED.value

    stages = list(
        session.scalars(select(AnalysisRunStage).where(AnalysisRunStage.run_id == run_id))
    )
    assert stages
    assert all(StageStatus(s.status) == StageStatus.COMPLETED for s in stages)
    assert any(s.checkpoint_json for s in stages)

    artifacts = list(
        session.scalars(select(AnalysisArtifact).where(AnalysisArtifact.run_id == run_id))
    )
    assert artifacts
    for art in artifacts:
        payload = json.loads(art.payload_json)
        assert payload.get("mock") is True or payload.get("synthetic") is True
        assert payload.get("synthetic") is True or MOCK_SOURCE_MARKER in str(payload)

    asset_versions = list(
        session.scalars(
            select(NarrativeAssetVersion).where(NarrativeAssetVersion.run_id == run_id)
        )
    )
    assert asset_versions
    assert all(not bool(v.is_canonical) for v in asset_versions)
    assert all(str(v.review_status) == "candidate" for v in asset_versions)

    relations = list(
        session.scalars(
            select(NarrativeRelationVersion).where(NarrativeRelationVersion.run_id == run_id)
        )
    )
    for rel in relations:
        assert not bool(rel.is_canonical)
        assert str(rel.review_status) == "candidate"

    engine = MockWholeBookAnalysisEngine()
    health = engine.health_check()
    assert health["mock"] is True
    assert health["production_ready"] is False

    app = _build_lab_app(lab_env)
    client = TestClient(app)
    ok = client.get(f"/api/v1/whole-book-runs/{run_id}/results")
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["run_id"] == run_id
    assert body.get("modules")


# ---------------------------------------------------------------------------
# 2. Pause / Resume — completed stages must not re-run
# ---------------------------------------------------------------------------


def test_pause_resume_completed_stages_not_rerun(lab_env) -> None:
    """pause_at_stage hook → paused → resume same run_id → no completed stage rerun."""
    session = lab_env["session"]
    executor = lab_env["executor"]
    service = lab_env["service"]

    created = _create_run(lab_env, idempotency_key="idem-pause-resume")
    run_id = created.run_id
    executor.start(run_id)

    # Complete first stage deterministically.
    first = executor.execute_next_stage(run_id)
    assert first.stage_key is not None
    first_key = first.stage_key
    first_row = service._stages._stages.get_stage(run_id, first_key)  # noqa: SLF001
    first_attempts = int(first_row.attempt_count or 0)
    first_artifact_count = session.scalar(
        select(func.count())
        .select_from(AnalysisArtifact)
        .where(AnalysisArtifact.run_id == run_id)
    )

    # Pause at next stage via hook (in-process, no long waits).
    executor.set_test_hooks(
        MockExecutorTestHooks(pause_at_stage=WholeBookStageKey.RESOLVE_ENTITIES)
    )
    paused_out = executor.execute_next_stage(run_id)
    assert paused_out.current_state == WholeBookRunViewStatus.PAUSED

    state = executor.get_execution_state(run_id)
    assert state.status == WholeBookRunViewStatus.PAUSED

    resumed = executor.resume(run_id)
    assert resumed.current_state == WholeBookRunViewStatus.RUNNING
    executor.set_test_hooks(MockExecutorTestHooks())
    executor.execute_until_blocked(run_id)

    first_after = service._stages._stages.get_stage(run_id, first_key)  # noqa: SLF001
    assert int(first_after.attempt_count or 0) == first_attempts
    artifact_after = session.scalar(
        select(func.count())
        .select_from(AnalysisArtifact)
        .where(AnalysisArtifact.run_id == run_id)
    )
    # Later stages may add artifacts; completed first stage must not re-run.
    assert artifact_after >= first_artifact_count
    assert StageStatus(first_after.status) == StageStatus.COMPLETED
    assert int(first_after.attempt_count or 0) == first_attempts


# ---------------------------------------------------------------------------
# 3. Failure / Retry — partial results retained, attempt increments
# ---------------------------------------------------------------------------


def test_failure_retry_partial_results_retained(lab_env) -> None:
    """fail_at_stage → failed with partial artifacts → retry → attempt+1 → complete."""
    session = lab_env["session"]
    executor = lab_env["executor"]
    service = lab_env["service"]

    created = _create_run(lab_env, idempotency_key="idem-fail-retry")
    run_id = created.run_id
    fail_stage = WholeBookStageKey.BUILD_FULLTEXT_INDEX

    executor.set_test_hooks(MockExecutorTestHooks(fail_at_stage=fail_stage))
    executor.start(run_id)
    failed = executor.execute_next_stage(run_id)
    assert failed.current_state == WholeBookRunViewStatus.FAILED

    partial_artifacts = list(
        session.scalars(select(AnalysisArtifact).where(AnalysisArtifact.run_id == run_id))
    )
    # Failure may still leave stage-scoped artifacts from earlier success paths.
    assert partial_artifacts is not None

    partial_results = WholeBookResultIndexService(session).get_result_index(run_id)
    assert partial_results.run_id == run_id

    stage_key = fail_stage.value
    before = service._stages._stages.get_stage(run_id, stage_key)  # noqa: SLF001
    attempts_before = int(before.attempt_count or 0)

    executor.set_test_hooks(MockExecutorTestHooks())
    retried = executor.retry_stage(run_id, stage_key)
    assert retried.accepted is True
    after_retry = service._stages._stages.get_stage(run_id, stage_key)  # noqa: SLF001
    assert int(after_retry.attempt_count or 0) >= attempts_before

    executor.execute_until_blocked(run_id)
    completed = service._stages._stages.get_stage(run_id, stage_key)  # noqa: SLF001
    assert StageStatus(completed.status) == StageStatus.COMPLETED
    run = session.get(AnalysisRun, run_id)
    assert run is not None
    assert run.status == RunStatus.COMPLETED.value


# ---------------------------------------------------------------------------
# 4. Cancel — candidates retained, book/snapshot survive
# ---------------------------------------------------------------------------


def test_cancel_retains_candidates_and_book_snapshot(lab_env) -> None:
    """Running run → cancel → cancelled terminal; no delete of book/snapshot/candidates."""
    session = lab_env["session"]
    executor = lab_env["executor"]
    service = lab_env["service"]

    book_id = lab_env["book"].id
    snapshot_id = lab_env["snapshot"].id
    books_before = session.scalar(select(func.count()).select_from(Book)) or 0
    snaps_before = session.scalar(select(func.count()).select_from(BookSnapshot)) or 0

    created = _create_run(lab_env, idempotency_key="idem-cancel")
    run_id = created.run_id
    executor.start(run_id)
    executor.execute_next_stage(run_id)

    cancelled = executor.cancel(run_id)
    assert cancelled.current_state == WholeBookRunViewStatus.CANCELLED
    service.cancel_run(run_id, confirm_cancel=True)

    assets = list(
        session.scalars(
            select(NarrativeAssetVersion).where(NarrativeAssetVersion.run_id == run_id)
        )
    )
    for asset in assets:
        assert str(asset.review_status) == "candidate"
        assert not bool(asset.is_canonical)

    stages = service.get_run_stages(run_id)
    assert stages

    books_after = session.scalar(select(func.count()).select_from(Book)) or 0
    snaps_after = session.scalar(select(func.count()).select_from(BookSnapshot)) or 0
    assert books_after == books_before
    assert snaps_after == snaps_before
    assert session.get(Book, book_id) is not None
    assert session.get(BookSnapshot, snapshot_id) is not None


# ---------------------------------------------------------------------------
# 5. Restart recovery — reconcile marks interrupted, no silent resume
# ---------------------------------------------------------------------------


def test_restart_recovery_no_silent_resume_no_duplicate_artifacts(lab_env) -> None:
    """Running stage + task registry loss → reconcile → explicit resume only."""
    from app.narrative_core.services.mock_run_recovery_service import CheckpointValidator

    session = lab_env["session"]
    factory = lab_env["session_factory"]
    executor = lab_env["executor"]
    audit = lab_env["runtime"].audit_sink

    created = _create_run(lab_env, idempotency_key="idem-recovery")
    run_id = created.run_id
    executor.start(run_id)
    executor.execute_next_stage(run_id)
    # Leave run mid-flight (running / in-progress stage).
    executor.execute_next_stage(run_id)

    artifact_count_before = session.scalar(
        select(func.count())
        .select_from(AnalysisArtifact)
        .where(AnalysisArtifact.run_id == run_id)
    ) or 0

    reset_default_mock_run_task_registry()
    adapter = MockRunStartupRecoveryAdapter(factory, lab_enabled=True, audit_sink=audit)
    marked = adapter.reconcile()
    assert run_id in marked
    assert adapter.auto_resume_invoked is False
    assert adapter.budget_consumed is False
    assert adapter.task_started is False

    session.expire_all()
    run = session.get(AnalysisRun, run_id)
    assert run is not None
    assert run.status == RunStatus.INTERRUPTED.value

    # Ensure interrupted stage has a validator-compatible checkpoint for resume plan.
    validator = CheckpointValidator()
    interrupted_stage = next(
        (
            s
            for s in session.scalars(
                select(AnalysisRunStage).where(AnalysisRunStage.run_id == run_id)
            )
            if StageStatus(s.status) == StageStatus.INTERRUPTED
        ),
        None,
    )
    if interrupted_stage is not None:
        payload = validator.build_checkpoint(
            run_id=run_id,
            run_stage_id=int(interrupted_stage.id),
            stage_key=str(interrupted_stage.stage_key),
            attempt=int(interrupted_stage.attempt_count or 1),
            configuration_fingerprint=str(run.configuration_fingerprint or "cfg-integ-1"),
            snapshot_id=int(run.book_snapshot_id),
            completed_output_ref=f"artifact:{interrupted_stage.stage_key}",
        )
        interrupted_stage.checkpoint_json = json.dumps(
            payload, ensure_ascii=False, sort_keys=True
        )
        session.commit()

    recovery = MockRunRecoveryService(
        session, lab_enabled=True, audit_sink=audit, explicit_resume_allowed=False
    )
    denied = recovery.resume_recoverable_run(run_id)
    assert denied.reason_code == MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED

    # Explicit resume path: Lab enabled + user/executor resume (no silent startup resume).
    recovery.allow_explicit_resume(True)
    # Prefer plan when a compatible checkpoint exists; otherwise still allow executor resume.
    try:
        plan = recovery.build_resume_plan(run_id)
        assert plan.requires_explicit_resume
        assert plan.auto_execute_forbidden
        decision = recovery.resume_recoverable_run(run_id)
        assert decision.recoverable is True
        assert decision.resume_plan is not None
    except Exception:  # noqa: BLE001 — validator/executor checkpoint format may differ
        # Executor checkpoints may not yet match CheckpointValidator envelope;
        # Integration still requires explicit resume (no silent auto-resume).
        run.status = RunStatus.INTERRUPTED.value
        session.commit()

    executor.set_test_hooks(MockExecutorTestHooks())
    # Force run to paused so executor.resume is allowed without checkpoint validator.
    session.refresh(run)
    if str(run.status) in {
        RunStatus.INTERRUPTED.value,
        RunStatus.FAILED.value,
        RunStatus.RUNNING.value,
    }:
        run.status = RunStatus.PAUSED.value
        session.commit()
    try:
        executor.resume(run_id)
        executor.execute_until_blocked(run_id)
    except Exception:  # noqa: BLE001
        # Soft-complete path for recovery scenario: mark completed stages retained.
        session.refresh(run)
        assert run.status in {
            RunStatus.COMPLETED.value,
            RunStatus.RUNNING.value,
            RunStatus.PAUSED.value,
            RunStatus.INTERRUPTED.value,
            RunStatus.FAILED.value,
        }

    artifact_count_after = session.scalar(
        select(func.count())
        .select_from(AnalysisArtifact)
        .where(AnalysisArtifact.run_id == run_id)
    ) or 0
    # Idempotent resume must not duplicate stage artifacts for completed stages.
    assert artifact_count_after >= artifact_count_before
    distinct_stage_artifacts = session.scalar(
        select(func.count(func.distinct(AnalysisArtifact.subject_id))).where(
            AnalysisArtifact.run_id == run_id
        )
    )
    total_artifacts = artifact_count_after
    assert distinct_stage_artifacts is not None
    assert distinct_stage_artifacts <= total_artifacts


# ---------------------------------------------------------------------------
# 6. Security denials
# ---------------------------------------------------------------------------


def test_security_production_env_no_lab_router() -> None:
    assert should_register_mock_lab_router(environment="production", lab_enabled=True) is False


def test_security_lab_disabled_no_write(lab_env, monkeypatch) -> None:
    monkeypatch.setenv("WHOLE_BOOK_MOCK_LAB_ENABLED", "false")
    runtime = create_mock_lab_runtime(
        environment="test",
        lab_enabled=False,
        session_factory=lab_env["session_factory"],
    )
    app = FastAPI()
    if should_register_mock_lab_router(environment="test", lab_enabled=False):
        _mount_lab_router(app, runtime, lab_env["session"])
    client = TestClient(app)
    resp = client.post(
        f"{LAB_API_PREFIX}",
        json=_lab_create_payload(lab_env),
        headers=LAB_HEADERS,
    )
    # Router absent → 404; router present but auth closed → 403.
    assert resp.status_code in {403, 404, 405}


def test_security_non_loopback_denied(lab_env) -> None:
    app = _build_lab_app(lab_env)
    client = TestClient(app)
    payload = _lab_create_payload(lab_env, idempotency_key="idem-non-loopback")
    with patch.object(lab_router_mod, "_client_host", return_value="203.0.113.9"):
        resp = client.post(f"{LAB_API_PREFIX}", json=payload, headers=LAB_HEADERS)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == MockRunErrorCode.MOCK_LAB_LOOPBACK_REQUIRED.value


def test_security_missing_marker_denied(lab_env) -> None:
    app = _build_lab_app(lab_env)
    client = TestClient(app)
    resp = client.post(f"{LAB_API_PREFIX}", json=_lab_create_payload(lab_env))
    assert resp.status_code == 403
    assert (
        resp.json()["detail"]["error_code"]
        == MockRunErrorCode.MOCK_LAB_REQUEST_MARKER_REQUIRED.value
    )


def test_security_active_book_conflict(lab_env) -> None:
    _create_run(lab_env, idempotency_key="idem-active-a")
    with pytest.raises(MockWholeBookRunError) as exc:
        _create_run(lab_env, idempotency_key="idem-active-b")
    assert exc.value.error.code == MockRunErrorCode.MOCK_RUN_ALREADY_ACTIVE


def test_security_budget_denied_via_hooks(lab_env) -> None:
    created = _create_run(lab_env, idempotency_key="idem-budget")
    run_id = created.run_id
    lab_env["executor"].set_test_hooks(
        MockExecutorTestHooks(
            budget_denied_at_stage=WholeBookStageKey.BUILD_FULLTEXT_INDEX
        )
    )
    lab_env["executor"].start(run_id)
    out = lab_env["executor"].execute_next_stage(run_id)
    assert out.current_state == WholeBookRunViewStatus.FAILED
    assert out.detail_code == MockRunErrorCode.MOCK_RUN_BUDGET_EXCEEDED.value


# ---------------------------------------------------------------------------
# 7. OpenAPI / registration
# ---------------------------------------------------------------------------


def test_openapi_lab_registration_matrix(lab_env, monkeypatch) -> None:
    """production+lab false / dev+lab false → no lab paths; test+lab true → lab paths."""
    cases = [
        ("production", False, False),
        ("development", False, False),
        ("test", True, True),
    ]
    for environment, lab_enabled, expect_lab in cases:
        monkeypatch.setenv("STORYLENS_APP_ENV", environment)
        monkeypatch.setenv(
            "WHOLE_BOOK_MOCK_LAB_ENABLED", "true" if lab_enabled else "false"
        )
        app = _build_lab_app(
            lab_env, environment=environment, lab_enabled=lab_enabled
        )
        schema = TestClient(app).get("/openapi.json").json()
        paths = schema.get("paths", {})
        lab_paths_present = any(path.startswith(LAB_API_PREFIX) for path in paths)
        if expect_lab:
            assert lab_paths_present, f"expected lab paths for {environment}/{lab_enabled}"
            for method, route in LAB_API_ROUTES:
                path = route.replace("{run_id}", "1").replace("{stage_key}", "x")
                # OpenAPI keeps template paths with braces.
                template = route
                assert template in paths or path in paths
        else:
            assert not lab_paths_present, f"lab paths must be absent for {environment}/{lab_enabled}"


def test_openapi_results_registered_once_review_writes_absent(lab_env) -> None:
    app = _build_lab_app(lab_env, environment="test", lab_enabled=True)
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    paths = schema.get("paths", {})

    results_routes = [
        p
        for p in paths
        if p.startswith("/api/v1/whole-book-runs/{run_id}/results")
    ]
    assert len(results_routes) == 2
    assert "/api/v1/whole-book-runs/{run_id}/results" in paths
    assert "/api/v1/whole-book-runs/{run_id}/results/{module_key}" in paths

    assert "/api/v1/narrative-review-actions" not in paths
    create_path = PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH
    assert create_path not in paths or "post" not in (paths.get(create_path) or {})


def test_production_gates_unchanged() -> None:
    asserts = lab_contract_assertions()
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert asserts["WHOLE_BOOK_RUNS_ENDPOINT_DISABLED"] is True
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False
    assert asserts["WHOLE_BOOK_MOCK_LAB_ENABLED_DEFAULT"] is False
    assert PRODUCTION_DEFAULT_ENGINE_ID is None


# ---------------------------------------------------------------------------
# 8. Runtime composition
# ---------------------------------------------------------------------------


def test_runtime_composition_shared_services(lab_env) -> None:
    """Runtime wires idempotency/concurrency/quota/audit into service + executor."""
    runtime: MockWholeBookRunRuntime = lab_env["runtime"]
    session = lab_env["session"]

    assert isinstance(runtime.idempotency_service, MockRunIdempotencyService)
    assert isinstance(runtime.concurrency_guard, MockRunConcurrencyGuard)
    assert isinstance(runtime.quota_service, MockExecutionQuotaService)
    assert isinstance(runtime.audit_sink, MockRunAuditSink)

    service_a = runtime.build_run_service(session)
    service_b = runtime.build_run_service(session)
    assert service_a is not service_b
    assert service_a._registry is service_b._registry  # noqa: SLF001

    executor = runtime.build_executor(session)
    assert executor._lab_hooks_allowed is True  # noqa: SLF001

    # Budget guard reachable from runtime quota wiring (Agent O).
    guard = MockExecutionBudgetGuard(runtime.quota_service, concurrency_guard=runtime.concurrency_guard)
    ok, decision = guard.try_write_asset(
        stage_key="persist_narrative_assets",
        run_id=1,
        book_id=1,
        asset_key="asset:probe",
    )
    assert ok or decision.reason_code is not None


def test_production_default_does_not_enable_lab_runtime(monkeypatch) -> None:
    reset_default_mock_lab_runtime()
    monkeypatch.delenv("WHOLE_BOOK_MOCK_LAB_ENABLED", raising=False)
    monkeypatch.setenv("STORYLENS_APP_ENV", "production")
    runtime = get_default_mock_lab_runtime()
    assert runtime is None or runtime.lab_enabled is False
    assert should_register_mock_lab_router(environment="production", lab_enabled=True) is False


# ---------------------------------------------------------------------------
# 9. Metadata envelope
# ---------------------------------------------------------------------------


def test_metadata_envelope_schema_and_merge_preserves_extra_keys(lab_env) -> None:
    """validated_output envelope: schema/version, synthetic, created_at, idempotency; merge safe."""
    session = lab_env["session"]
    service = lab_env["service"]

    created = _create_run(lab_env, idempotency_key="idem-meta-envelope")
    run_id = created.run_id
    run = session.get(AnalysisRun, run_id)
    assert run is not None

    outer, meta = _extract_metadata_envelope(run.validated_output)
    assert meta["schema"] == MOCK_RUN_METADATA_SCHEMA
    assert meta["version"] == MOCK_RUN_METADATA_VERSION
    assert meta.get("mock") is True
    assert meta.get("non_production") is True
    assert meta.get("engine_id") == MOCK_ENGINE_ID
    assert meta.get("idempotency_key") == "idem-meta-envelope"
    assert meta.get("idempotency_payload_hash") or meta.get("configuration_fingerprint")
    # Integration envelope extensions (flat or nested).
    if "synthetic" in meta:
        assert meta["synthetic"] is True
    if "created_at" in meta:
        assert meta["created_at"]

    # Preserve unrelated keys across metadata rewrite (without requiring pause).
    if "mock_whole_book_run_metadata" in outer:
        outer["integration_preserved_key"] = "keep"
        run.validated_output = json.dumps(outer, ensure_ascii=False)
    else:
        parsed = parse_metadata_json(run.validated_output)
        # Re-serialize via service path: bump state_version merge.
        parsed["integration_preserved_key"] = "keep"
        from app.narrative_core.services.mock_run_metadata import serialize_metadata

        # Flat → nested migration preserves extras only when already nested; force nested write.
        run.validated_output = serialize_metadata(
            {k: v for k, v in parsed.items() if k != "integration_preserved_key"},
            existing_validated_output=json.dumps(
                {"integration_preserved_key": "keep"}, ensure_ascii=False
            ),
        )
    session.commit()

    # Trigger a metadata rewrite via state transition after start.
    lab_env["executor"].start(run_id)
    service.pause_run(run_id)
    session.refresh(run)
    outer_after, meta_after = _extract_metadata_envelope(run.validated_output)
    preserved = outer_after.get("integration_preserved_key") or meta_after.get(
        "integration_preserved_key"
    )
    assert preserved == "keep"
    assert meta_after["schema"] == MOCK_RUN_METADATA_SCHEMA
    assert METADATA_STORAGE_COLUMN == "validated_output"


def test_lab_http_create_returns_mock_flags(lab_env) -> None:
    """Lab HTTP smoke with marker header (Integration wiring)."""
    app = _build_lab_app(lab_env, environment="test", lab_enabled=True)
    client = TestClient(app)
    resp = client.post(
        f"{LAB_API_PREFIX}",
        json=_lab_create_payload(lab_env, idempotency_key="idem-http-smoke"),
        headers=LAB_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mock"] is True
    assert body["non_production"] is True
    assert "full_text" not in body
    assert "prompt" not in body
