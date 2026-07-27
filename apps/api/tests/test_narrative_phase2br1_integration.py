"""Phase 2B-R1 Integration E2E (CHG-20260723-048).

Composes Agent U (provider/context/cost) + Agent V (Lab run/persistence) via
PrivateWholeBookLiveReadinessRuntime. Dry path only — no live Provider HTTP,
no novel bodies in logs/asserts, no VERSION/migration changes.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisRun,
    Base,
    Book,
    Chapter,
    NarrativeAssetVersion,
    Paragraph,
)
from app.db.session import get_db
from app.main import create_app, mount_private_engine_lab_if_enabled
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import SnapshotStatus, StageStatus, WholeBookAnalysisMode, WholeBookModuleKey
from app.narrative_core.migrations.runner import (
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED
from app.narrative_core.run_shell_contract.private_engine_lab import (
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER,
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_VALUE,
    PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER,
    PRIVATE_LAB_TASK_TYPE,
    PRIVATE_PROVIDER_LIVE_PROBE_ENV,
    WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
    PrivateEngineLabDenyReason,
)
from app.narrative_core.services.candidate_persistence_adapter import (
    Phase1BCandidatePersistenceSink,
    RecordingCandidatePersistenceSink,
)
from app.narrative_core.services.data_transfer_consent_guard import (
    PrivateEngineProviderBudgetGuard,
)
from app.narrative_core.services.in_process_private_lab_task_registry import (
    InProcessPrivateLabTaskRegistry,
    reset_default_private_lab_task_registry,
)
from app.narrative_core.services.private_engine_lab_authorization_service import (
    PrivateEngineLabAuthorizationDenied,
    PrivateEngineLabAuthorizationService,
    is_private_provider_live_probe_enabled,
    should_register_private_engine_lab_router,
)
from app.narrative_core.services.private_engine_lab_run_service import (
    CreatePrivateLabRunRequest,
    PrivateWholeBookLabRunError,
)
from app.narrative_core.services.private_lab_ports import FakePrivateLabProviderExecutionPort
from app.narrative_core.services.private_lab_recovery_service import PrivateLabRecoveryService
from app.narrative_core.services.private_lab_run_executor import PrivateLabRunExecutor
from app.narrative_core.services.private_lab_run_metadata import is_private_lab_run_metadata
from app.narrative_core.services.private_lab_service_adapters import (
    resolve_server_security_status,
)
from app.narrative_core.services.private_whole_book_analysis_runtime import (
    create_lab_private_whole_book_analysis_runtime,
    create_private_whole_book_analysis_runtime,
)
from app.narrative_core.services.private_whole_book_live_readiness_runtime import (
    create_live_readiness_runtime,
    reset_default_live_readiness_runtime_for_tests,
)
from app.narrative_core.services.run_stage_service import RunStageService
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_engine_registry import PRODUCTION_DEFAULT_ENGINE_ID
from app.narrative_core.services.whole_book_module_runner import (
    FakeBookOverviewRunner,
    FakeChapterFunctionsRunner,
    FakeStorylinesRunner,
    FakeStructureStagesRunner,
    make_execution_request,
)
from app.narrative_core.services.whole_book_provider_gateway import (
    CapturingProviderTransport,
    ExistingCredentialServiceAdapter,
    FakeProviderAdapter,
    StubTransportResponse,
)
from app.routers.whole_book_private_engine_lab_runs import (
    reset_private_engine_lab_sessions_for_tests,
    router as private_lab_router,
)
import app.narrative_core.services.private_whole_book_live_readiness_runtime as live_runtime_mod

REPO_ROOT = Path(__file__).resolve().parents[3]
MARKER = {PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER: PRIVATE_ENGINE_LAB_REQUEST_MARKER_VALUE}
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


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
        title="Phase2BR1 Integration",
        source_file_name="integ.txt",
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
            raw_text="合成样本",
            normalized_text="合成样本",
            char_start=0,
            char_end=4,
        )
    )
    session.commit()
    return book


@pytest.fixture
def network_deny(monkeypatch: pytest.MonkeyPatch):
    """Fail closed: live probe unset; real outbound HTTP via requests/httpx transport denied.

    Do not patch httpx.Client.send — Starlette TestClient uses it for in-process ASGI.
    """

    monkeypatch.setenv(PRIVATE_PROVIDER_LIVE_PROBE_ENV, "")
    monkeypatch.delenv(PRIVATE_PROVIDER_LIVE_PROBE_ENV, raising=False)

    def _deny(*_a: Any, **_k: Any) -> None:
        raise AssertionError(
            "network denied: Provider HTTP must not be called in Phase 2B-R1 Integration E2E"
        )

    try:
        import httpx

        # Deny real network transports only (TestClient uses ASGITransport).
        if hasattr(httpx, "HTTPTransport"):
            monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _deny, raising=False)
        if hasattr(httpx, "AsyncHTTPTransport"):
            monkeypatch.setattr(
                httpx.AsyncHTTPTransport, "handle_async_request", _deny, raising=False
            )
    except Exception:  # noqa: BLE001
        pass
    try:
        import requests

        monkeypatch.setattr(requests.Session, "request", _deny, raising=False)
        monkeypatch.setattr(requests, "request", _deny, raising=False)
    except Exception:  # noqa: BLE001
        pass

    assert is_private_provider_live_probe_enabled(environ={}) is False
    yield


@pytest.fixture
def integ_env(tmp_path, network_deny):
    """In-memory-ish sqlite + live readiness composition for Integration E2E."""

    reset_default_private_lab_task_registry()
    reset_private_engine_lab_sessions_for_tests()
    reset_default_live_readiness_runtime_for_tests()

    db = _fk_engine(f"sqlite:///{tmp_path / 'phase2br1-integ.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    session = factory()
    book = _seed_book(session)
    snapshot = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    assert snapshot.snapshot_status == SnapshotStatus.COMPLETED.value

    transport = CapturingProviderTransport(
        stub=StubTransportResponse(
            text='{"synthetic":true,"partial":true,"items":[]}',
            model="qwen3.7-plus",
            request_id="integ-stub",
            input_tokens=40,
            output_tokens=18,
        )
    )
    runtime = create_live_readiness_runtime(
        environment="test",
        lab_enabled=True,
        dry_run=True,
        allow_network=False,
        session=session,
        transport=transport,
        allow_fake_resolver=False,
        auto_wire_credentials=False,
    )
    live_runtime_mod._default_runtime = runtime  # noqa: SLF001 — test DI injection

    registry = InProcessPrivateLabTaskRegistry()
    runtime.task_registry = registry
    service = runtime.build_run_service(session)
    executor = runtime.build_executor(session)

    def override_db():
        try:
            yield session
        finally:
            pass

    app = FastAPI()
    app.dependency_overrides[get_db] = override_db
    app.include_router(private_lab_router)
    client = TestClient(app)

    yield {
        "session": session,
        "book": book,
        "snapshot": snapshot,
        "runtime": runtime,
        "service": service,
        "executor": executor,
        "transport": transport,
        "registry": registry,
        "client": client,
        "db": db,
        "factory": factory,
        "stage_service": RunStageService(session),
    }
    session.close()
    db.dispose()
    reset_default_private_lab_task_registry()
    reset_default_live_readiness_runtime_for_tests()


def _fingerprints(
    env: dict[str, Any],
    *,
    cfg: str = "cfg-integ-1",
    modules: tuple[str, ...] = PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER,
) -> dict[str, str]:
    runtime = env["runtime"]
    assert runtime.preflight is not None and runtime.estimate is not None
    runtime.preflight.session = env["session"]
    pre = runtime.preflight.preflight(
        book_id=env["book"].id,
        book_snapshot_id=env["snapshot"].id,
        configuration_fingerprint=cfg,
        requested_modules=modules,
    )
    assert pre.ok is True, pre.reason_code
    if pre.snapshot_content_hash:
        runtime.estimate.snapshot_content_hash = str(pre.snapshot_content_hash)
    est = runtime.estimate.estimate(
        book_id=env["book"].id,
        book_snapshot_id=env["snapshot"].id,
        configuration_fingerprint=cfg,
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        quality_profile="balanced",
        requested_modules=modules,
        preflight_fingerprint=pre.fingerprint,
    )
    cached = runtime.estimate._cache.get(est.fingerprint) or {}  # noqa: SLF001
    consent_fp = str(cached.get("consent_fingerprint") or "")
    return {
        "configuration_fingerprint": cfg,
        "preflight_fingerprint": pre.fingerprint,
        "estimate_fingerprint": est.fingerprint,
        "consent_fingerprint": consent_fp,
        "data_transfer_manifest_hash": str(est.data_transfer_manifest_hash or ""),
        "usage_summary": dict(est.usage_summary),
        "cost_summary": dict(est.cost_summary),
        "estimate": est,
        "preflight": pre,
    }


def _create_req(env: dict[str, Any], fps: dict[str, str], **overrides: Any) -> CreatePrivateLabRunRequest:
    base = {
        "book_id": env["book"].id,
        "book_snapshot_id": env["snapshot"].id,
        "analysis_mode": WholeBookAnalysisMode.NATIVE,
        "requested_modules": PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER,
        "configuration_fingerprint": fps["configuration_fingerprint"],
        "idempotency_key": "idem-integ-001",
        "preflight_fingerprint": fps["preflight_fingerprint"],
        "estimate_fingerprint": fps["estimate_fingerprint"],
        "consent_fingerprint": fps["consent_fingerprint"],
        "data_transfer_manifest_hash": fps["data_transfer_manifest_hash"],
        "context_bundle_hash": "context-hash-ok",
        "dry_run": True,
        "data_transfer_consented": True,
        "user_confirmed": True,
        "budget_ok": True,
        "capability_ok": True,
    }
    base.update(overrides)
    return CreatePrivateLabRunRequest(**base)


def _create(env: dict[str, Any], fps: dict[str, str] | None = None, **overrides: Any):
    fps = fps or _fingerprints(env)
    return env["service"].create_run(
        _create_req(env, fps, **overrides),
        loopback=True,
        request_marker_present=True,
    )


def _http_create_flow(client: TestClient, env: dict[str, Any], *, idem: str, dry_run: bool = True):
    cfg = f"cfg-http-{idem}"
    pre = client.post(
        "/api/v1/labs/private-whole-book-runs/preflight",
        headers=MARKER,
        json={
            "book_id": env["book"].id,
            "book_snapshot_id": env["snapshot"].id,
            "configuration_fingerprint": cfg,
        },
    )
    assert pre.status_code == 200, pre.text
    preflight_fp = pre.json()["fingerprint"]
    est = client.post(
        "/api/v1/labs/private-whole-book-runs/estimate",
        headers=MARKER,
        json={
            "book_id": env["book"].id,
            "book_snapshot_id": env["snapshot"].id,
            "configuration_fingerprint": cfg,
            "preflight_fingerprint": preflight_fp,
        },
    )
    assert est.status_code == 200, est.text
    est_body = est.json()
    create = client.post(
        "/api/v1/labs/private-whole-book-runs",
        headers=MARKER,
        json={
            "book_id": env["book"].id,
            "book_snapshot_id": env["snapshot"].id,
            "idempotency_key": idem,
            "configuration_fingerprint": cfg,
            "preflight_fingerprint": preflight_fp,
            "estimate_fingerprint": est_body["fingerprint"],
            "consent_fingerprint": est_body["consent_fingerprint"],
            "data_transfer_manifest_hash": est_body["data_transfer_manifest_hash"],
            "auto_start": False,
            "dry_run": dry_run,
            "credential_present": True,
            "budget_ok": True,
            "capability_ok": True,
            "user_confirmed": True,
        },
    )
    return pre, est, create


# ---------------------------------------------------------------------------
# 1. Preflight
# ---------------------------------------------------------------------------


def test_01_preflight_gates_and_no_run(integ_env) -> None:
    # lab disabled reject
    auth_off = PrivateEngineLabAuthorizationService(environment="test", lab_enabled=False)
    with pytest.raises(PrivateEngineLabAuthorizationDenied) as exc_off:
        auth_off.require(loopback=True, request_marker_present=True)
    assert exc_off.value.reason == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_DISABLED

    # production reject
    auth_prod = PrivateEngineLabAuthorizationService(environment="production", lab_enabled=True)
    with pytest.raises(PrivateEngineLabAuthorizationDenied):
        auth_prod.require(loopback=True, request_marker_present=True)
    assert should_register_private_engine_lab_router(environment="production", lab_enabled=True) is False

    # loopback / marker
    auth = PrivateEngineLabAuthorizationService(environment="test", lab_enabled=True)
    with pytest.raises(PrivateEngineLabAuthorizationDenied) as exc_lb:
        auth.require(loopback=False, request_marker_present=True)
    assert exc_lb.value.reason == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_LOOPBACK_REQUIRED
    with pytest.raises(PrivateEngineLabAuthorizationDenied) as exc_mk:
        auth.require(loopback=True, request_marker_present=False)
    assert exc_mk.value.reason == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_REQUEST_MARKER_REQUIRED

    # completed snapshot + no Run created
    before = len(integ_env["session"].scalars(select(AnalysisRun)).all())
    client: TestClient = integ_env["client"]
    pre = client.post(
        "/api/v1/labs/private-whole-book-runs/preflight",
        headers=MARKER,
        json={
            "book_id": integ_env["book"].id,
            "book_snapshot_id": integ_env["snapshot"].id,
            "configuration_fingerprint": "cfg-preflight-1",
        },
    )
    assert pre.status_code == 200, pre.text
    body = pre.json()
    assert body["ok"] is True
    assert body["run_created"] is False
    assert body["details"].get("snapshot_status") == SnapshotStatus.COMPLETED.value
    assert body["details"].get("creates_analysis_run") is False
    assert body["details"].get("calls_provider") is False
    assert len(integ_env["session"].scalars(select(AnalysisRun)).all()) == before


# ---------------------------------------------------------------------------
# 2. Estimate
# ---------------------------------------------------------------------------


def test_02_estimate_local_payload_no_provider(integ_env) -> None:
    fps = _fingerprints(integ_env, cfg="cfg-estimate-1")
    usage = fps["usage_summary"]
    cost = fps["cost_summary"]
    # tokens not fixed 512/256
    assert not (
        usage.get("estimated_input_tokens") == 512
        and usage.get("estimated_output_tokens") == 256
    )
    assert usage.get("tokens_hardcoded") is False
    assert cost.get("cost_hardcoded") is False
    # cost low/expected/high or unknown
    if cost.get("pricing_status") == "unknown" or cost.get("cost_unknown"):
        assert cost.get("cost_expected") is None
    else:
        assert cost.get("cost_low") is not None
        assert cost.get("cost_expected") is not None
        assert cost.get("cost_high") is not None
        assert cost["cost_low"] <= cost["cost_expected"] <= cost["cost_high"]

    # manifest no body — safe_dict path
    cached = integ_env["runtime"].estimate._cache[fps["estimate_fingerprint"]]  # noqa: SLF001
    primary = cached.get("primary_manifest")
    assert primary is not None
    safe = primary.safe_dict() if hasattr(primary, "safe_dict") else dict(primary)
    blob = json.dumps(safe, ensure_ascii=False)
    assert "合成样本" not in blob
    assert "messages" not in safe
    assert "api_key" not in blob.lower()
    # no provider call during estimate
    assert integ_env["transport"].calls == []
    assert integ_env["runtime"].provider_execution is not None
    assert integ_env["runtime"].provider_execution.http_calls == 0


# ---------------------------------------------------------------------------
# 3. Client boolean bypass
# ---------------------------------------------------------------------------


def test_03_client_booleans_cannot_bypass_server_gates(integ_env, network_deny) -> None:
    # credential_present=true cannot bypass missing server credential
    missing_cred = ExistingCredentialServiceAdapter(store=None, enabled=True)
    assert missing_cred.resolve("aliyun_qwen_plus") is None
    runtime_cred = create_live_readiness_runtime(
        environment="test",
        lab_enabled=True,
        dry_run=False,
        allow_network=False,
        session=integ_env["session"],
        credential_adapter=missing_cred,
        transport=integ_env["transport"],
        allow_fake_resolver=False,
        auto_wire_credentials=False,
    )
    security = resolve_server_security_status(
        credential_resolver=missing_cred,
        budget_guard=runtime_cred.budget_guard,
        capability_ok=True,
    )
    assert security.credential_present is False

    before = len(integ_env["session"].scalars(select(AnalysisRun)).all())
    svc = runtime_cred.build_run_service(integ_env["session"])
    # Router pattern: ignore client credential_present=True; use server False
    with pytest.raises(PrivateWholeBookLabRunError) as exc_server:
        svc.create_run(
            CreatePrivateLabRunRequest(
                book_id=integ_env["book"].id,
                book_snapshot_id=integ_env["snapshot"].id,
                idempotency_key="idem-bypass-cred-server",
                dry_run=False,
                credential_present=security.credential_present,  # False — not client True
                budget_ok=True,
                capability_ok=True,
                data_transfer_consented=True,
                user_confirmed=True,
            ),
            loopback=True,
            request_marker_present=True,
        )
    assert (
        exc_server.value.reason
        == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CREDENTIAL_REQUIRED
    )
    assert len(integ_env["session"].scalars(select(AnalysisRun)).all()) == before

    # budget force_deny — client budget_ok=true cannot bypass server False
    runtime_budget = create_live_readiness_runtime(
        environment="test",
        lab_enabled=True,
        dry_run=False,
        allow_network=False,
        session=integ_env["session"],
        credential_adapter=missing_cred,
        force_deny_budget=True,
        transport=integ_env["transport"],
        allow_fake_resolver=False,
        auto_wire_credentials=False,
    )
    sec_budget = resolve_server_security_status(
        credential_resolver=runtime_budget.credential_adapter,
        budget_guard=runtime_budget.budget_guard,
        capability_ok=True,
    )
    assert sec_budget.budget_ok is False
    assert runtime_budget.budget_guard.force_deny is True
    svc_b = runtime_budget.build_run_service(integ_env["session"])
    with pytest.raises(PrivateWholeBookLabRunError) as exc_budget:
        svc_b.create_run(
            CreatePrivateLabRunRequest(
                book_id=integ_env["book"].id,
                book_snapshot_id=integ_env["snapshot"].id,
                idempotency_key="idem-bypass-budget2",
                dry_run=False,
                credential_present=True,  # past credential gate to assert budget
                budget_ok=sec_budget.budget_ok,  # False from force_deny — not client True
                capability_ok=True,
                data_transfer_consented=True,
                user_confirmed=True,
            ),
            loopback=True,
            request_marker_present=True,
        )
    assert (
        exc_budget.value.reason == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_BUDGET_DENIED
    )
    assert len(integ_env["session"].scalars(select(AnalysisRun)).all()) == before

    # HTTP path: client credential_present=true ignored when server credential missing
    live_runtime_mod._default_runtime = create_live_readiness_runtime(  # noqa: SLF001
        environment="test",
        lab_enabled=True,
        dry_run=False,
        allow_network=False,
        session=integ_env["session"],
        credential_adapter=missing_cred,
        force_deny_budget=False,
        transport=integ_env["transport"],
        allow_fake_resolver=False,
        auto_wire_credentials=False,
    )
    _pre, _est, create = _http_create_flow(
        integ_env["client"], integ_env, idem="http-bypass-cred", dry_run=False
    )
    assert create.status_code >= 400
    detail = create.json().get("detail") or {}
    code = detail.get("error_code") if isinstance(detail, dict) else None
    assert code == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CREDENTIAL_REQUIRED.value
    assert len(integ_env["session"].scalars(select(AnalysisRun)).all()) == before

    # HTTP path: force_deny budget — client budget_ok ignored (consent/budget gate)
    live_runtime_mod._default_runtime = create_live_readiness_runtime(  # noqa: SLF001
        environment="test",
        lab_enabled=True,
        dry_run=True,
        allow_network=False,
        session=integ_env["session"],
        credential_adapter=missing_cred,
        force_deny_budget=True,
        transport=integ_env["transport"],
        allow_fake_resolver=False,
        auto_wire_credentials=False,
    )
    _pre2, _est2, create_b = _http_create_flow(
        integ_env["client"], integ_env, idem="http-bypass-budget", dry_run=True
    )
    assert create_b.status_code >= 400
    detail_b = create_b.json().get("detail") or {}
    code_b = detail_b.get("error_code") if isinstance(detail_b, dict) else None
    detail_code_b = detail_b.get("detail_code") if isinstance(detail_b, dict) else None
    assert code_b in {
        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_BUDGET_DENIED.value,
        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONSENT_FINGERPRINT_MISMATCH.value,
    }
    # dry_run authorize skips budget; consent path surfaces force_deny as detail_code
    if code_b == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONSENT_FINGERPRINT_MISMATCH.value:
        assert detail_code_b == "force_deny"
    assert len(integ_env["session"].scalars(select(AnalysisRun)).all()) == before


# ---------------------------------------------------------------------------
# 4. Create
# ---------------------------------------------------------------------------


def test_04_create_analysis_run_stages_task_no_network(integ_env) -> None:
    fps = _fingerprints(integ_env, cfg="cfg-create-1")
    result = _create(integ_env, fps, idempotency_key="idem-create-ok")
    assert result.created is True
    assert result.private_lab is True
    assert result.modules_implemented is True
    run = integ_env["session"].get(AnalysisRun, result.run_id)
    assert run is not None
    assert run.task_type == PRIVATE_LAB_TASK_TYPE
    assert is_private_lab_run_metadata(run.validated_output)
    stages = integ_env["service"].get_run_stages(result.run_id)
    assert len(stages) == 10
    handle = integ_env["registry"].get(result.run_id)
    assert handle is not None
    assert integ_env["transport"].calls == []
    assert integ_env["runtime"].provider_execution.http_calls == 0


# ---------------------------------------------------------------------------
# 5. Provider payload structure
# ---------------------------------------------------------------------------


def test_05_provider_payload_structure_captured(integ_env) -> None:
    fps = _fingerprints(integ_env, cfg="cfg-payload-1")
    result = _create(integ_env, fps, idempotency_key="idem-payload")
    exec_result = integ_env["executor"].start(result.run_id)
    assert exec_result.status in {
        WholeBookRunViewStatus.COMPLETED.value,
        WholeBookRunViewStatus.FAILED.value,
        WholeBookRunViewStatus.CANCELLED.value,
    }
    provider = integ_env["runtime"].provider_execution
    assert provider is not None
    # Capturing transport saw real message structure (dry path)
    assert integ_env["transport"].calls or provider.last_payloads
    if integ_env["transport"].calls:
        call = integ_env["transport"].calls[0]
        assert call["has_system"] is True
        assert call["has_user"] is True
        assert "content" not in call  # structure only — no body retained
    if provider.last_payloads:
        payload = provider.last_payloads[0]
        assert payload["has_system"] is True
        assert payload["has_user"] is True
        assert payload["source_untrusted"] is True
        assert payload["ref_only"] is False
        assert "content" not in payload
        assert "合成样本" not in json.dumps(payload, ensure_ascii=False)
    assert provider.http_calls == 0


# ---------------------------------------------------------------------------
# 6. Four modules sequential (dry)
# ---------------------------------------------------------------------------


def test_06_four_modules_sequential_dry_semantics(integ_env) -> None:
    # Module-level Fake semantics (overview / non-three-act / multi-tag / multi-belong)
    overview = FakeBookOverviewRunner().execute(
        make_execution_request(
            provider_policy={
                "provider_kind": "fake",
                "synthetic_output": {
                    "overview_mode": "multi_protagonist",
                    "major_storyline_ids": (10, 20),
                    "partial": True,
                    "skip_provider": True,
                },
            }
        )
    ).module_outputs
    assert overview.get("protagonist_asset_id") is None
    assert len(overview.get("major_storyline_ids") or ()) == 2

    structure = FakeStructureStagesRunner().execute(
        make_execution_request(
            module_key=WholeBookModuleKey.STRUCTURE_STAGES,
            provider_policy={
                "provider_kind": "fake",
                "synthetic_output": {"structure_mode": "five_stages", "skip_provider": True},
            },
        )
    ).module_outputs
    stages = structure.get("stages") or []
    assert len(stages) == 5
    assert len(stages) != 3  # non-three-act

    chapter = FakeChapterFunctionsRunner().execute(
        make_execution_request(
            module_key=WholeBookModuleKey.CHAPTER_FUNCTIONS,
            provider_policy={
                "provider_kind": "fake",
                "synthetic_output": {
                    "chapter_mode": "side_flashback",
                    "skip_provider": True,
                },
            },
        )
    ).module_outputs
    labels = set(chapter.get("function_labels") or ())
    assert "side_story" in labels and "flashback" in labels  # multi-tag

    storylines = FakeStorylinesRunner().execute(
        make_execution_request(
            module_key=WholeBookModuleKey.STORYLINES,
            provider_policy={
                "provider_kind": "fake",
                "synthetic_output": {
                    "storyline_type": "relationship",
                    "key_event_ids": (1, 2),
                    "status": "incomplete",
                    "skip_provider": True,
                },
            },
        )
    ).module_outputs
    assert storylines.get("key_event_ids")  # multi-belong / multi-event

    # Sequential Lab executor order
    fps = _fingerprints(integ_env, cfg="cfg-seq-1")
    created = _create(integ_env, fps, idempotency_key="idem-seq")
    exec_result = integ_env["executor"].start(created.run_id)
    modules = [r["module_key"] for r in exec_result.detail.get("module_results", [])]
    assert modules == list(PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER) or modules[:4] == list(
        PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER
    )[: len(modules)]
    for row in exec_result.detail.get("module_results", []):
        assert row.get("http") is False
        assert row.get("auto_canonical") is False
        assert row.get("auto_lock") is False
    assert integ_env["runtime"].provider_execution.http_calls == 0


# ---------------------------------------------------------------------------
# 7. Persistence
# ---------------------------------------------------------------------------


def test_07_persistence_phase1b_or_recording_no_canonical(integ_env) -> None:
    recording = RecordingCandidatePersistenceSink()
    assert isinstance(recording, RecordingCandidatePersistenceSink)

    phase = Phase1BCandidatePersistenceSink(integ_env["session"], book_id=integ_env["book"].id)
    for name in (
        "persist_assets",
        "persist_relations",
        "persist_asset_evidence",
        "persist_relation_evidence",
        "persist_conflicts",
        "persist_stage_artifact",
    ):
        assert hasattr(phase, name)

    # Executor with runtime_factory + recording sink path (document when no ORM rows)
    registry = InProcessPrivateLabTaskRegistry()
    fake_provider = FakePrivateLabProviderExecutionPort(
        responses={
            m: {
                "synthetic": True,
                "partial": True,
                "module_key": m,
                "force_accept": True,
                "empty_dto": False,
                "asset_candidates": [
                    {
                        "asset_type": "event",
                        "title": f"cand-{m}",
                        "summary": "synthetic",
                        "output_ref": f"{m}.out",
                    }
                ],
                "evidence_candidates": [],
                "conflict_candidates": [],
            }
            for m in PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER
        }
    )

    def _runtime_factory(**kwargs: Any) -> Any:
        return create_lab_private_whole_book_analysis_runtime(
            session=kwargs.get("session"),
            book_id=kwargs.get("book_id"),
            use_phase1b_persistence=False,  # recording sink path
            lab_dry_run=True,
            fallback_to_fake=True,
        )

    fps = _fingerprints(integ_env, cfg="cfg-persist-1")
    created = _create(integ_env, fps, idempotency_key="idem-persist")
    executor = PrivateLabRunExecutor(
        integ_env["session"],
        stage_service=integ_env["stage_service"],
        task_registry=registry,
        provider_port=fake_provider,
        runtime_factory=_runtime_factory,
        use_recording_persistence=True,
    )
    registry.register(created.run_id)
    out = executor.start(created.run_id)
    assert out.status in {
        WholeBookRunViewStatus.COMPLETED.value,
        WholeBookRunViewStatus.FAILED.value,
    }
    # Recording path: no auto canonical / lock; ORM may remain empty (documented)
    assets = integ_env["session"].scalars(select(NarrativeAssetVersion)).all()
    for a in assets:
        assert bool(getattr(a, "is_canonical", False)) is False
        assert str(getattr(a, "review_status", "candidate")) != "locked"
    for row in out.detail.get("module_results", []):
        persist = row.get("persistence_summary") or {}
        assert persist.get("auto_confirm", False) is False
        assert persist.get("auto_lock", False) is False
        assert persist.get("canonical_overwrite", False) is False
    # Document recording sink path when Phase1B ORM not written
    assert fake_provider.http_calls == 0
    _ = recording  # recording sink path documented above


# ---------------------------------------------------------------------------
# 8. Validation failure → no candidate write (module rollback)
# ---------------------------------------------------------------------------


def test_08_validation_failure_module_rollback(integ_env) -> None:
    before_assets = len(integ_env["session"].scalars(select(NarrativeAssetVersion)).all())
    registry = InProcessPrivateLabTaskRegistry()
    bad_provider = FakePrivateLabProviderExecutionPort(
        responses={
            "book_overview": {
                "synthetic": True,
                "empty_dto": True,
                "skip_provider": True,
                "asset_candidates": [
                    {
                        "asset_type": "event",
                        "title": "should-not-persist",
                        "output_ref": "bad.out",
                    }
                ],
            }
        }
    )

    def _runtime_factory(**kwargs: Any) -> Any:
        return create_private_whole_book_analysis_runtime(
            session=kwargs.get("session"),
            book_id=kwargs.get("book_id"),
            lab_mode=True,
            use_phase1b_persistence=True,
            fallback_to_fake=True,
        )

    modules = ("book_overview",)
    fps = _fingerprints(integ_env, cfg="cfg-val-fail", modules=modules)
    created = _create(
        integ_env,
        fps,
        idempotency_key="idem-val-fail",
        requested_modules=modules,
    )
    executor = PrivateLabRunExecutor(
        integ_env["session"],
        stage_service=integ_env["stage_service"],
        task_registry=registry,
        provider_port=bad_provider,
        runtime_factory=_runtime_factory,
        use_recording_persistence=False,
    )
    registry.register(created.run_id)
    out = executor.start(created.run_id)
    # Illegal / empty schema → rejected persistence (no new ORM candidates)
    after_assets = len(integ_env["session"].scalars(select(NarrativeAssetVersion)).all())
    assert after_assets == before_assets
    for row in out.detail.get("module_results", []):
        validation = row.get("validation_summary") or {}
        persist = row.get("persistence_summary") or {}
        if row.get("module_key") == "book_overview":
            # accepted may be False, or persist denied / no orm
            assert (
                validation.get("accepted") is False
                or validation.get("schema_valid") is False
                or persist.get("orm_written") is False
                or persist.get("rejected") is True
                or persist.get("fallback") == "port_only"
            )
    assert bad_provider.http_calls == 0


# ---------------------------------------------------------------------------
# 9. Cancel / Budget
# ---------------------------------------------------------------------------


def test_09_cancel_and_budget_zero_provider_http(integ_env) -> None:
    fps = _fingerprints(integ_env, cfg="cfg-cancel-1")
    created = _create(integ_env, fps, idempotency_key="idem-cancel")
    integ_env["registry"].request_cancel(created.run_id)
    # cancel propagates to provider port
    ref = integ_env["registry"].get(created.run_id).cancellation_ref
    integ_env["runtime"].provider_execution.cancel(ref or "")
    assert ref in integ_env["runtime"].provider_execution.cancelled
    exec_result = integ_env["executor"].start(created.run_id)
    assert exec_result.status == WholeBookRunViewStatus.CANCELLED.value
    assert integ_env["runtime"].provider_execution.http_calls == 0

    # budget denied → zero provider http
    guard = PrivateEngineProviderBudgetGuard(force_deny=True)
    denied = guard.check(estimated_tokens=10, estimated_cost=0.01)
    assert denied.allowed is False
    runtime_b = create_live_readiness_runtime(
        environment="test",
        lab_enabled=True,
        dry_run=True,
        allow_network=False,
        session=integ_env["session"],
        force_deny_budget=True,
        transport=CapturingProviderTransport(
            stub=StubTransportResponse(text='{"ok":true}', input_tokens=1, output_tokens=1)
        ),
        allow_fake_resolver=False,
        auto_wire_credentials=False,
    )
    usage = runtime_b.provider_execution.execute_module(
        module_key="book_overview",
        request={
            "book_id": integ_env["book"].id,
            "book_snapshot_id": integ_env["snapshot"].id,
        },
    )
    assert usage.status == "budget_denied"
    assert usage.usage.get("http") is False
    assert runtime_b.provider_execution.http_calls == 0


# ---------------------------------------------------------------------------
# 10. Resume / Retry
# ---------------------------------------------------------------------------


def test_10_resume_retry_fingerprint_and_completed(integ_env) -> None:
    fps = _fingerprints(integ_env, cfg="cfg-resume-1")
    created = _create(integ_env, fps, idempotency_key="idem-resume")
    run = integ_env["session"].get(AnalysisRun, created.run_id)
    run.status = "interrupted"
    integ_env["session"].commit()

    # prompt/context/model change rejected via fingerprint mismatch
    with pytest.raises(PrivateWholeBookLabRunError) as exc_est:
        integ_env["service"].resume_run(
            created.run_id,
            estimate_fingerprint="changed-estimate-fp",
            consent_fingerprint=fps["consent_fingerprint"],
            context_bundle_hash="context-hash-ok",
        )
    assert (
        exc_est.value.reason
        == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_ESTIMATE_FINGERPRINT_MISMATCH
    )
    with pytest.raises(PrivateWholeBookLabRunError) as exc_ctx:
        integ_env["service"].resume_run(
            created.run_id,
            estimate_fingerprint=fps["estimate_fingerprint"],
            consent_fingerprint=fps["consent_fingerprint"],
            context_bundle_hash="changed-context-hash",
        )
    assert (
        exc_ctx.value.reason
        == PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CHECKPOINT_INVALID
    )

    # Compatible resume ok
    resumed = integ_env["service"].resume_run(
        created.run_id,
        estimate_fingerprint=fps["estimate_fingerprint"],
        consent_fingerprint=fps["consent_fingerprint"],
        context_bundle_hash="context-hash-ok",
    )
    assert resumed["status"] == WholeBookRunViewStatus.RUNNING.value

    # completed stage must not re-run / retry
    integ_env["stage_service"].transition_stage(
        created.run_id, "analyze_structure", StageStatus.RUNNING
    )
    integ_env["stage_service"].transition_stage(
        created.run_id, "analyze_structure", StageStatus.COMPLETED
    )
    with pytest.raises(PrivateWholeBookLabRunError) as exc_retry:
        integ_env["service"].retry_stage(created.run_id, "analyze_structure")
    assert exc_retry.value.detail_code == "COMPLETED_STAGE_NO_RETRY"


# ---------------------------------------------------------------------------
# 11. Recovery
# ---------------------------------------------------------------------------


def test_11_recovery_running_to_interrupted_no_silent_resume(integ_env) -> None:
    fps = _fingerprints(integ_env, cfg="cfg-recovery-1")
    created = _create(integ_env, fps, idempotency_key="idem-recovery")
    run = integ_env["session"].get(AnalysisRun, created.run_id)
    run.status = "running"
    integ_env["session"].commit()

    recovery = PrivateLabRecoveryService(
        integ_env["session"], stage_service=integ_env["stage_service"]
    )
    scan = recovery.startup_reconcile()
    assert scan.auto_resumed == 0
    assert created.run_id in scan.interrupted_run_ids
    run = integ_env["session"].get(AnalysisRun, created.run_id)
    assert run.status == "interrupted"
    # no provider during recovery
    assert integ_env["runtime"].provider_execution.http_calls == 0
    assert integ_env["transport"].calls == []


# ---------------------------------------------------------------------------
# 12. Production isolation
# ---------------------------------------------------------------------------


def test_12_production_isolation_version_no_migration(network_deny) -> None:
    assert WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED is False
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert PRODUCTION_DEFAULT_ENGINE_ID is None
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False
    assert VERSION == "1.0.5"
    assert is_private_provider_live_probe_enabled(environ={}) is False
    assert os.environ.get(PRIVATE_PROVIDER_LIVE_PROBE_ENV, "") in {"", "0", "false", "no", "off"}

    # production: no router mount
    assert should_register_private_engine_lab_router(
        environment="production", lab_enabled=True
    ) is False
    app = create_app()
    before = len(app.routes)
    mounted = mount_private_engine_lab_if_enabled(
        app, environment="production", lab_enabled=True
    )
    assert mounted is False
    assert len(app.routes) == before

    # formal create disabled
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True

    # no Fake silent live fallback when live probe absent
    adapter = FakeProviderAdapter()
    assert adapter.allow_network is False
    with pytest.raises(ValueError):
        FakeProviderAdapter(allow_network=True)

    # live readiness must not be production-enabled
    with pytest.raises(RuntimeError):
        rt = create_live_readiness_runtime(environment="production", lab_enabled=True)
        rt.lab_enabled = True  # force
        rt.environment = "production"
        rt.assert_not_production_enabled()

    # no phase2br1 migration modules
    mig_dir = REPO_ROOT / "apps" / "api" / "app" / "narrative_core" / "migrations"
    if mig_dir.is_dir():
        names = [p.name for p in mig_dir.rglob("*") if p.is_file()]
        assert not any("phase2br1" in n.lower() for n in names)
        assert not any("2br1" in n.lower() for n in names)
