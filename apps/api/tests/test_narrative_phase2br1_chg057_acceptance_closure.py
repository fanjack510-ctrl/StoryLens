"""CHG-20260724-057 BookOverview Provider Output Contract Enforcement — final acceptance.

Direct product-boundary acceptance (HTTP Lab + FakeHttpProviderTransport + executor).
Zero real network. Independent temp SQLite per test (pytest tmp_path).

AUTHORITY: STAGE_PROVIDER_ATTEMPT_IS_AUTHORITATIVE
  Lab Live provider call ledger = Stage provider_attempt checkpoints (+ FakeHttp call log).
  model_invocations remains legacy chapter/scene structured_output ledger only.
"""

from __future__ import annotations

# STAGE_PROVIDER_ATTEMPT_IS_AUTHORITATIVE — Lab Live ledger (not model_invocations).
STAGE_PROVIDER_ATTEMPT_IS_AUTHORITATIVE = "STAGE_PROVIDER_ATTEMPT_IS_AUTHORITATIVE"

import json
import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from typing import Any

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
    BookSnapshotParagraph,
    Chapter,
    ModelInvocation,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    Paragraph,
)
from app.db.session import get_db
from app.narrative_core.enums import SnapshotStatus, StageStatus
from app.narrative_core.migrations.runner import (
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)
from app.narrative_core.private_engine_contract.model_invocation_authority import AUTHORITY
from app.narrative_core.private_engine_contract.provider_estimate import estimate_fingerprint_for
from app.narrative_core.run_shell_contract.private_engine_lab import (
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER,
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_VALUE,
    PRIVATE_PROVIDER_LIVE_PROBE_ENV,
)
from app.narrative_core.services.book_overview_output_contract import (
    FAILURE_UNDECLARED_TOP_LEVEL,
)
from app.narrative_core.services.in_process_private_lab_task_registry import (
    InProcessPrivateLabTaskRegistry,
    reset_default_private_lab_task_registry,
)
from app.narrative_core.services.private_whole_book_analysis_runtime import (
    try_load_first_four_private_runners,
)
from app.narrative_core.services.private_whole_book_live_readiness_runtime import (
    create_live_readiness_runtime,
    reset_default_live_readiness_runtime_for_tests,
)
from app.narrative_core.services.provider_transport_kind import FakeHttpProviderTransport
from app.narrative_core.services.quote_resolution import SnapshotQuoteIndex
from app.narrative_core.services.run_stage_service import RunStageService
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_provider_gateway import (
    CapturingProviderTransport,
    ExistingCredentialServiceAdapter,
    StubTransportResponse,
)
from app.routers.whole_book_private_engine_lab_runs import (
    reset_private_engine_lab_sessions_for_tests,
    router as private_lab_router,
)
from app.routers.whole_book_results import router as whole_book_results_router
import app.narrative_core.services.private_whole_book_live_readiness_runtime as live_runtime_mod

MARKER = {
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER: PRIVATE_ENGINE_LAB_REQUEST_MARKER_VALUE,
}
assert AUTHORITY == STAGE_PROVIDER_ATTEMPT_IS_AUTHORITATIVE

_SENSITIVE_TOKENS = (
    "sk-test-not-real",
    "system_instruction",
    "raw_response",
    "evidence_map",
    "合成段落甲。",
)


def _require_private_engine() -> None:
    if try_load_first_four_private_runners() is None:
        pytest.skip("storylens_private_engine not installed")


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


class _FakeKeyStore:
    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._map = dict(mapping or {})

    def available(self) -> bool:
        return True

    def get(self, provider_kind: str) -> str | None:
        return self._map.get(provider_kind)


def _seed_book(session: Session) -> Book:
    book = Book(
        title="CHG057 Acceptance",
        source_file_name="chg057-ac.txt",
        source_file_hash="c" * 64,
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
        word_count=6,
    )
    session.add(chapter)
    session.flush()
    session.add(
        Paragraph(
            id=f"B{book.id:04d}-C0001-P0001",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=1,
            raw_text="合成段落甲。",
            normalized_text="合成段落甲。",
            char_start=0,
            char_end=6,
        )
    )
    session.commit()
    return book


def _synthetic_dto(env: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """BookOverviewResultDto-shaped flat payload — evidence_id = snapshot paragraph PK."""

    sp = env["paragraph"]
    base: dict[str, Any] = {
        "logline": "合成总览一句话",
        "premise": "合成前提说明",
        "central_question": "合成核心问题",
        "primary_conflict": "合成主要冲突",
        "protagonist_asset_id": None,
        "major_storyline_ids": [],
        "structure_summary": "合成结构摘要",
        "ending_state": "unknown",
        "confidence": 0.7,
        "evidence_refs": [
            {
                "evidence_id": str(sp.id),
                "evidence_role": "support",
                "target_output_ref": "book_overview.claim",
            }
        ],
    }
    base.update(overrides)
    # CHG-057: never inject undeclared top-level keys (partial/synthetic/wrappers).
    for banned in ("partial", "synthetic", "book_overview", "evidence_map", "claims"):
        base.pop(banned, None)
    return base


def _invalid_envelope_dto(env: dict[str, Any]) -> dict[str, Any]:
    """Undeclared wrapper shape — triggers UNDECLARED_TOP_LEVEL_FIELDS."""

    flat = _synthetic_dto(env)
    return {
        "book_overview": {
            k: v
            for k, v in flat.items()
            if k not in {"evidence_refs", "partial", "synthetic", "confidence"}
        },
        "evidence_map": {"ignored": True},
        "synthetic": False,
    }


def _configure_fake_http(
    env: dict[str, Any],
    *,
    stub_texts: list[str] | None = None,
    stub_text: str | None = None,
    request_ids: list[str] | None = None,
    request_id: str = "fake-http-valid-1",
    input_tokens: int = 90,
    output_tokens: int = 45,
) -> FakeHttpProviderTransport:
    fake: FakeHttpProviderTransport = env["fake_http"]
    fake.stub_texts = list(stub_texts) if stub_texts is not None else []
    fake.stub_text = stub_text if stub_text is not None else (stub_texts[0] if stub_texts else "")
    fake.request_ids = list(request_ids) if request_ids else []
    fake.request_id = request_id
    fake.input_tokens = int(input_tokens)
    fake.output_tokens = int(output_tokens)
    fake.calls.clear()
    fake._call_index = 0  # noqa: SLF001 — reset FakeHttp call cursor between scenarios
    return fake


@pytest.fixture
def product_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Independent temp SQLite + Live readiness DI + FastAPI Lab/Results client."""

    _require_private_engine()
    reset_default_private_lab_task_registry()
    reset_private_engine_lab_sessions_for_tests()
    reset_default_live_readiness_runtime_for_tests()

    monkeypatch.setenv(PRIVATE_PROVIDER_LIVE_PROBE_ENV, "1")
    monkeypatch.setenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", "1")

    def _deny(*_a: Any, **_k: Any) -> None:
        raise AssertionError(
            "network denied: Provider HTTP must not leave FakeHttp in CHG-057 acceptance"
        )

    try:
        import httpx

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

    db = _fk_engine(f"sqlite:///{tmp_path / 'chg057-acceptance.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    session = factory()
    book = _seed_book(session)
    snapshot = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    assert snapshot.snapshot_status == SnapshotStatus.COMPLETED.value
    paragraph = session.scalars(
        select(BookSnapshotParagraph).where(BookSnapshotParagraph.snapshot_id == snapshot.id)
    ).first()
    assert paragraph is not None

    store = _FakeKeyStore({"aliyun_qwen_plus": "sk-test-not-real"})
    fake_cred = ExistingCredentialServiceAdapter(store=store, enabled=True)
    capturing = CapturingProviderTransport(
        stub=StubTransportResponse(
            text='{"synthetic":true,"partial":true}',
            model="qwen3.7-plus",
            request_id="cap-dry",
            input_tokens=1,
            output_tokens=1,
        )
    )
    fake_http = FakeHttpProviderTransport(
        stub_text="{}",
        request_id="fake-http-pending",
        input_tokens=90,
        output_tokens=45,
        http_status=200,
    )
    runtime = create_live_readiness_runtime(
        environment="test",
        lab_enabled=True,
        dry_run=False,
        allow_network=None,
        session=session,
        transport=capturing,
        live_transport=fake_http,
        credential_adapter=fake_cred,
        allow_fake_resolver=False,
        explicit_test_transport_override=True,
        auto_wire_credentials=False,
    )
    live_runtime_mod._default_runtime = runtime  # noqa: SLF001 — test DI injection

    registry = InProcessPrivateLabTaskRegistry()
    runtime.task_registry = registry
    service = runtime.build_run_service(session)
    executor = runtime.build_executor(session)
    stage_service = RunStageService(session)

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
        "paragraph": paragraph,
        "runtime": runtime,
        "service": service,
        "executor": executor,
        "build_executor": lambda: runtime.build_executor(session),
        "stage_service": stage_service,
        "registry": registry,
        "client": client,
        "fake_http": fake_http,
        "capturing": capturing,
        "cred": fake_cred,
        "db": db,
        "factory": factory,
    }
    session.close()
    db.dispose()
    live_runtime_mod._default_runtime = None  # noqa: SLF001
    reset_default_private_lab_task_registry()
    reset_private_engine_lab_sessions_for_tests()
    reset_default_live_readiness_runtime_for_tests()


def _http_flow(
    client: TestClient,
    env: dict[str, Any],
    *,
    idem: str,
    modules: tuple[str, ...] = ("book_overview",),
    dry_run: bool = False,
    auto_start: bool = False,
    estimate_fingerprint_override: str | None = None,
    consent_fingerprint_override: str | None = None,
):
    """POST preflight → estimate → create with fingerprints from HTTP bodies."""

    cfg = f"cfg-ac-{idem}"
    module_list = list(modules)
    pre = client.post(
        "/api/v1/labs/private-whole-book-runs/preflight",
        headers=MARKER,
        json={
            "book_id": env["book"].id,
            "book_snapshot_id": env["snapshot"].id,
            "configuration_fingerprint": cfg,
            "requested_modules": module_list,
        },
    )
    est = client.post(
        "/api/v1/labs/private-whole-book-runs/estimate",
        headers=MARKER,
        json={
            "book_id": env["book"].id,
            "book_snapshot_id": env["snapshot"].id,
            "configuration_fingerprint": cfg,
            "preflight_fingerprint": pre.json().get("fingerprint", "missing")
            if pre.status_code == 200
            else "missing",
            "requested_modules": module_list,
        },
    )
    est_body = est.json() if est.status_code == 200 else {}
    create = client.post(
        "/api/v1/labs/private-whole-book-runs",
        headers=MARKER,
        json={
            "book_id": env["book"].id,
            "book_snapshot_id": env["snapshot"].id,
            "idempotency_key": idem,
            "configuration_fingerprint": cfg,
            "requested_modules": module_list,
            "preflight_fingerprint": pre.json().get("fingerprint", "missing")
            if pre.status_code == 200
            else "missing",
            "estimate_fingerprint": estimate_fingerprint_override
            if estimate_fingerprint_override is not None
            else est_body.get("fingerprint", "missing"),
            "consent_fingerprint": consent_fingerprint_override
            if consent_fingerprint_override is not None
            else est_body.get("consent_fingerprint", "missing"),
            "data_transfer_manifest_hash": est_body.get(
                "data_transfer_manifest_hash", "missing"
            ),
            "auto_start": auto_start,
            "dry_run": dry_run,
            "credential_present": True,
            "budget_ok": True,
            "capability_ok": True,
            "user_confirmed": True,
        },
    )
    return pre, est, create


def _orm_counts(session: Session) -> dict[str, int]:
    return {
        "assets": int(session.scalar(select(func.count()).select_from(NarrativeAsset)) or 0),
        "versions": int(
            session.scalar(select(func.count()).select_from(NarrativeAssetVersion)) or 0
        ),
        "evidence": int(
            session.scalar(select(func.count()).select_from(NarrativeAssetEvidence)) or 0
        ),
        "artifacts": int(
            session.scalar(select(func.count()).select_from(AnalysisArtifact)) or 0
        ),
        "model_invocations": int(
            session.scalar(select(func.count()).select_from(ModelInvocation)) or 0
        ),
    }


def _stage_checkpoint(session: Session, run_id: int) -> dict[str, Any]:
    stages = list(
        session.scalars(
            select(AnalysisRunStage).where(AnalysisRunStage.run_id == int(run_id))
        ).all()
    )
    for stage in stages:
        raw = stage.checkpoint_json or "{}"
        try:
            payload = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict) and payload:
            return payload
    return {}


def _provider_attempt_payload(session: Session, run_id: int) -> dict[str, Any]:
    stages = list(
        session.scalars(
            select(AnalysisRunStage).where(AnalysisRunStage.run_id == int(run_id))
        ).all()
    )
    for stage in stages:
        try:
            payload = json.loads(stage.checkpoint_json or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("checkpoint_kind") == "provider_attempt":
            return payload
        nested = payload.get("pipeline_diagnostics") if isinstance(payload, dict) else None
        if isinstance(nested, dict) and nested.get("checkpoint_kind") == "provider_attempt":
            return nested
    return {}


def _module_result_usage(env: dict[str, Any], run_id: int) -> dict[str, Any]:
    results = env["executor"].get_module_results(int(run_id))
    if not results:
        return {}
    return dict(results[0].get("usage") or {})


def _pipeline_diags(env: dict[str, Any], run_id: int) -> dict[str, Any]:
    results = env["executor"].get_module_results(int(run_id))
    if not results:
        # Fall back to stage checkpoint pipeline_diagnostics after overwrite.
        cp = _stage_checkpoint(env["session"], run_id)
        return dict(cp.get("pipeline_diagnostics") or {})
    persist = dict(results[0].get("persistence_summary") or {})
    diags = dict(persist.get("pipeline_diagnostics") or {})
    if diags:
        return diags
    cp = _stage_checkpoint(env["session"], run_id)
    return dict(cp.get("pipeline_diagnostics") or {})


def _assert_no_sensitive(blob: str) -> None:
    lower = blob.lower()
    for token in _SENSITIVE_TOKENS:
        assert token.lower() not in lower, f"sensitive token leaked: {token}"
    # Key-shaped leaks only (avoid matching credential_absent / credential_present flags).
    assert '"api_key"' not in lower
    assert '"prompt"' not in lower
    assert '"credential"' not in lower
    assert '"messages"' not in lower
    assert '"full_text"' not in lower


def _assert_fail_closed(session: Session, run_id: int, result_json: dict[str, Any]) -> None:
    """Shared fail-closed invariants for product-boundary failure cases."""

    run = session.get(AnalysisRun, int(run_id))
    assert run is not None
    assert str(run.status).lower() not in {"completed", "complete"}

    stages = list(
        session.scalars(
            select(AnalysisRunStage).where(AnalysisRunStage.run_id == int(run_id))
        ).all()
    )
    producer = [s for s in stages if s.stage_key == "analyze_structure"]
    assert producer
    assert StageStatus(producer[0].status) != StageStatus.COMPLETED

    modules = list(result_json.get("modules") or [])
    bo = next((m for m in modules if m.get("module_key") == "book_overview"), None)
    if bo is not None:
        assert str(bo.get("module_status") or "").lower() != "completed"

    counts = _orm_counts(session)
    assert counts["assets"] == 0
    assert counts["versions"] == 0
    assert counts["evidence"] == 0
    assert counts["model_invocations"] == 0

    dump = json.dumps(result_json, ensure_ascii=False)
    _assert_no_sensitive(dump)
    for stage in stages:
        stage_blob = str(stage.checkpoint_json or "")
        _assert_no_sensitive(stage_blob)
        assert '"synthetic_success": true' not in stage_blob.lower().replace(" ", "")
    assert '"synthetic": true' not in dump.lower().replace(" ", "")


def _create_and_start(
    env: dict[str, Any],
    *,
    idem: str,
    expect_create_ok: bool = True,
    modules: tuple[str, ...] = ("book_overview",),
) -> tuple[Any, Any, Any, Any]:
    client: TestClient = env["client"]
    pre, est, create = _http_flow(
        client, env, idem=idem, dry_run=False, auto_start=False, modules=modules
    )
    if expect_create_ok:
        assert pre.status_code == 200, pre.text
        assert est.status_code == 200, est.text
        assert create.status_code == 200, create.text
        body = create.json()
        assert body.get("created") is True or body.get("run_id") or body.get("lab_run_id")
        run_id = int(body.get("run_id") or body.get("lab_run_id"))
        exec_result = env["executor"].start(run_id)
        return pre, est, create, exec_result
    return pre, est, create, None


# ---------------------------------------------------------------------------
# Scenario A / B / C
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Legacy Private Lab replay was superseded by formal Whole-Book V2 execution-context binding")
def test_ac_router_create_scenario_a_valid_flat_no_repair(product_env) -> None:
    env = product_env
    dto = _synthetic_dto(env)
    _configure_fake_http(
        env,
        stub_texts=[json.dumps(dto, ensure_ascii=False)],
        request_ids=["fake-http-valid-1"],
        request_id="fake-http-valid-1",
        input_tokens=90,
        output_tokens=45,
    )

    pre, est, create, exec_result = _create_and_start(env, idem="ac-a-norepair")
    assert pre.status_code == 200
    assert est.status_code == 200
    assert create.status_code == 200
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() in {"completed", "complete"}

    fake: FakeHttpProviderTransport = env["fake_http"]
    assert len(fake.calls) == 1
    assert len(env["capturing"].calls) == 0

    usage = _module_result_usage(env, run_id)
    contract = dict(usage.get("output_contract") or {})
    diags = _pipeline_diags(env, run_id)
    repair_attempted = contract.get("repair_attempted")
    if repair_attempted is None:
        repair_attempted = diags.get("repair_attempted")
    repair_count = contract.get("repair_count")
    if repair_count is None:
        repair_count = diags.get("repair_count")
    assert repair_attempted is False or repair_attempted is None
    assert int(repair_count or 0) == 0
    assert (
        contract.get("dto_validation_status") == "SUCCESS"
        or diags.get("dto_mapper_status") in {"mapped", "SUCCESS", "success"}
        or diags.get("dto_validation_status") == "SUCCESS"
    )
    assert int(diags.get("semantic_claim_count") or diags.get("private_candidate_count") or 0) >= 1
    assert int(diags.get("evidence_valid_count") or diags.get("evidence_written_count") or 0) >= 1
    assert diags.get("transaction_committed") is True or (
        env["executor"].get_module_results(run_id)[0]
        .get("persistence_summary", {})
        .get("persistence_complete")
        is True
    )

    session: Session = env["session"]
    counts = _orm_counts(session)
    assert counts["assets"] >= 1
    assert counts["versions"] >= 1
    assert counts["evidence"] >= 1
    assert counts["artifacts"] >= 1
    assert counts["model_invocations"] == 0

    client: TestClient = env["client"]
    result_resp = client.get(f"/api/v1/whole-book-runs/{run_id}/results/book_overview")
    assert result_resp.status_code == 200, result_resp.text
    result_body = result_resp.json()
    assert str(result_body.get("module_status") or "").lower() == "completed"
    assert list(result_body.get("asset_ids") or [])
    assert int(result_body.get("evidence_count") or 0) > 0
    _assert_no_sensitive(json.dumps(result_body, ensure_ascii=False))

    safe_counters = {
        "fake_http_calls": len(fake.calls),
        "repair_count": int(repair_count or 0),
        "assets": counts["assets"],
        "versions": counts["versions"],
        "evidence": counts["evidence"],
        "artifacts": counts["artifacts"],
        "model_invocations": counts["model_invocations"],
        "result_evidence_count": int(result_body.get("evidence_count") or 0),
    }
    assert safe_counters["fake_http_calls"] == 1
    assert safe_counters["model_invocations"] == 0


@pytest.mark.skip(reason="Legacy Private Lab replay was superseded by formal Whole-Book V2 execution-context binding")
def test_ac_router_create_scenario_b_envelope_one_repair(product_env) -> None:
    env = product_env
    bad = _invalid_envelope_dto(env)
    good = _synthetic_dto(env)
    _configure_fake_http(
        env,
        stub_texts=[
            json.dumps(bad, ensure_ascii=False),
            json.dumps(good, ensure_ascii=False),
        ],
        request_ids=["fake-http-invalid-1", "fake-http-repair-1"],
        input_tokens=90,
        output_tokens=45,
    )

    _pre, _est, create, exec_result = _create_and_start(env, idem="ac-b-onerepair")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() in {"completed", "complete"}

    fake: FakeHttpProviderTransport = env["fake_http"]
    assert len(fake.calls) == 2
    call_ids = [str(c.get("request_id")) for c in fake.calls]
    assert call_ids == ["fake-http-invalid-1", "fake-http-repair-1"]

    usage = _module_result_usage(env, run_id)
    contract = dict(usage.get("output_contract") or {})
    assert (
        contract.get("initial_contract_failure_code") == FAILURE_UNDECLARED_TOP_LEVEL
        or FAILURE_UNDECLARED_TOP_LEVEL in json.dumps(contract, ensure_ascii=False)
    )
    assert int(contract.get("repair_count") or usage.get("retry_count") or 0) == 1

    ids = list(usage.get("provider_request_ids") or [])
    attempts = list(usage.get("attempts") or [])
    cp = _provider_attempt_payload(env["session"], run_id)
    if cp:
        ids = ids or list(cp.get("provider_request_ids") or [])
        attempts = attempts or list(cp.get("attempts") or [])
    assert len(ids) == 2 or len(attempts) == 2 or len(set(call_ids)) == 2
    if len(ids) >= 2:
        assert ids[0] != ids[1]

    expected_in = 90 * 2
    expected_out = 45 * 2
    assert int(usage.get("input_tokens") or 0) == expected_in
    assert int(usage.get("output_tokens") or 0) == expected_out
    stage_tokens_in = sum(
        int(s.token_input or 0)
        for s in env["session"].scalars(
            select(AnalysisRunStage).where(AnalysisRunStage.run_id == run_id)
        ).all()
    )
    assert stage_tokens_in >= expected_in

    counts = _orm_counts(env["session"])
    assert counts["assets"] >= 1
    assert counts["evidence"] >= 1
    assert counts["model_invocations"] == 0

    result_resp = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results/book_overview")
    assert result_resp.status_code == 200
    result_body = result_resp.json()
    assert str(result_body.get("module_status") or "").lower() == "completed"
    # Repair visible safely if projected — counters only, no bodies.
    if "repair_count" in result_body or "repair" in json.dumps(result_body).lower():
        assert "evidence_map" not in json.dumps(result_body).lower()
    _assert_no_sensitive(json.dumps(result_body, ensure_ascii=False))


@pytest.mark.skip(reason="Legacy Private Lab replay was superseded by formal Whole-Book V2 execution-context binding")
def test_ac_router_create_scenario_c_repair_still_fails(product_env) -> None:
    env = product_env
    bad = _invalid_envelope_dto(env)
    _configure_fake_http(
        env,
        stub_texts=[
            json.dumps(bad, ensure_ascii=False),
            json.dumps(bad, ensure_ascii=False),
        ],
        request_ids=["fake-http-invalid-1", "fake-http-invalid-2"],
        input_tokens=90,
        output_tokens=45,
    )

    _pre, _est, create, exec_result = _create_and_start(env, idem="ac-c-repairfail")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    assert len(env["fake_http"].calls) == 2

    session: Session = env["session"]
    run = session.get(AnalysisRun, run_id)
    assert run is not None
    assert str(run.status).lower() == "failed"

    stages = list(
        session.scalars(select(AnalysisRunStage).where(AnalysisRunStage.run_id == run_id)).all()
    )
    producer = next(s for s in stages if s.stage_key == "analyze_structure")
    assert StageStatus(producer.status) == StageStatus.FAILED

    cp = _provider_attempt_payload(session, run_id)
    assert cp.get("checkpoint_kind") == "provider_attempt"
    ids = list(cp.get("provider_request_ids") or [])
    attempts = list(cp.get("attempts") or [])
    assert len(ids) == 2 or len(attempts) == 2
    if len(ids) >= 2:
        assert len(set(ids)) == 2

    counts = _orm_counts(session)
    assert counts["assets"] == 0
    assert counts["versions"] == 0
    assert counts["evidence"] == 0
    assert counts["model_invocations"] == 0

    result_resp = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results")
    assert result_resp.status_code == 200
    result_json = result_resp.json()
    _assert_fail_closed(session, run_id, result_json)

    # persistence / transaction not committed for success path
    diags = _pipeline_diags(env, run_id)
    if diags:
        assert diags.get("transaction_committed") is not True
        assert diags.get("persistence_complete") is not True


# ---------------------------------------------------------------------------
# Estimate / fingerprint / authority
# ---------------------------------------------------------------------------


def test_ac_estimate_http_exposes_repair_budget(product_env) -> None:
    env = product_env
    client: TestClient = env["client"]
    cfg = "cfg-ac-estimate-budget"
    pre = client.post(
        "/api/v1/labs/private-whole-book-runs/preflight",
        headers=MARKER,
        json={
            "book_id": env["book"].id,
            "book_snapshot_id": env["snapshot"].id,
            "configuration_fingerprint": cfg,
            "requested_modules": ["book_overview"],
        },
    )
    assert pre.status_code == 200, pre.text
    est = client.post(
        "/api/v1/labs/private-whole-book-runs/estimate",
        headers=MARKER,
        json={
            "book_id": env["book"].id,
            "book_snapshot_id": env["snapshot"].id,
            "configuration_fingerprint": cfg,
            "preflight_fingerprint": pre.json()["fingerprint"],
            "requested_modules": ["book_overview"],
        },
    )
    assert est.status_code == 200, est.text
    body = est.json()

    required = (
        "repair_policy",
        "repair_policy_version",
        "max_repair_count",
        "expected_no_repair_cost",
        "max_one_repair_cost",
        "max_total_authorized_cost",
        "estimated_input_tokens",
        "estimated_output_tokens",
        "estimated_total_tokens",
        "pricing_version",
    )
    for key in required:
        assert key in body, f"missing repair budget field: {key}"
        assert body[key] is not None, f"null repair budget field: {key}"

    assert body["repair_policy_version"]
    assert int(body["max_repair_count"]) >= 1
    assert float(body["max_total_authorized_cost"]) >= float(body["expected_no_repair_cost"])
    assert body["max_one_repair_cost"] is not None
    assert int(body["estimated_input_tokens"]) > 0
    assert int(body["estimated_total_tokens"]) > 0

    dump = json.dumps(body, ensure_ascii=False).lower()
    for banned in (
        '"prompt"',
        '"credential"',
        '"api_key"',
        "evidence_map",
        "合成段落甲",
        '"messages"',
        "system_instruction",
    ):
        assert banned not in dump
    assert len(env["fake_http"].calls) == 0


def test_ac_repair_budget_fingerprint_and_stale_reject(product_env) -> None:
    env = product_env
    client: TestClient = env["client"]

    def _estimate_only(idem: str) -> tuple[Any, Any]:
        cfg = f"cfg-ac-{idem}"
        pre = client.post(
            "/api/v1/labs/private-whole-book-runs/preflight",
            headers=MARKER,
            json={
                "book_id": env["book"].id,
                "book_snapshot_id": env["snapshot"].id,
                "configuration_fingerprint": cfg,
                "requested_modules": ["book_overview"],
            },
        )
        assert pre.status_code == 200, pre.text
        est = client.post(
            "/api/v1/labs/private-whole-book-runs/estimate",
            headers=MARKER,
            json={
                "book_id": env["book"].id,
                "book_snapshot_id": env["snapshot"].id,
                "configuration_fingerprint": cfg,
                "preflight_fingerprint": pre.json()["fingerprint"],
                "requested_modules": ["book_overview"],
            },
        )
        assert est.status_code == 200, est.text
        return pre, est

    _pre1, est1 = _estimate_only("ac-fp-1")
    _pre2, est2 = _estimate_only("ac-fp-2")
    fp1 = est1.json()["fingerprint"]
    fp2 = est2.json()["fingerprint"]
    assert fp1 and fp2

    a = estimate_fingerprint_for(
        request_id="ac-fp",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        module_key="book_overview",
        estimated_input_tokens=100,
        estimated_output_tokens=50,
        pricing_version="v1",
        estimate_method="generic_v1",
        output_policy_version="1",
        repair_policy_version="1.0.0",
        max_repair_count=1,
    )
    b = estimate_fingerprint_for(
        request_id="ac-fp",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        module_key="book_overview",
        estimated_input_tokens=100,
        estimated_output_tokens=50,
        pricing_version="v1",
        estimate_method="generic_v1",
        output_policy_version="1",
        repair_policy_version="9.9.9",
        max_repair_count=1,
    )
    assert a != b

    before = len(env["session"].scalars(select(AnalysisRun)).all())
    _pre, est, create = _http_flow(
        client,
        env,
        idem="ac-fp-stale",
        dry_run=False,
        auto_start=False,
        estimate_fingerprint_override="stale-estimate-fingerprint-not-real",
    )
    assert est.status_code == 200
    assert 400 <= create.status_code < 500
    assert len(env["session"].scalars(select(AnalysisRun)).all()) == before


@pytest.mark.skip(reason="Legacy Private Lab replay was superseded by formal Whole-Book V2 execution-context binding")
def test_ac_model_invocation_authority_is_stage_provider_attempt(product_env) -> None:
    """Document authority: Stage provider_attempt is Lab Live ledger; MI stays 0."""

    assert AUTHORITY == STAGE_PROVIDER_ATTEMPT_IS_AUTHORITATIVE
    assert STAGE_PROVIDER_ATTEMPT_IS_AUTHORITATIVE == "STAGE_PROVIDER_ATTEMPT_IS_AUTHORITATIVE"

    env = product_env
    # Failure-after-calls retains provider_attempt checkpoint_kind.
    bad = _invalid_envelope_dto(env)
    _configure_fake_http(
        env,
        stub_texts=[json.dumps(bad), json.dumps(bad)],
        request_ids=["auth-fail-1", "auth-fail-2"],
    )
    _pre, _est, create, exec_result = _create_and_start(env, idem="ac-auth-fail")
    run_fail = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    cp = _provider_attempt_payload(env["session"], run_fail)
    assert cp.get("checkpoint_kind") == "provider_attempt"
    assert _orm_counts(env["session"])["model_invocations"] == 0

    # Scenario-A-like success: model_invocations remains 0; FakeHttp is the call surface.
    dto = _synthetic_dto(env)
    _configure_fake_http(
        env,
        stub_texts=[json.dumps(dto, ensure_ascii=False)],
        request_ids=["auth-ok-1"],
    )
    _p, _e, create_ok, exec_ok = _create_and_start(env, idem="ac-auth-ok")
    run_ok = int(create_ok.json().get("run_id") or create_ok.json().get("lab_run_id"))
    assert exec_ok.status.lower() in {"completed", "complete"}
    assert len(env["fake_http"].calls) == 1
    usage = _module_result_usage(env, run_ok)
    assert usage.get("provider_request_id") or usage.get("provider_attempted")
    assert _orm_counts(env["session"])["model_invocations"] == 0


# ---------------------------------------------------------------------------
# Failure equivalence classes (F1–F8)
# ---------------------------------------------------------------------------


def test_f1_http_parse_non_json_fail_closed(product_env) -> None:
    env = product_env
    _configure_fake_http(
        env,
        stub_texts=["not-json{{"],
        request_ids=["fake-http-nonjson-1", "fake-http-nonjson-2"],
    )
    _pre, _est, create, exec_result = _create_and_start(env, idem="ac-f1-nonjson")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    assert len(env["fake_http"].calls) <= 2
    result_json = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results").json()
    _assert_fail_closed(env["session"], run_id, result_json)


def test_f2_contract_wrapper_fail_closed(product_env) -> None:
    """Dedicated wrapper failure — same fail-closed invariants as scenario C."""

    env = product_env
    bad = _invalid_envelope_dto(env)
    _configure_fake_http(
        env,
        stub_texts=[json.dumps(bad), json.dumps(bad)],
        request_ids=["f2-bad-1", "f2-bad-2"],
    )
    _pre, _est, create, exec_result = _create_and_start(env, idem="ac-f2-wrapper")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    assert len(env["fake_http"].calls) == 2
    result_json = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results").json()
    _assert_fail_closed(env["session"], run_id, result_json)
    cp = _provider_attempt_payload(env["session"], run_id)
    assert cp.get("checkpoint_kind") == "provider_attempt"


def test_f3_empty_semantic_fail_closed(product_env) -> None:
    env = product_env
    empty = _synthetic_dto(
        env,
        logline="",
        premise="",
        central_question="",
        primary_conflict="",
        structure_summary="",
        ending_state="",
    )
    _configure_fake_http(
        env,
        stub_texts=[json.dumps(empty), json.dumps(empty)],
        request_ids=["f3-empty-1", "f3-empty-2"],
    )
    _pre, _est, create, exec_result = _create_and_start(env, idem="ac-f3-empty")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    result_json = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results").json()
    _assert_fail_closed(env["session"], run_id, result_json)


def test_f4_unknown_evidence_fail_closed(product_env) -> None:
    env = product_env
    dto = _synthetic_dto(
        env,
        evidence_refs=[
            {
                "evidence_id": "unknown-evidence-id-999999",
                "evidence_role": "support",
                "target_output_ref": "book_overview.claim",
            }
        ],
    )
    _configure_fake_http(
        env,
        stub_texts=[json.dumps(dto, ensure_ascii=False)],
        request_ids=["f4-unknown-ev"],
    )
    _pre, _est, create, exec_result = _create_and_start(env, idem="ac-f4-unknown-ev")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    result_json = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results").json()
    _assert_fail_closed(env["session"], run_id, result_json)


def test_f5_fiction_reference_fail_closed(product_env) -> None:
    env = product_env
    dto = _synthetic_dto(env, protagonist_asset_id="fake-asset-999")
    _configure_fake_http(
        env,
        stub_texts=[json.dumps(dto, ensure_ascii=False), json.dumps(dto, ensure_ascii=False)],
        request_ids=["f5-fiction-1", "f5-fiction-2"],
    )
    _pre, _est, create, exec_result = _create_and_start(env, idem="ac-f5-fiction")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    result_json = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results").json()
    _assert_fail_closed(env["session"], run_id, result_json)


def test_f6_empty_candidates_fail_closed(product_env) -> None:
    env = product_env
    dto = _synthetic_dto(env, evidence_refs=[])
    _configure_fake_http(
        env,
        stub_texts=[json.dumps(dto, ensure_ascii=False), json.dumps(dto, ensure_ascii=False)],
        request_ids=["f6-empty-cand-1", "f6-empty-cand-2"],
    )
    _pre, _est, create, exec_result = _create_and_start(env, idem="ac-f6-empty-cand")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    result_json = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results").json()
    _assert_fail_closed(env["session"], run_id, result_json)


def test_f7_persistence_fail_closed(product_env) -> None:
    """F7-adjacent: unknown evidence rejects before ORM write (no redesign)."""

    env = product_env
    dto = _synthetic_dto(
        env,
        evidence_refs=[
            {
                "evidence_id": "persist-reject-unknown-ev",
                "evidence_role": "support",
                "target_output_ref": "book_overview.claim",
            }
        ],
    )
    _configure_fake_http(
        env,
        stub_texts=[json.dumps(dto, ensure_ascii=False)],
        request_ids=["f7-persist"],
    )
    _pre, _est, create, exec_result = _create_and_start(env, idem="ac-f7-persist")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    counts = _orm_counts(env["session"])
    assert counts["assets"] == 0
    assert counts["versions"] == 0
    assert counts["evidence"] == 0
    result_json = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results").json()
    _assert_fail_closed(env["session"], run_id, result_json)


def test_f8_usage_budget_path(product_env) -> None:
    """Repair budget fields present on estimate; create rejects bad fingerprint."""

    env = product_env
    client: TestClient = env["client"]
    pre = client.post(
        "/api/v1/labs/private-whole-book-runs/preflight",
        headers=MARKER,
        json={
            "book_id": env["book"].id,
            "book_snapshot_id": env["snapshot"].id,
            "configuration_fingerprint": "cfg-ac-f8",
            "requested_modules": ["book_overview"],
        },
    )
    assert pre.status_code == 200
    est = client.post(
        "/api/v1/labs/private-whole-book-runs/estimate",
        headers=MARKER,
        json={
            "book_id": env["book"].id,
            "book_snapshot_id": env["snapshot"].id,
            "configuration_fingerprint": "cfg-ac-f8",
            "preflight_fingerprint": pre.json()["fingerprint"],
            "requested_modules": ["book_overview"],
        },
    )
    assert est.status_code == 200
    body = est.json()
    assert body.get("max_total_authorized_cost") is not None
    assert body.get("max_one_repair_cost") is not None
    assert body.get("repair_policy_version") is not None

    create = client.post(
        "/api/v1/labs/private-whole-book-runs",
        headers=MARKER,
        json={
            "book_id": env["book"].id,
            "book_snapshot_id": env["snapshot"].id,
            "idempotency_key": "ac-f8-bad-fp",
            "configuration_fingerprint": "cfg-ac-f8",
            "requested_modules": ["book_overview"],
            "preflight_fingerprint": pre.json()["fingerprint"],
            "estimate_fingerprint": "definitely-wrong-estimate-fp",
            "consent_fingerprint": body["consent_fingerprint"],
            "data_transfer_manifest_hash": body["data_transfer_manifest_hash"],
            "auto_start": False,
            "dry_run": False,
            "user_confirmed": True,
        },
    )
    assert create.status_code == 400


def test_ac_offset_invalid_cross_ref_and_quote_index(product_env) -> None:
    """Product-boundary note: OFFSET_INVALID covered by SnapshotQuoteIndex + existing unit test.

    Cross-ref: test_narrative_phase2br1_live_persistence_boundary.test_offset_invalid_rejected
    """

    env = product_env
    from pathlib import Path

    unit_path = Path(__file__).with_name(
        "test_narrative_phase2br1_live_persistence_boundary.py"
    )
    assert unit_path.is_file()
    assert "def test_offset_invalid_rejected" in unit_path.read_text(encoding="utf-8")
    idx = SnapshotQuoteIndex.build_from_session(
        env["session"], book_snapshot_id=int(env["snapshot"].id)
    )
    sp = env["paragraph"]
    bad = idx.resolve(
        evidence_key=str(sp.id),
        expected_snapshot_id=int(env["snapshot"].id),
        start_offset=0,
        end_offset=99999,
    )
    assert bad.failure_code == "OFFSET_INVALID"
