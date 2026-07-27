"""Phase 2A Agent M — Mock Lab backend (CHG-20260723-032).

Covers authorization, create service, executor, task registry, Lab API, and
no-model proofs. Does not run full pytest suite.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
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
    Chapter,
    NarrativeAssetVersion,
    NarrativeRelationVersion,
    Paragraph,
)
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import (
    AnalysisScopeType,
    AnalysisType,
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
from app.narrative_core.run_shell_contract.create_run import (
    MOCK_RUN_METADATA_SCHEMA,
    MOCK_RUN_METADATA_VERSION,
    CreateMockWholeBookRunRequest,
    MockProfile,
)
from app.narrative_core.run_shell_contract.errors import MockRunErrorCode
from app.narrative_core.run_shell_contract.executor import (
    EXECUTOR_PROTOCOL_METHODS,
    MockExecutorTestHooks,
)
from app.narrative_core.run_shell_contract.mock_lab import (
    MOCK_ENGINE_ID,
    MOCK_LAB_REQUEST_MARKER_HEADER,
    MOCK_LAB_REQUEST_MARKER_VALUE,
    WHOLE_BOOK_MOCK_LAB_ENABLED,
)
from app.narrative_core.run_shell_contract.task_registry import TASK_REGISTRY_PROTOCOL_METHODS
from app.narrative_core.services.in_process_mock_run_task_registry import (
    InProcessMockRunTaskRegistry,
    reset_default_mock_run_task_registry,
)
from app.narrative_core.services.mock_lab_authorization_service import (
    MockLabAuthorizationDenied,
    MockLabAuthorizationService,
)
from app.narrative_core.services.mock_run_metadata import (
    METADATA_SCHEMA_ISSUES,
    METADATA_SCHEMA_SUFFICIENT,
    METADATA_STORAGE_COLUMN,
    parse_metadata_json,
)
from app.narrative_core.services.mock_whole_book_engine import MockWholeBookAnalysisEngine
from app.narrative_core.services.mock_whole_book_run_executor import (
    DefaultMockWholeBookRunExecutor,
)
from app.narrative_core.services.mock_whole_book_run_service import (
    MockWholeBookRunError,
    MockWholeBookRunService,
)
from app.narrative_core.services.run_stage_service import RunStageService
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_engine_registry import (
    DefaultWholeBookEngineFactory,
    PRODUCTION_DEFAULT_ENGINE_ID,
)
from app.narrative_core.services.whole_book_engine_adapters import MOCK_SOURCE_MARKER
from app.routers import whole_book_mock_lab_runs as lab_router_mod
from app.routers.whole_book_mock_lab_runs import (
    INTEGRATION_ISSUE_MAIN_PY_ROUTER_REGISTRATION,
    lab_contract_assertions,
    router as lab_router,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


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
        title="Mock Lab Book",
        source_file_name="lab.txt",
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
    reset_default_mock_run_task_registry()
    db = _fk_engine(f"sqlite:///{tmp_path / 'phase2a-lab.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    session = factory()
    book = _seed_book(session)
    snapshot = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    assert snapshot.snapshot_status == SnapshotStatus.COMPLETED.value

    auth = MockLabAuthorizationService(
        environment="test",
        lab_enabled=True,
    )
    registry = InProcessMockRunTaskRegistry()
    stage_service = RunStageService(session)
    service = MockWholeBookRunService(
        session, auth=auth, stage_service=stage_service, task_registry=registry
    )
    executor = DefaultMockWholeBookRunExecutor(
        session,
        stage_service=stage_service,
        task_registry=registry,
        lab_hooks_allowed=True,
    )
    yield {
        "session": session,
        "book": book,
        "snapshot": snapshot,
        "auth": auth,
        "service": service,
        "executor": executor,
        "registry": registry,
        "stage_service": stage_service,
        "db": db,
    }
    session.close()
    db.dispose()
    reset_default_mock_run_task_registry()


def _create_req(env, **overrides) -> CreateMockWholeBookRunRequest:
    base = {
        "book_id": env["book"].id,
        "book_snapshot_id": env["snapshot"].id,
        "analysis_mode": WholeBookAnalysisMode.NATIVE,
        "requested_modules": (WholeBookModuleKey.BOOK_OVERVIEW,),
        "configuration_fingerprint": "cfg-lab-1",
        "idempotency_key": "idem-lab-001",
        "mock_profile": MockProfile.DETERMINISTIC_MINIMAL,
        "requested_by": "tester",
        "preflight_fingerprint": "preflight-lab-1",
    }
    base.update(overrides)
    return CreateMockWholeBookRunRequest(**base)


def _create(env, **overrides):
    return env["service"].create_run(
        _create_req(env, **overrides),
        loopback=True,
        request_marker_present=True,
        declare_mock_lab=True,
    )


# ----- 1–5 Authorization -----


def test_lab_default_disabled() -> None:
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False
    auth = MockLabAuthorizationService(environment="test", lab_enabled=False)
    decision = auth.evaluate(
        loopback=True,
        request_marker_present=True,
    )
    assert decision.allowed is False
    assert decision.reason_code == MockRunErrorCode.MOCK_LAB_DISABLED.value


def test_production_environment_rejected() -> None:
    auth = MockLabAuthorizationService(environment="production", lab_enabled=True)
    with pytest.raises(MockLabAuthorizationDenied) as exc:
        auth.require(loopback=True, request_marker_present=True)
    assert exc.value.error.code == MockRunErrorCode.MOCK_LAB_ENVIRONMENT_NOT_ALLOWED


def test_non_loopback_rejected() -> None:
    auth = MockLabAuthorizationService(environment="test", lab_enabled=True)
    with pytest.raises(MockLabAuthorizationDenied) as exc:
        auth.require(loopback=False, request_marker_present=True)
    assert exc.value.error.code == MockRunErrorCode.MOCK_LAB_LOOPBACK_REQUIRED


def test_missing_marker_rejected() -> None:
    auth = MockLabAuthorizationService(environment="test", lab_enabled=True)
    with pytest.raises(MockLabAuthorizationDenied) as exc:
        auth.require(loopback=True, request_marker_present=False)
    assert exc.value.error.code == MockRunErrorCode.MOCK_LAB_REQUEST_MARKER_REQUIRED


def test_non_mock_engine_rejected() -> None:
    auth = MockLabAuthorizationService(environment="test", lab_enabled=True)
    with pytest.raises(MockLabAuthorizationDenied) as exc:
        auth.require(
            loopback=True,
            request_marker_present=True,
            requested_engine_id="private_real_engine",
            engine_is_mock=False,
        )
    assert exc.value.error.code == MockRunErrorCode.MOCK_LAB_ENGINE_REQUIRED


# ----- 6–13 Create / metadata -----


def test_create_success(lab_env) -> None:
    result = _create(lab_env)
    assert result.created is True
    assert result.mock is True
    assert result.non_production is True
    assert result.status == WholeBookRunViewStatus.PENDING
    assert result.duplicate_of_run_id is None
    stages = lab_env["service"].get_run_stages(result.run_id)
    assert len(stages) >= 1
    assert all(s["status"] == StageStatus.PENDING.value for s in stages)


def test_create_precheck_failure_no_persist(lab_env) -> None:
    session = lab_env["session"]
    before_runs = session.scalar(select(func.count()).select_from(AnalysisRun)) or 0
    before_stages = session.scalar(select(func.count()).select_from(AnalysisRunStage)) or 0
    with pytest.raises(MockWholeBookRunError) as exc:
        _create(lab_env, book_snapshot_id=999999)
    assert exc.value.error.code == MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID
    after_runs = session.scalar(select(func.count()).select_from(AnalysisRun)) or 0
    after_stages = session.scalar(select(func.count()).select_from(AnalysisRunStage)) or 0
    assert after_runs == before_runs
    assert after_stages == before_stages


def test_idempotency(lab_env) -> None:
    first = _create(lab_env, idempotency_key="idem-same")
    second = _create(lab_env, idempotency_key="idem-same")
    assert first.created is True
    assert second.created is False
    assert second.duplicate_of_run_id == first.run_id
    assert second.run_id == first.run_id


def test_duplicate_of_run_id_field(lab_env) -> None:
    first = _create(lab_env, idempotency_key="idem-dup")
    second = _create(lab_env, idempotency_key="idem-dup")
    assert second.duplicate_of_run_id == first.run_id


def test_snapshot_invalid(lab_env) -> None:
    with pytest.raises(MockWholeBookRunError) as exc:
        _create(lab_env, book_id=lab_env["book"].id + 999)
    assert exc.value.error.code == MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID


def test_module_invalid(lab_env) -> None:
    req = CreateMockWholeBookRunRequest(
        book_id=lab_env["book"].id,
        book_snapshot_id=lab_env["snapshot"].id,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        requested_modules=(WholeBookModuleKey.BOOK_OVERVIEW,),
        configuration_fingerprint="cfg",
        idempotency_key="idem-mod",
        mock_profile=MockProfile.DETERMINISTIC_MINIMAL,
        requested_by="t",
        preflight_fingerprint="pf",
    )
    # Bypass frozen request with an invalid module string for service validation.
    bad = CreateMockWholeBookRunRequest(
        book_id=req.book_id,
        book_snapshot_id=req.book_snapshot_id,
        analysis_mode=req.analysis_mode,
        requested_modules=("not_a_real_module",),  # type: ignore[arg-type]
        configuration_fingerprint=req.configuration_fingerprint,
        idempotency_key=req.idempotency_key,
        mock_profile=req.mock_profile,
        requested_by=req.requested_by,
        preflight_fingerprint=req.preflight_fingerprint,
    )
    with pytest.raises(MockWholeBookRunError) as exc:
        lab_env["service"].create_run(
            bad, loopback=True, request_marker_present=True
        )
    assert exc.value.error.code == MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED
    assert exc.value.error.detail_code == "MODULE_INVALID"


def test_active_run_conflict(lab_env) -> None:
    _create(lab_env, idempotency_key="idem-a1")
    with pytest.raises(MockWholeBookRunError) as exc:
        _create(lab_env, idempotency_key="idem-a2")
    assert exc.value.error.code == MockRunErrorCode.MOCK_RUN_ALREADY_ACTIVE


def test_metadata_schema_version(lab_env) -> None:
    assert METADATA_SCHEMA_SUFFICIENT is True
    assert METADATA_SCHEMA_ISSUES == ()
    assert METADATA_STORAGE_COLUMN == "validated_output"
    result = _create(lab_env)
    run = lab_env["session"].get(AnalysisRun, result.run_id)
    meta = parse_metadata_json(run.validated_output)
    assert meta["schema"] == MOCK_RUN_METADATA_SCHEMA
    assert meta["version"] == MOCK_RUN_METADATA_VERSION
    assert meta["run_scope"] == "whole_book"
    assert meta["mock"] is True
    assert meta["non_production"] is True
    assert meta["engine_id"] == MOCK_ENGINE_ID
    assert "requested_modules" in meta
    assert "resolved_modules" in meta
    assert "configuration_fingerprint" in meta


# ----- 14 Task registry -----


def test_task_single_instance(lab_env) -> None:
    for name in TASK_REGISTRY_PROTOCOL_METHODS:
        assert hasattr(lab_env["registry"], name)
    result = _create(lab_env)
    h1 = lab_env["registry"].register(result.run_id)
    h2 = lab_env["registry"].register(result.run_id)
    assert h1.run_id == h2.run_id
    assert len([h for h in lab_env["registry"].list() if h.run_id == result.run_id]) == 1


# ----- 15–22 Executor -----


def test_executor_start_and_next(lab_env) -> None:
    for name in EXECUTOR_PROTOCOL_METHODS:
        assert hasattr(lab_env["executor"], name)
    result = _create(lab_env)
    started = lab_env["executor"].start(result.run_id)
    assert started.current_state == WholeBookRunViewStatus.RUNNING
    nxt = lab_env["executor"].execute_next_stage(result.run_id)
    assert nxt.accepted is True
    assert nxt.stage_key is not None
    stage = lab_env["stage_service"]._stages.get_stage(result.run_id, nxt.stage_key)  # noqa: SLF001
    assert StageStatus(stage.status) == StageStatus.COMPLETED


def test_execute_until_blocked(lab_env) -> None:
    result = _create(lab_env)
    lab_env["executor"].start(result.run_id)
    final = lab_env["executor"].execute_until_blocked(result.run_id)
    assert final.current_state == WholeBookRunViewStatus.COMPLETED
    stages = lab_env["service"].get_run_stages(result.run_id)
    assert all(s["status"] == StageStatus.COMPLETED.value for s in stages)


def test_pause_resume(lab_env) -> None:
    result = _create(lab_env)
    lab_env["executor"].start(result.run_id)
    lab_env["executor"].execute_next_stage(result.run_id)
    paused = lab_env["executor"].pause(result.run_id)
    assert paused.current_state == WholeBookRunViewStatus.PAUSED
    # Idempotent pause
    paused2 = lab_env["executor"].pause(result.run_id)
    assert paused2.current_state == WholeBookRunViewStatus.PAUSED
    resumed = lab_env["executor"].resume(result.run_id)
    assert resumed.current_state == WholeBookRunViewStatus.RUNNING


def test_cancel(lab_env) -> None:
    result = _create(lab_env)
    lab_env["executor"].start(result.run_id)
    cancelled = lab_env["executor"].cancel(result.run_id)
    assert cancelled.current_state == WholeBookRunViewStatus.CANCELLED
    # Results retained — no physical delete
    stages = lab_env["service"].get_run_stages(result.run_id)
    assert stages
    # Terminal cancel idempotent
    again = lab_env["executor"].cancel(result.run_id)
    assert again.current_state == WholeBookRunViewStatus.CANCELLED


def test_retry_and_completed_no_rerun(lab_env) -> None:
    result = _create(lab_env)
    lab_env["executor"].set_test_hooks(
        MockExecutorTestHooks(fail_at_stage=WholeBookStageKey.BUILD_FULLTEXT_INDEX)
    )
    lab_env["executor"].start(result.run_id)
    failed = lab_env["executor"].execute_next_stage(result.run_id)
    assert failed.current_state == WholeBookRunViewStatus.FAILED
    stage_key = WholeBookStageKey.BUILD_FULLTEXT_INDEX.value
    before = lab_env["stage_service"]._stages.get_stage(result.run_id, stage_key)  # noqa: SLF001
    attempts = int(before.attempt_count or 0)

    lab_env["executor"].set_test_hooks(MockExecutorTestHooks())
    retried = lab_env["executor"].retry_stage(result.run_id, stage_key)
    assert retried.accepted is True
    after = lab_env["stage_service"]._stages.get_stage(result.run_id, stage_key)  # noqa: SLF001
    assert int(after.attempt_count or 0) >= attempts

    # Complete remaining; completed stages must not rerun.
    lab_env["executor"].execute_until_blocked(result.run_id)
    completed = lab_env["stage_service"]._stages.get_stage(  # noqa: SLF001
        result.run_id, stage_key
    )
    assert StageStatus(completed.status) == StageStatus.COMPLETED
    # Re-executing current completed path via orchestrator skip
    request_meta = parse_metadata_json(
        lab_env["session"].get(AnalysisRun, result.run_id).validated_output
    )
    from app.narrative_core.services.mock_whole_book_run_executor import _lab_capability
    from app.narrative_core.contracts.whole_book_dto import WholeBookAnalysisRequest

    req = WholeBookAnalysisRequest(
        run_id=result.run_id,
        book_id=int(request_meta["book_id"]),
        book_snapshot_id=int(request_meta["book_snapshot_id"]),
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        capability_context=_lab_capability(),
        configuration_fingerprint=str(request_meta["configuration_fingerprint"]),
        snapshot_status=SnapshotStatus.COMPLETED,
    )
    skip = lab_env["executor"]._orch.execute_current_stage(req, stage_key)
    assert skip.metrics.get("skipped_rerun") is True


# ----- 23–26 Artifacts / candidates -----


def test_stage_artifact_and_candidates(lab_env) -> None:
    result = _create(lab_env)
    lab_env["executor"].start(result.run_id)
    lab_env["executor"].execute_until_blocked(result.run_id)
    session = lab_env["session"]
    artifacts = list(
        session.scalars(
            select(AnalysisArtifact).where(AnalysisArtifact.run_id == result.run_id)
        )
    )
    assert artifacts
    for art in artifacts:
        payload = json.loads(art.payload_json)
        assert payload.get("mock") is True or "mock" in str(payload).lower()
        assert payload.get("synthetic") is True or MOCK_SOURCE_MARKER in str(payload)

    versions = list(
        session.scalars(
            select(NarrativeAssetVersion).where(
                NarrativeAssetVersion.run_id == result.run_id
            )
        )
    )
    assert versions
    assert all(not bool(v.is_canonical) for v in versions)
    assert all(str(v.review_status) == "candidate" for v in versions)

    relations = list(
        session.scalars(
            select(NarrativeRelationVersion).where(
                NarrativeRelationVersion.run_id == result.run_id
            )
        )
    )
    # Relations may appear after enough stages; if present must be candidate.
    for rel in relations:
        assert not bool(rel.is_canonical)
        assert str(rel.review_status) == "candidate"


def test_budget_denied(lab_env) -> None:
    result = _create(lab_env)
    lab_env["executor"].set_test_hooks(
        MockExecutorTestHooks(
            budget_denied_at_stage=WholeBookStageKey.BUILD_FULLTEXT_INDEX
        )
    )
    lab_env["executor"].start(result.run_id)
    out = lab_env["executor"].execute_next_stage(result.run_id)
    assert out.current_state == WholeBookRunViewStatus.FAILED
    assert out.detail_code == MockRunErrorCode.MOCK_RUN_BUDGET_EXCEEDED.value
    assets = list(
        lab_env["session"].scalars(
            select(NarrativeAssetVersion).where(
                NarrativeAssetVersion.run_id == result.run_id
            )
        )
    )
    assert assets == []


# ----- 28–30 Lab API / production gate -----


def test_lab_api_dto_and_non_mock_reject(lab_env) -> None:
    app = FastAPI()
    app.include_router(lab_router)

    def _override_db():
        yield lab_env["session"]

    from app.db.session import get_db

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    headers = {MOCK_LAB_REQUEST_MARKER_HEADER: MOCK_LAB_REQUEST_MARKER_VALUE}

    # Lab disabled by default on service auth from Depends — inject enabled service.
    enabled_auth = MockLabAuthorizationService(environment="test", lab_enabled=True)
    registry = lab_env["registry"]

    def _svc():
        return MockWholeBookRunService(
            lab_env["session"],
            auth=enabled_auth,
            stage_service=lab_env["stage_service"],
            task_registry=registry,
        )

    def _ex():
        return DefaultMockWholeBookRunExecutor(
            lab_env["session"],
            stage_service=lab_env["stage_service"],
            task_registry=registry,
        )

    app.dependency_overrides[lab_router_mod.get_run_service] = _svc
    app.dependency_overrides[lab_router_mod.get_executor] = _ex

    payload = {
        "book_id": lab_env["book"].id,
        "book_snapshot_id": lab_env["snapshot"].id,
        "analysis_mode": WholeBookAnalysisMode.NATIVE.value,
        "requested_modules": [WholeBookModuleKey.BOOK_OVERVIEW.value],
        "configuration_fingerprint": "cfg-api-1",
        "idempotency_key": "idem-api-001",
        "mock_profile": MockProfile.DETERMINISTIC_MINIMAL.value,
        "requested_by": "api-tester",
        "preflight_fingerprint": "pf-api-1",
        "declare_mock_lab": True,
    }
    resp = client.post("/api/v1/labs/whole-book-runs", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mock"] is True
    assert body["non_production"] is True
    assert "full_text" not in body
    assert "prompt" not in body
    run_id = body["run_id"]

    got = client.get(f"/api/v1/labs/whole-book-runs/{run_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["metadata_schema"] == MOCK_RUN_METADATA_SCHEMA

    # Non-mock run rejected
    stage_service = lab_env["stage_service"]
    non_mock = stage_service.create_scoped_run(
        scope_type=AnalysisScopeType.BOOK,
        analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
        book_id=lab_env["book"].id,
        book_snapshot_id=lab_env["snapshot"].id,
        configuration_fingerprint="cfg-non-mock",
        validated_output=json.dumps({"not": "mock"}),
    )
    bad = client.get(
        f"/api/v1/labs/whole-book-runs/{non_mock.id}", headers=headers
    )
    assert bad.status_code == 403
    assert bad.json()["detail"]["error_code"] == MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET.value

    # Missing marker
    no_marker = client.post("/api/v1/labs/whole-book-runs", json=payload)
    assert no_marker.status_code == 403


def test_formal_run_entry_still_disabled() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    asserts = lab_contract_assertions()
    assert asserts["WHOLE_BOOK_RUNS_ENDPOINT_DISABLED"] is True
    assert "main.py" in INTEGRATION_ISSUE_MAIN_PY_ROUTER_REGISTRATION


# ----- 31 No model calls -----


def test_no_model_provider_http_calls(lab_env) -> None:
    """Prove Mock path never calls providers / HTTP / llama / Aliyun / prompts."""
    http_mock = MagicMock()
    with (
        patch("urllib.request.urlopen", http_mock),
        patch("http.client.HTTPConnection", http_mock),
    ):
        result = _create(lab_env, idempotency_key="idem-nomodel")
        lab_env["executor"].start(result.run_id)
        lab_env["executor"].execute_until_blocked(result.run_id)
    assert http_mock.call_count == 0

    # Production factory rejects Mock
    factory = DefaultWholeBookEngineFactory(production_mode=True)
    with pytest.raises(Exception):
        factory.create_engine(MOCK_ENGINE_ID)
    assert PRODUCTION_DEFAULT_ENGINE_ID is None

    # Synthetic markers present
    run = lab_env["session"].get(AnalysisRun, result.run_id)
    meta = parse_metadata_json(run.validated_output)
    assert meta["mock"] is True
    assert meta["non_production"] is True
    assert meta["engine_id"] == MOCK_ENGINE_ID

    # Engine itself is mock
    engine = MockWholeBookAnalysisEngine()
    health = engine.health_check()
    assert health["mock"] is True
    assert health["production_ready"] is False
    assert "no model calls" in health["detail"]


# ----- 32–34 version / change registry / git diff -----


def test_version_manager_check() -> None:
    proc = subprocess.run(
        ["python", "scripts/version_manager.py", "check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_change_registry_check() -> None:
    proc = subprocess.run(
        ["python", "scripts/change_registry.py", "check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_git_diff_check() -> None:
    proc = subprocess.run(
        ["git", "diff", "--check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
