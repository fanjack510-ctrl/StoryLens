"""Phase 2A Agent O — Mock Run recovery / reliability directed tests."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisArtifact,
    AnalysisRun,
    AnalysisRunStage,
    Base,
    Book,
    BookSnapshot,
    Chapter,
)
from app.narrative_core.enums import (
    AnalysisScopeType,
    AnalysisType,
    RunStatus,
    SnapshotStatus,
    StageStatus,
    WholeBookStageKey,
)
from app.narrative_core.migrations.runner import apply_narrative_phase1p_migrations
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.errors import MockRunErrorCode
from app.narrative_core.run_shell_contract.quota import MockExecutionQuotaPolicy
from app.narrative_core.run_shell_contract.recovery import CHECKPOINT_SCHEMA, CHECKPOINT_VERSION
from app.narrative_core.services.mock_execution_quota import (
    MockExecutionBudgetGuard,
    MockExecutionQuotaService,
)
from app.narrative_core.services.mock_run_audit import MockRunAuditEventName, MockRunAuditSink
from app.narrative_core.services.mock_run_fault_injection import (
    FaultInjectionController,
    FaultInjectionKind,
    assert_fault_injection_allowed,
    build_profile,
)
from app.narrative_core.services.mock_run_idempotency import (
    IdempotencyNamespace,
    MockRunConcurrencyGuard,
    MockRunIdempotencyService,
    MockRunServiceError,
)
from app.narrative_core.services.mock_run_recovery_service import (
    CheckpointValidator,
    MockRunRecoveryService,
    MockRunStartupRecoveryAdapter,
)
from app.narrative_core.services.mock_whole_book_engine import MOCK_ENGINE_ID, MOCK_ENGINE_VERSION
from app.narrative_core.services.run_scope_service import StubSnapshotValidationGateway
from app.narrative_core.services.run_stage_service import RunStageService

REPO_ROOT = Path(__file__).resolve().parents[3]


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'recovery.db'}")
    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    return engine


def _session(engine) -> Session:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _make_book_snapshot(session: Session, *, status: str = SnapshotStatus.COMPLETED.value):
    book = Book(title="Mock Lab Book", source_file_name="m.txt", source_file_hash="a" * 64)
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=0,
        title="Ch1",
        chapter_title="Ch1",
        display_title="Ch1",
        source_title_line="第1章",
    )
    session.add(chapter)
    session.flush()
    snap = BookSnapshot(
        book_id=book.id,
        content_hash="b" * 64,
        chapter_count=1,
        paragraph_count=1,
        character_count=100,
        snapshot_status=status,
        source_fingerprint="c" * 64,
    )
    session.add(snap)
    session.commit()
    return book, chapter, snap


def _make_mock_run(
    session: Session,
    *,
    book: Book,
    snap: BookSnapshot,
    status: str = RunStatus.RUNNING.value,
    with_stages: bool = True,
    configuration_fingerprint: str = "cfg-fp-1",
    engine_version: str = MOCK_ENGINE_VERSION,
):
    service = RunStageService(
        session, snapshot_gateway=StubSnapshotValidationGateway(session)
    )
    run = service.create_scoped_run(
        scope_type=AnalysisScopeType.BOOK,
        analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
        book_id=book.id,
        book_snapshot_id=snap.id,
        configuration_fingerprint=configuration_fingerprint,
        provider="mock",
        model=f"mock:{MOCK_ENGINE_ID}@{engine_version}",
        prompt_version=engine_version,
        schema_version="1",
        input_hash="d" * 64,
        task_type="whole_book_mock",
        client_request_id=f"mock_lab:create:{book.id}:{configuration_fingerprint}",
    )
    run.status = status
    session.commit()
    stages = []
    if with_stages:
        keys = [
            WholeBookStageKey.BUILD_FULLTEXT_INDEX.value,
            WholeBookStageKey.RESOLVE_ENTITIES.value,
            WholeBookStageKey.ANALYZE_STRUCTURE.value,
        ]
        stages = list(service.initialize_run_stages(run.id, keys))
    return run, stages, service


def _write_valid_checkpoint(
    session: Session,
    *,
    run: AnalysisRun,
    stage: AnalysisRunStage,
    validator: CheckpointValidator | None = None,
):
    validator = validator or CheckpointValidator()
    payload = validator.build_checkpoint(
        run_id=run.id,
        run_stage_id=stage.id,
        stage_key=stage.stage_key,
        attempt=stage.attempt_count,
        configuration_fingerprint=run.configuration_fingerprint or "cfg-fp-1",
        snapshot_id=int(run.book_snapshot_id),
        completed_output_ref=f"artifact:{stage.stage_key}",
    )
    stage.checkpoint_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    session.commit()
    return payload


@pytest.fixture
def env(tmp_path):
    engine = _engine(tmp_path)
    session = _session(engine)
    book, chapter, snap = _make_book_snapshot(session)
    idem = MockRunIdempotencyService()
    guard = MockRunConcurrencyGuard()
    audit = MockRunAuditSink(emit_logs=False)
    yield {
        "engine": engine,
        "session": session,
        "book": book,
        "chapter": chapter,
        "snap": snap,
        "idem": idem,
        "guard": guard,
        "audit": audit,
    }
    session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_01_create_idempotency(env):
    idem: MockRunIdempotencyService = env["idem"]
    payload = {"book_id": 1, "snapshot_id": 2, "cfg": "x"}
    idem.register_create_request(
        idempotency_key="k1", actor="lab", request_scope="book:1", payload=payload, run_id=10
    )
    idem.mark_operation_completed(
        namespace=IdempotencyNamespace.CREATE,
        idempotency_key="k1",
        actor="lab",
        request_scope="book:1",
        result={"run_id": 10},
        run_id=10,
    )
    hit = idem.resolve_create_request(
        idempotency_key="k1", actor="lab", request_scope="book:1", payload=payload
    )
    assert hit.hit and hit.record is not None
    assert hit.record.result["run_id"] == 10
    # Second register returns same record — no second run.
    again = idem.register_create_request(
        idempotency_key="k1", actor="lab", request_scope="book:1", payload=payload, run_id=99
    )
    assert again.run_id == 10


def test_02_payload_conflict(env):
    idem: MockRunIdempotencyService = env["idem"]
    idem.register_create_request(
        idempotency_key="k1",
        actor="lab",
        request_scope="book:1",
        payload={"book_id": 1},
        run_id=1,
    )
    with pytest.raises(MockRunServiceError) as exc:
        idem.register_create_request(
            idempotency_key="k1",
            actor="lab",
            request_scope="book:1",
            payload={"book_id": 2},
        )
    assert exc.value.code == MockRunErrorCode.MOCK_RUN_IDEMPOTENCY_CONFLICT
    resolved = idem.resolve_create_request(
        idempotency_key="k1",
        actor="lab",
        request_scope="book:1",
        payload={"book_id": 2},
    )
    assert resolved.conflict
    assert resolved.error_code == MockRunErrorCode.MOCK_RUN_IDEMPOTENCY_CONFLICT


@pytest.mark.parametrize(
    "namespace",
    [
        IdempotencyNamespace.PAUSE,
        IdempotencyNamespace.RESUME,
        IdempotencyNamespace.CANCEL,
        IdempotencyNamespace.RETRY,
    ],
)
def test_03_to_07_operation_idempotency(env, namespace):
    idem: MockRunIdempotencyService = env["idem"]
    payload = {"run_id": 7, "action": namespace.value}
    idem.register_operation(
        namespace=namespace,
        idempotency_key="op-1",
        actor="user",
        request_scope="run:7",
        payload=payload,
        run_id=7,
    )
    idem.mark_operation_completed(
        namespace=namespace,
        idempotency_key="op-1",
        actor="user",
        request_scope="run:7",
        result={"applied": True, "status": namespace.value},
        run_id=7,
    )
    first = idem.resolve_operation(
        namespace=namespace,
        idempotency_key="op-1",
        actor="user",
        request_scope="run:7",
        payload=payload,
    )
    second = idem.resolve_operation(
        namespace=namespace,
        idempotency_key="op-1",
        actor="user",
        request_scope="run:7",
        payload=payload,
    )
    assert first.hit and second.hit
    assert first.record.result == second.record.result


def test_08_duplicate_stage_completion(env):
    idem: MockRunIdempotencyService = env["idem"]
    first = idem.remember_stage_completion(
        run_id=1, stage_key="resolve_entities", attempt=1, artifact_id=100
    )
    second = idem.remember_stage_completion(
        run_id=1, stage_key="resolve_entities", attempt=1, artifact_id=100
    )
    assert first.hit is False
    assert second.hit is True


def test_09_duplicate_artifact(env):
    idem: MockRunIdempotencyService = env["idem"]
    first = idem.remember_artifact_write(
        run_id=1, stage_key="resolve_entities", attempt=1, artifact_id=100
    )
    second = idem.remember_artifact_write(
        run_id=1, stage_key="resolve_entities", attempt=1, artifact_id=100
    )
    assert first.hit is False
    assert second.hit is True


def test_10_duplicate_asset_version(env):
    idem: MockRunIdempotencyService = env["idem"]
    first = idem.remember_asset_version_write(
        run_id=1, asset_key="entity:hero", attempt=1, asset_version_id=55
    )
    second = idem.remember_asset_version_write(
        run_id=1, asset_key="entity:hero", attempt=1, asset_version_id=55
    )
    assert first.hit is False
    assert second.hit is True


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_11_active_book_conflict(env):
    guard: MockRunConcurrencyGuard = env["guard"]
    guard.reserve_book_slot(book_id=1, run_id=10)
    with pytest.raises(MockRunServiceError) as exc:
        guard.reserve_book_slot(book_id=1, run_id=11)
    assert exc.value.code == MockRunErrorCode.MOCK_RUN_ALREADY_ACTIVE


def test_12_single_executor(env):
    guard: MockRunConcurrencyGuard = env["guard"]
    guard.acquire_executor(5, lease_id="a")
    with pytest.raises(MockRunServiceError) as exc:
        guard.acquire_executor(5, lease_id="b")
    assert exc.value.code == MockRunErrorCode.MOCK_RUN_STATE_CONFLICT
    assert guard.executor_held(5)


def test_13_reserve_release_idempotent(env):
    guard: MockRunConcurrencyGuard = env["guard"]
    r1 = guard.reserve_book_slot(book_id=2, run_id=20, reservation_id="r-20")
    r2 = guard.reserve_book_slot(book_id=2, run_id=20, reservation_id="r-20")
    assert r1.reservation_id == r2.reservation_id
    guard.release_book_slot(reservation_id="r-20")
    guard.release_book_slot(reservation_id="r-20")
    assert not guard.has_active_book_run(2)
    guard.release_executor(20)
    guard.release_executor(20)


def test_14_failed_does_not_occupy_slot(env):
    guard: MockRunConcurrencyGuard = env["guard"]
    guard.reserve_book_slot(book_id=3, run_id=30)
    guard.note_run_status(30, WholeBookRunViewStatus.FAILED)
    assert not guard.has_active_book_run(3)
    # New run can reserve.
    guard.reserve_book_slot(book_id=3, run_id=31)
    assert guard.has_active_book_run(3)


def test_concurrent_reserve_requests(env):
    guard = MockRunConcurrencyGuard()
    results: list[str] = []

    def _try(run_id: int) -> None:
        try:
            guard.reserve_book_slot(book_id=99, run_id=run_id)
            results.append(f"ok:{run_id}")
        except MockRunServiceError as exc:
            results.append(f"err:{exc.code.value}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_try, range(1, 9)))
    assert sum(1 for r in results if r.startswith("ok:")) == 1
    assert sum(1 for r in results if r.startswith("err:")) == 7


# ---------------------------------------------------------------------------
# Recovery / Checkpoint
# ---------------------------------------------------------------------------


def test_15_16_17_scan_mark_preserve_completed(env):
    session: Session = env["session"]
    book, snap = env["book"], env["snap"]
    run, stages, service = _make_mock_run(session, book=book, snap=snap)
    service.transition_stage(run.id, stages[0].stage_key, StageStatus.RUNNING)
    service.transition_stage(run.id, stages[0].stage_key, StageStatus.COMPLETED)
    art = AnalysisArtifact(
        run_id=run.id,
        artifact_type="whole_book_stage",
        subject_type="stage",
        subject_id=stages[0].stage_key,
        schema_version="1",
        prompt_version=MOCK_ENGINE_VERSION,
        payload_json=json.dumps({"mock": True}),
        confidence=1.0,
    )
    session.add(art)
    session.flush()
    stages[0].output_artifact_id = art.id
    service.transition_stage(run.id, stages[1].stage_key, StageStatus.RUNNING)
    _write_valid_checkpoint(session, run=run, stage=stages[1])
    session.refresh(run)

    recovery = MockRunRecoveryService(session, lab_enabled=True, audit_sink=env["audit"])
    scanned = recovery.scan_recoverable_runs()
    assert run.id in scanned
    decision = recovery.mark_process_interrupted(run.id)
    assert decision.marked_interrupted
    session.refresh(run)
    session.refresh(stages[0])
    session.refresh(stages[1])
    assert run.status == RunStatus.INTERRUPTED.value
    assert stages[0].status == StageStatus.COMPLETED.value
    assert stages[1].status == StageStatus.INTERRUPTED.value
    assert stages[1].checkpoint_json  # retained


def test_18_resume_plan(env):
    session: Session = env["session"]
    run, stages, service = _make_mock_run(session, book=env["book"], snap=env["snap"])
    service.transition_stage(run.id, stages[0].stage_key, StageStatus.RUNNING)
    service.transition_stage(run.id, stages[0].stage_key, StageStatus.COMPLETED)
    art = AnalysisArtifact(
        run_id=run.id,
        artifact_type="whole_book_stage",
        subject_type="stage",
        subject_id=stages[0].stage_key,
        schema_version="1",
        prompt_version=MOCK_ENGINE_VERSION,
        payload_json="{}",
        confidence=1.0,
    )
    session.add(art)
    session.flush()
    stages[0].output_artifact_id = art.id
    service.transition_stage(run.id, stages[1].stage_key, StageStatus.RUNNING)
    service.transition_stage(run.id, stages[1].stage_key, StageStatus.INTERRUPTED)
    _write_valid_checkpoint(session, run=run, stage=stages[1])
    run.status = RunStatus.INTERRUPTED.value
    session.commit()

    recovery = MockRunRecoveryService(session, lab_enabled=True, audit_sink=env["audit"])
    plan = recovery.build_resume_plan(run.id)
    assert plan.resume_from_stage_key == stages[1].stage_key
    assert stages[0].stage_key in plan.skip_completed_stages
    assert plan.requires_explicit_resume
    assert plan.auto_execute_forbidden


def test_19_lab_disabled_no_resume(env):
    session: Session = env["session"]
    run, stages, service = _make_mock_run(session, book=env["book"], snap=env["snap"])
    service.transition_stage(run.id, stages[0].stage_key, StageStatus.RUNNING)
    _write_valid_checkpoint(session, run=run, stage=stages[0])
    recovery = MockRunRecoveryService(
        session, lab_enabled=False, audit_sink=env["audit"], explicit_resume_allowed=True
    )
    marked = recovery.mark_process_interrupted(run.id)
    assert marked.marked_interrupted
    assert marked.recoverable is False
    decision = recovery.resume_recoverable_run(run.id)
    assert decision.reason_code == MockRunErrorCode.MOCK_LAB_DISABLED
    assert decision.resume_plan is None


def test_20_snapshot_missing(env):
    session: Session = env["session"]
    run, stages, _ = _make_mock_run(session, book=env["book"], snap=env["snap"])
    run.book_snapshot_id = 999999
    session.commit()
    recovery = MockRunRecoveryService(session, lab_enabled=True)
    with pytest.raises(MockRunServiceError) as exc:
        recovery.build_resume_plan(run.id)
    assert exc.value.code == MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID


def test_21_snapshot_non_completed(env):
    session: Session = env["session"]
    run, stages, _ = _make_mock_run(session, book=env["book"], snap=env["snap"])
    snap = session.get(BookSnapshot, run.book_snapshot_id)
    snap.snapshot_status = SnapshotStatus.BUILDING.value
    session.commit()
    recovery = MockRunRecoveryService(session, lab_enabled=True)
    with pytest.raises(MockRunServiceError) as exc:
        recovery.build_resume_plan(run.id)
    assert exc.value.code == MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID


def test_22_engine_mismatch(env):
    session: Session = env["session"]
    run, stages, service = _make_mock_run(session, book=env["book"], snap=env["snap"])
    service.transition_stage(run.id, stages[0].stage_key, StageStatus.RUNNING)
    service.transition_stage(run.id, stages[0].stage_key, StageStatus.INTERRUPTED)
    _write_valid_checkpoint(session, run=run, stage=stages[0])
    run.status = RunStatus.INTERRUPTED.value
    session.commit()
    recovery = MockRunRecoveryService(
        session,
        lab_enabled=True,
        current_engine_version="0.0.0-other",
    )
    with pytest.raises(MockRunServiceError) as exc:
        recovery.build_resume_plan(run.id)
    assert exc.value.code == MockRunErrorCode.MOCK_RUN_ENGINE_VERSION_MISMATCH


def test_23_configuration_mismatch(env):
    session: Session = env["session"]
    run, stages, service = _make_mock_run(session, book=env["book"], snap=env["snap"])
    service.transition_stage(run.id, stages[0].stage_key, StageStatus.RUNNING)
    service.transition_stage(run.id, stages[0].stage_key, StageStatus.INTERRUPTED)
    validator = CheckpointValidator()
    payload = validator.build_checkpoint(
        run_id=run.id,
        run_stage_id=stages[0].id,
        stage_key=stages[0].stage_key,
        attempt=0,
        configuration_fingerprint="other-cfg",
        snapshot_id=int(run.book_snapshot_id),
    )
    stages[0].checkpoint_json = json.dumps(payload)
    run.status = RunStatus.INTERRUPTED.value
    session.commit()
    recovery = MockRunRecoveryService(session, lab_enabled=True)
    with pytest.raises(MockRunServiceError) as exc:
        recovery.validate_checkpoint(run.id)
    assert exc.value.code == MockRunErrorCode.MOCK_RUN_CHECKPOINT_INVALID


def test_24_checkpoint_schema(env):
    validator = CheckpointValidator()
    result = validator.validate_payload(
        {"schema": "wrong", "version": "9.9.9"},
        run_id=1,
        stage_key="x",
    )
    assert not result.ok
    assert result.error_code == MockRunErrorCode.MOCK_RUN_CHECKPOINT_INVALID


def test_25_corrupted_checkpoint(env):
    validator = CheckpointValidator()
    result = validator.validate_payload("{not-json", run_id=1)
    assert not result.ok
    assert result.detail_code == "CHECKPOINT_CORRUPTED_JSON"
    # Must not treat as completed.
    assert result.ref is None or result.ref.compatible is False


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_26_27_audit_events_no_body(env):
    from dataclasses import asdict

    audit: MockRunAuditSink = env["audit"]
    audit.run_created(1, actor="lab", idempotency_key="k")
    audit.run_started(1, actor="executor")
    audit.stage_started(1, stage_key="resolve_entities", attempt=1)
    audit.stage_completed(1, stage_key="resolve_entities", attempt=1)
    audit.stage_failed(1, stage_key="analyze_structure", attempt=1, detail_code="FAIL")
    audit.pause_requested(1, actor="user", idempotency_key="p")
    audit.paused(1, actor="executor")
    audit.resumed(1, actor="user", previous_state="paused")
    audit.retry_requested(1, stage_key="analyze_structure", actor="user")
    audit.cancel_requested(1, actor="user")
    audit.cancelled(1, actor="executor", previous_state="running")
    audit.interrupted(1, actor="startup")
    audit.recovery_planned(1, actor="recovery")
    audit.recovery_rejected(1, actor="recovery", detail_code="X")
    audit.run_completed(1, actor="executor")
    events = audit.list_events(1)
    names = {e.event_type for e in events}
    required = {e.value for e in MockRunAuditEventName if e != MockRunAuditEventName.BUDGET_DENIED}
    assert required.issubset(names)
    blob = json.dumps([asdict(e) for e in events])
    for token in ("full_text", "novel_body", "api_key", "system_prompt", "evidence_full_text"):
        assert token not in blob
    with pytest.raises(ValueError):
        audit.emit(
            run_id=1,
            event_type="bad",
            actor="x",
            extra={"full_text": "secret novel"},
        )


# ---------------------------------------------------------------------------
# Quota / Budget
# ---------------------------------------------------------------------------


def test_28_to_32_quota_limits(env):
    guard = MockRunConcurrencyGuard()
    policy = MockExecutionQuotaPolicy(
        max_concurrent_mock_runs=1,
        max_mock_chapters=2,
        max_mock_characters=100,
        max_synthetic_tokens=50,
        max_synthetic_cost=1.0,
        max_run_duration_seconds=10,
    )
    quota = MockExecutionQuotaService(policy=policy, concurrency_guard=guard)
    assert quota.reserve(chapters=2, characters=50, synthetic_tokens=10, synthetic_cost=0.1).allowed
    assert not quota.reserve(chapters=1).allowed  # chapters
    quota.clear()
    assert not quota.reserve(characters=101).allowed
    quota.clear()
    assert not quota.reserve(synthetic_tokens=51).allowed
    quota.clear()
    assert not quota.reserve(synthetic_cost=1.5).allowed
    quota.clear()
    assert not quota.reserve(duration_seconds=11).allowed


def test_33_budget_denied_no_asset_write(env):
    guard = MockRunConcurrencyGuard()
    guard.reserve_book_slot(book_id=1, run_id=1)
    quota = MockExecutionQuotaService(concurrency_guard=guard)
    budget = MockExecutionBudgetGuard(
        quota, deny_at_stage="persist_narrative_assets", concurrency_guard=guard
    )
    ok, decision = budget.try_write_asset(
        stage_key="persist_narrative_assets",
        run_id=1,
        book_id=1,
        asset_key="asset:1",
    )
    assert not ok
    assert decision.reason_code == MockRunErrorCode.MOCK_RUN_BUDGET_EXCEEDED.value
    assert decision.write_assets_on_deny is False
    assert budget.written_assets == ()
    assert not guard.has_active_book_run(1)


# ---------------------------------------------------------------------------
# Fault injection / restart
# ---------------------------------------------------------------------------


def test_34_35_fault_fail_interrupt():
    ctrl = FaultInjectionController(
        profile=build_profile(FaultInjectionKind.FAIL_AT_STAGE), environment="test"
    )
    assert ctrl.apply_stage_outcome(ctrl.profile.stage_key) == "failed"
    ctrl.set_profile(build_profile(FaultInjectionKind.INTERRUPT_AT_STAGE))
    assert ctrl.apply_stage_outcome(ctrl.profile.stage_key) == "interrupted"
    assert ctrl.profile.fingerprint()  # deterministic


def test_36_task_registry_loss():
    ctrl = FaultInjectionController(
        profile=build_profile(FaultInjectionKind.TASK_REGISTRY_LOSS), environment="test"
    )
    ctrl.register_task(1)
    assert ctrl.task_registry
    ctrl.simulate_task_registry_loss()
    assert ctrl.task_registry == {}


def test_37_38_restart_reconciliation_no_silent_resume(env, tmp_path):
    engine = env["engine"]
    session: Session = env["session"]
    run, stages, service = _make_mock_run(session, book=env["book"], snap=env["snap"])
    service.transition_stage(run.id, stages[0].stage_key, StageStatus.RUNNING)
    _write_valid_checkpoint(session, run=run, stage=stages[0])
    session.commit()

    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    adapter = MockRunStartupRecoveryAdapter(SessionLocal, lab_enabled=True, audit_sink=env["audit"])
    marked = adapter.reconcile()
    assert run.id in marked
    assert adapter.auto_resume_invoked is False
    assert adapter.budget_consumed is False
    assert adapter.task_started is False

    # Explicit resume only after gate.
    session2 = SessionLocal()
    recovery = MockRunRecoveryService(
        session2, lab_enabled=True, audit_sink=env["audit"], explicit_resume_allowed=False
    )
    denied = recovery.resume_recoverable_run(run.id)
    assert denied.reason_code == MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED
    recovery.allow_explicit_resume(True)
    # Need interrupted state + valid outputs path
    session2.refresh(session2.get(AnalysisRun, run.id))
    ok = recovery.resume_recoverable_run(run.id)
    assert ok.recoverable is True
    assert ok.resume_plan is not None
    session2.close()

    ctrl = FaultInjectionController(
        profile=build_profile(
            FaultInjectionKind.PROCESS_RESTART_MARKER, process_restart_marker="r1"
        ),
        environment="test",
    )
    assert ctrl.mark_process_restart() == "r1"
    with pytest.raises(RuntimeError):
        assert_fault_injection_allowed(environment="production")


# ---------------------------------------------------------------------------
# Version / change registry / whitespace
# ---------------------------------------------------------------------------


def test_39_version_manager_check():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "version_manager.py"), "check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_40_change_registry_check():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "change_registry.py"), "check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_41_git_diff_check():
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_phase1a_no_stage_compat(env):
    session: Session = env["session"]
    run, _, _ = _make_mock_run(
        session, book=env["book"], snap=env["snap"], with_stages=False, status=RunStatus.RUNNING.value
    )
    recovery = MockRunRecoveryService(session, lab_enabled=True, audit_sink=env["audit"])
    decision = recovery.mark_process_interrupted(run.id)
    assert decision.marked_interrupted
    session.refresh(run)
    assert run.status == RunStatus.INTERRUPTED.value
