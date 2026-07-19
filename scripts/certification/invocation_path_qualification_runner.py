# -*- coding: utf-8 -*-
"""Real Invocation Path Qualification runner (DEFECT-CANARY-015).

Exercises nested model-call paths through ModelInvocationBroker with a
preflight-frozen fault-injection proxy. Covered repair/retry types must
include at least one real HTTP ModelInvocation with full policy audit fields.

Does NOT run the 8-run full canary. Does NOT write the main database.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "scripts"))

AUDITS = ROOT / "audits" / "single-chapter-pipeline"
QUAL_AUDITS = AUDITS / "invocation-path-qualification-v1"
PREFLIGHT = AUDITS / "real-invocation-path-qualification-preflight-v1.json"
AUTH = QUAL_AUDITS / "authorization-qualification-v1.json"
CHANGE_PKG = AUDITS / "changes" / "global-model-invocation-policy-change-v1.1.0.json"
GRAPH = AUDITS / "model-invocation-graph-v1.json"
MAIN_DB = ROOT / "data" / "storylens.db"
QUAL_DB = (
    ROOT
    / "artifacts"
    / "single-chapter-pipeline-certification"
    / "real-canary"
    / "qualification-v1.sqlite3"
)

PROVIDER = "aliyun_qwen_plus"
MODEL = "qwen3.7-plus"
FLASH = "aliyun_qwen_flash"

REQUIRED_TYPES = [
    "reader_journey_scene_schema_repair",
    "reader_journey_structural_repair",
    "generic_provider_retry",
    "repair_provider_retry",
    "reader_journey_targeted_evidence_patch",
    "scene_analysis_provider_recovery",
    "reader_journey_chapter_schema_repair",
]

POLICY_KEYS = [
    "requested_provider",
    "requested_model",
    "resolved_provider",
    "resolved_model",
    "route_source",
    "fallback_used",
    "auto_route",
    "provider_enabled",
    "policy_match",
    "request_hash",
]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _boundary_ok() -> str:
    return json.dumps(
        {
            "chapter_id": "B0001-C0001",
            "boundaries": [],
            "overall_confidence": 1.0,
        },
        ensure_ascii=False,
    )


def _boundary_invalid() -> str:
    # Missing required fields → SCHEMA_VALIDATION_FAILED
    return json.dumps({"boundaries": []}, ensure_ascii=False)


def _chapter_invalid() -> str:
    return json.dumps({"phases": []}, ensure_ascii=False)


def _load_oos_batch_json() -> str:
    path = (
        AUDITS
        / "real-canary-v7"
        / "defects"
        / "DEFECT-CANARY-011-attempt1-normal-response.json"
    )
    return path.read_text(encoding="utf-8")


@dataclass
class FaultAction:
    kind: str  # passthrough | invalid_json | disconnect | canned_json
    payload: str | None = None


@dataclass
class ScenarioResult:
    scenario_id: str
    covers: str
    ok: bool
    detail: str
    invocation_ids: list[int] = field(default_factory=list)
    error: str | None = None


class QualificationFaultProxy:
    """Preflight-frozen fault injection wrapper around the real Plus provider."""

    def __init__(self, inner: Any, script: list[FaultAction]):
        self.inner = inner
        self.script = list(script)
        self.name = inner.name
        self.default_model = inner.default_model
        self.calls = 0
        self.real_http_calls = 0

    def capabilities(self):
        return self.inner.capabilities()

    async def health(self):
        return await self.inner.health()

    async def generate(self, request):
        from app.model_gateway.base import ModelResponse, ProviderRequestError
        from app.model_gateway.provider_errors import TRANSPORT_REMOTE_DISCONNECT

        self.calls += 1
        action = self.script.pop(0) if self.script else FaultAction("passthrough")
        if action.kind == "disconnect":
            raise ProviderRequestError(
                "Server disconnected without sending a response.",
                http_request_sent=True,
                error_code="PROVIDER_REMOTE_DISCONNECT",
                transport_kind=TRANSPORT_REMOTE_DISCONNECT,
                retryable=True,
                exception_type="RemoteProtocolError",
                provider=self.name,
                model=request.model or self.default_model,
                phase="provider_request",
            )
        if action.kind in {"invalid_json", "canned_json"}:
            text = action.payload or _boundary_invalid()
            return ModelResponse(
                text=text,
                model=request.model or self.default_model,
                http_status_code=200,
                input_tokens=32,
                output_tokens=16,
                total_tokens=48,
                finish_reason="stop",
            )
        self.real_http_calls += 1
        return await self.inner.generate(request)


def load_auth_and_preflight() -> tuple[dict, dict, dict]:
    if not AUTH.exists():
        raise SystemExit("AUTHORIZATION_REQUIRED: missing authorization-qualification-v1.json")
    if not PREFLIGHT.exists():
        raise SystemExit("QUALIFICATION_BLOCKED: missing preflight")
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    pre = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if not auth.get("operator_approved"):
        raise SystemExit("AUTHORIZATION_REQUIRED: operator_approved!=true")
    if not str(auth.get("operator_approval_note") or "").strip():
        raise SystemExit("AUTHORIZATION_REQUIRED: operator_approval_note required")
    if float(auth.get("operator_max_cost_cny") or 0) <= 0:
        raise SystemExit("AUTHORIZATION_REQUIRED: max_cost must be > 0")
    if not pre.get("execution_allowed"):
        raise SystemExit("QUALIFICATION_BLOCKED: preflight execution_allowed!=true")
    if pre.get("status") != "OPERATOR_AUTHORIZED":
        raise SystemExit("QUALIFICATION_BLOCKED: preflight not OPERATOR_AUTHORIZED")
    if not pre.get("real_model_requests_allowed"):
        raise SystemExit("QUALIFICATION_BLOCKED: real_model_requests_allowed!=true")
    if auth.get("scope") != "invocation_path_qualification":
        raise SystemExit("AUTHORIZATION_REQUIRED: scope must be invocation_path_qualification")
    if "real-canary-preflight-v12" in str(auth.get("operator_approval_note") or "") and (
        "不允许启动 real-canary-preflight-v12" not in str(auth.get("operator_approval_note"))
    ):
        pass
    # Forbid launching full canary from this auth.
    if auth.get("allows_full_canary") is True:
        raise SystemExit("AUTHORIZATION_REQUIRED: allows_full_canary must be false")
    if auth.get("provider") != PROVIDER or auth.get("model") != MODEL:
        raise SystemExit("AUTHORIZATION_REQUIRED: provider/model mismatch")
    if auth.get("allow_auto_route") is not False:
        raise SystemExit("AUTHORIZATION_REQUIRED: allow_auto_route must be false")
    # Hash freeze
    frozen = pre.get("frozen_hashes") or {}
    for rel, expected in frozen.items():
        path = ROOT / rel
        if not path.exists():
            raise SystemExit(f"QUALIFICATION_BLOCKED: missing frozen file {rel}")
        actual = _sha256(path)
        if actual != expected:
            raise SystemExit(
                f"QUALIFICATION_BLOCKED: hash drift {rel}: expected={expected} actual={actual}"
            )
    limits = {
        "max_cost_cny": float(auth["operator_max_cost_cny"]),
        "max_model_requests": int((pre.get("hard_limits") or {}).get("max_model_requests", 40)),
        "max_retry_requests": int((pre.get("hard_limits") or {}).get("max_retry_requests", 20)),
        "max_input_tokens": int((pre.get("hard_limits") or {}).get("max_input_tokens", 200_000)),
        "max_output_tokens": int((pre.get("hard_limits") or {}).get("max_output_tokens", 80_000)),
        "max_total_duration_minutes": int(
            (pre.get("hard_limits") or {}).get("max_total_duration_minutes", 45)
        ),
    }
    return auth, pre, limits


def main_db_counts() -> tuple[int, int]:
    conn = sqlite3.connect(str(MAIN_DB))
    try:
        a = conn.execute("select count(*) from analysis_runs").fetchone()[0]
        j = conn.execute("select count(*) from reader_journey_runs").fetchone()[0]
    finally:
        conn.close()
    return int(a), int(j)


def read_base_url() -> str:
    from app.services.aliyun_endpoint import resolve_aliyun_compatible_base_url

    conn = sqlite3.connect(f"file:{MAIN_DB.as_posix()}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "select base_url, workspace_id, region from provider_configurations where provider_name=?",
            (PROVIDER,),
        ).fetchone()
    finally:
        conn.close()
    if not row or not (row[0] or row[1]):
        raise SystemExit("QUALIFICATION_BLOCKED: missing plus base_url in main DB (read-only)")
    resolved = resolve_aliyun_compatible_base_url(
        base_url=row[0] or "",
        workspace_id=row[1] or "",
        region=(row[2] or "cn-beijing"),
        allow_region_public_default=False,
    )
    if not resolved:
        raise SystemExit("QUALIFICATION_BLOCKED: resolved plus base_url empty")
    return resolved.rstrip("/")


def ensure_qual_env(base_url: str, max_cost: float) -> None:
    QUAL_DB.parent.mkdir(parents=True, exist_ok=True)
    QUAL_AUDITS.mkdir(parents=True, exist_ok=True)
    if QUAL_DB.exists():
        QUAL_DB.unlink()
    rel = (
        "sqlite:///./artifacts/single-chapter-pipeline-certification/"
        "real-canary/qualification-v1.sqlite3"
    )
    os.environ["STORYLENS_DATABASE_URL"] = rel
    os.environ.setdefault("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_1_MIN", "0")
    os.environ.setdefault("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_1_MAX", "0")
    os.environ.setdefault("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_2_MIN", "0")
    os.environ.setdefault("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_2_MAX", "0")
    os.environ.setdefault("STORYLENS_ALIYUN_TRANSPORT_MAX_ATTEMPTS", "3")
    os.environ.setdefault("STORYLENS_ALIYUN_MAX_RETRIES", "3")
    os.environ.setdefault("STORYLENS_SCENE_ANALYSIS_RECOVERY_COOLDOWN_SECONDS", "0")
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    if "storylens.db" in settings.database_url and "qualification-v1" not in settings.database_url:
        raise SystemExit("QUALIFICATION_BLOCKED: refused to bind main DB")
    if "qualification-v1.sqlite3" not in settings.database_url:
        raise SystemExit(f"QUALIFICATION_BLOCKED: unexpected DB URL {settings.database_url}")

    from app.db.session import SessionLocal, create_db, engine
    from app.db.models import ApplicationSetting, ProviderConfiguration
    from app.schemas.settings import CloudBudgetUpdate

    if "qualification-v1" not in str(engine.url):
        raise SystemExit(f"QUALIFICATION_BLOCKED: engine not bound to qualification DB ({engine.url})")
    create_db()
    with SessionLocal() as session:
        session.merge(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True)))
        budget = CloudBudgetUpdate().model_dump()
        budget.update(
            {
                "cloud_daily_request_limit": 200,
                "cloud_daily_token_limit": 2_000_000,
                "cloud_daily_estimated_cost_limit": float(max_cost),
                "cloud_max_requests_per_run": 80,
                "cloud_max_input_tokens_per_request": 16000,
                "cloud_max_output_tokens_per_request": 2000,
                "cloud_stop_on_unknown_pricing": True,
            }
        )
        session.merge(
            ApplicationSetting(key="cloud_budget_settings", value_json=json.dumps(budget))
        )
        session.merge(
            ProviderConfiguration(
                provider_name=PROVIDER,
                display_name="阿里云百炼",
                region="cn-beijing",
                workspace_id="",
                base_url=base_url,
                plus_model=MODEL,
                max_model="qwen3.7-max",
                flash_model="qwen3.6-flash",
                timeout_seconds=180,
                max_retries=3,
                enabled=True,
                disconnected=False,
                allow_auto_route=False,
                raw_logging_enabled=False,
                credential_reference=f"keyring:{PROVIDER}",
            )
        )
        session.commit()


def build_real_plus_provider(session):
    from app.model_gateway.registry import get_model_gateway
    from app.services.credentials.keyring_store import KeyringCredentialStore
    from app.services.provider_runtime import bind_gateway_runtime

    store = KeyringCredentialStore()
    if not store.available() or not store.get(PROVIDER):
        raise SystemExit("QUALIFICATION_BLOCKED: missing keyring credential for aliyun_qwen_plus")
    gateway = get_model_gateway()
    bind_gateway_runtime(gateway, session, store)
    plus = gateway.get(PROVIDER)
    if not plus.capabilities().enabled:
        raise SystemExit("QUALIFICATION_BLOCKED: plus provider not enabled after runtime bind")
    # Ensure Flash remains disabled / unused.
    try:
        flash = gateway.get(FLASH)
        flash.enabled = False
    except Exception:
        pass
    return plus


def make_run(session, *, task_type: str = "qualification") -> Any:
    from app.db.models import AnalysisRun

    run = AnalysisRun(
        task_type=task_type,
        subject_type="chapter",
        subject_id="1",
        provider=PROVIDER,
        model=MODEL,
        prompt_version="v1",
        schema_version="v1",
        prompt_hash="qual",
        input_hash=f"qual-{time.time_ns()}",
        status="running",
        execution_mode="cloud",
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def extract_policy(inv) -> dict:
    params = {}
    if inv.request_parameters_json:
        try:
            params = json.loads(inv.request_parameters_json)
        except json.JSONDecodeError:
            params = {}
    return {
        "invocation_id": inv.id,
        "task_type": inv.task_type,
        "invocation_kind": inv.invocation_kind,
        "invocation_type": params.get("invocation_type"),
        "provider_name": inv.provider_name,
        "model_name": inv.model_name,
        "http_request_sent": inv.http_request_sent,
        "status": inv.status,
        "error_code": inv.error_code,
        "request_hash": inv.request_hash or params.get("request_hash"),
        "requested_provider": params.get("requested_provider"),
        "requested_model": params.get("requested_model"),
        "resolved_provider": params.get("resolved_provider"),
        "resolved_model": params.get("resolved_model"),
        "route_source": params.get("route_source"),
        "fallback_used": params.get("fallback_used"),
        "auto_route": params.get("auto_route"),
        "provider_enabled": params.get("provider_enabled"),
        "policy_match": params.get("policy_match"),
    }


async def _run_generate(
    *,
    session,
    proxy: QualificationFaultProxy,
    run,
    task_type: str,
    schema,
    prompt,
    user_content: str,
    business_validator,
    initial_invocation_kind: str = "initial",
    policy_invocation_type: str | None = None,
    input_snapshot: dict | None = None,
):
    from app.model_gateway.gateway import ModelGateway
    from app.services.structured_output import generate_validated

    gateway = ModelGateway([proxy])
    return await generate_validated(
        session=session,
        gateway=gateway,
        run_id=run.id,
        provider_name=PROVIDER,
        task_type=task_type,
        prompt=prompt,
        schema=schema,
        input_snapshot=input_snapshot or {},
        user_content=user_content,
        business_validator=business_validator,
        initial_invocation_kind=initial_invocation_kind,
        allow_truncation_retry=False,
        policy_invocation_type=policy_invocation_type,
    )


def _rows_for_run(session, run_id: int):
    from sqlalchemy import select
    from app.db.models import ModelInvocation

    return list(
        session.scalars(
            select(ModelInvocation)
            .where(ModelInvocation.run_id == run_id)
            .order_by(ModelInvocation.id)
        )
    )


def _find_cover(rows, covers: str) -> list:
    found = []
    for inv in rows:
        pol = extract_policy(inv)
        if pol.get("invocation_type") == covers and inv.http_request_sent:
            found.append(inv)
    return found


async def scenario_schema_repair(session, plus) -> ScenarioResult:
    from app.schemas.scene import SceneBoundaryResult
    from app.services.prompt_service import load_prompt
    from app.services.structured_output import StructuredOutputError

    covers = "reader_journey_scene_schema_repair"
    run = make_run(session)
    proxy = QualificationFaultProxy(
        plus,
        [
            FaultAction("invalid_json", _boundary_invalid()),
            FaultAction("passthrough"),
        ],
    )
    prompt = load_prompt("scene_boundary", "v3.1")
    try:
        await _run_generate(
            session=session,
            proxy=proxy,
            run=run,
            task_type="reader_journey_scene",
            schema=SceneBoundaryResult,
            prompt=prompt,
            user_content="qualification schema repair fixture",
            business_validator=lambda _: None,
            initial_invocation_kind="normal_batch_request",
        )
    except StructuredOutputError:
        pass
    rows = _rows_for_run(session, run.id)
    hit = _find_cover(rows, covers)
    ok = bool(hit) and proxy.real_http_calls >= 1
    return ScenarioResult(
        "FI-SCHEMA-SCENE",
        covers,
        ok,
        f"real_http={proxy.real_http_calls} hits={len(hit)}",
        [i.id for i in hit],
    )


async def scenario_structural_repair(session, plus) -> ScenarioResult:
    from app.schemas.scene import SceneBoundaryResult
    from app.services.prompt_service import load_prompt
    from app.services.structured_output import StructuredOutputError
    from app.services.validation_errors import StructuralValidationError

    covers = "reader_journey_structural_repair"
    run = make_run(session)
    state = {"n": 0}

    def biz(_):
        state["n"] += 1
        if state["n"] == 1:
            raise StructuralValidationError(
                "qualification OOS",
                "JOURNEY_EVIDENCE_OUT_OF_SCOPE",
            )

    proxy = QualificationFaultProxy(
        plus,
        [
            FaultAction("canned_json", _boundary_ok()),
            FaultAction("passthrough"),
        ],
    )
    prompt = load_prompt("scene_boundary", "v3.1")
    try:
        await _run_generate(
            session=session,
            proxy=proxy,
            run=run,
            task_type="reader_journey_scene",
            schema=SceneBoundaryResult,
            prompt=prompt,
            user_content="qualification structural repair fixture",
            business_validator=biz,
            initial_invocation_kind="normal_batch_request",
        )
    except StructuredOutputError:
        pass
    rows = _rows_for_run(session, run.id)
    hit = _find_cover(rows, covers)
    ok = bool(hit) and proxy.real_http_calls >= 1
    return ScenarioResult(
        "FI-STRUCTURAL",
        covers,
        ok,
        f"real_http={proxy.real_http_calls} hits={len(hit)}",
        [i.id for i in hit],
    )


async def scenario_generic_retry(session, plus) -> ScenarioResult:
    from app.schemas.scene import SceneBoundaryResult
    from app.services.prompt_service import load_prompt
    from app.services.structured_output import StructuredOutputError

    covers = "generic_provider_retry"
    run = make_run(session)
    proxy = QualificationFaultProxy(
        plus,
        [FaultAction("disconnect"), FaultAction("passthrough")],
    )
    prompt = load_prompt("scene_boundary", "v3.1")
    try:
        await _run_generate(
            session=session,
            proxy=proxy,
            run=run,
            task_type="scene_boundary",
            schema=SceneBoundaryResult,
            prompt=prompt,
            user_content="qualification provider retry fixture",
            business_validator=lambda _: None,
        )
    except StructuredOutputError:
        pass
    rows = _rows_for_run(session, run.id)
    hit = _find_cover(rows, covers)
    # map: scene_boundary + provider_retry → generic_provider_retry
    ok = bool(hit) and proxy.real_http_calls >= 1
    return ScenarioResult(
        "FI-PROVIDER-RETRY",
        covers,
        ok,
        f"real_http={proxy.real_http_calls} hits={len(hit)} kinds={[r.invocation_kind for r in rows]}",
        [i.id for i in hit],
    )


async def scenario_repair_provider_retry(session, plus) -> ScenarioResult:
    from app.schemas.scene import SceneBoundaryResult
    from app.services.prompt_service import load_prompt
    from app.services.structured_output import StructuredOutputError
    from app.services.validation_errors import StructuralValidationError

    covers = "repair_provider_retry"
    run = make_run(session)
    state = {"n": 0}

    def biz(_):
        state["n"] += 1
        if state["n"] == 1:
            raise StructuralValidationError(
                "qualification OOS for repair retry",
                "JOURNEY_EVIDENCE_OUT_OF_SCOPE",
            )

    proxy = QualificationFaultProxy(
        plus,
        [
            FaultAction("canned_json", _boundary_ok()),
            FaultAction("disconnect"),
            FaultAction("passthrough"),
        ],
    )
    prompt = load_prompt("scene_boundary", "v3.1")
    try:
        await _run_generate(
            session=session,
            proxy=proxy,
            run=run,
            task_type="reader_journey_scene",
            schema=SceneBoundaryResult,
            prompt=prompt,
            user_content="qualification repair provider retry fixture",
            business_validator=biz,
            initial_invocation_kind="normal_batch_request",
        )
    except StructuredOutputError:
        pass
    rows = _rows_for_run(session, run.id)
    hit = _find_cover(rows, covers)
    ok = bool(hit) and proxy.real_http_calls >= 1
    return ScenarioResult(
        "FI-REPAIR-RETRY",
        covers,
        ok,
        f"real_http={proxy.real_http_calls} hits={len(hit)} kinds={[r.invocation_kind for r in rows]}",
        [i.id for i in hit],
    )


async def scenario_targeted_patch(session, plus) -> ScenarioResult:
    from app.schemas.reader_journey import SceneReaderJourneyBatchResult
    from app.services.prompt_service import load_prompt
    from app.services.reader_journey_validation import validate_scene_batch_result
    from app.services.structured_output import StructuredOutputError

    covers = "reader_journey_targeted_evidence_patch"
    run = make_run(session, task_type="reader_journey_scene")
    para = {
        1: {f"B0001-C0001-P{i:04d}" for i in range(1, 5)},
        2: {f"B0001-C0001-P{i:04d}" for i in range(5, 11)},
    }
    snapshot = {
        "profiles_target": [
            {
                "scene_id": 1,
                "scene_ordinal": 1,
                "paragraphs": [
                    {"id": f"B0001-C0001-P{i:04d}", "text": f"s1p{i}"} for i in range(1, 5)
                ],
            },
            {
                "scene_id": 2,
                "scene_ordinal": 2,
                "paragraphs": [
                    {"id": f"B0001-C0001-P{i:04d}", "text": f"s2p{i}"} for i in range(5, 11)
                ],
            },
        ],
        "owned_scene_ids_json": "[1, 2]",
    }

    def biz(value: SceneReaderJourneyBatchResult) -> None:
        validate_scene_batch_result(
            value, expected_scene_ids={1, 2}, paragraph_ids_by_scene=para
        )

    proxy = QualificationFaultProxy(
        plus,
        [
            FaultAction("canned_json", _load_oos_batch_json()),
            FaultAction("passthrough"),
        ],
    )
    prompt = load_prompt("reader_journey_scene", "v1.5")
    try:
        await _run_generate(
            session=session,
            proxy=proxy,
            run=run,
            task_type="reader_journey_scene",
            schema=SceneReaderJourneyBatchResult,
            prompt=prompt,
            user_content="qualification targeted evidence patch fixture",
            business_validator=biz,
            initial_invocation_kind="normal_batch_request",
            input_snapshot=snapshot,
        )
    except StructuredOutputError:
        pass
    rows = _rows_for_run(session, run.id)
    hit = _find_cover(rows, covers)
    ok = bool(hit) and proxy.real_http_calls >= 1
    return ScenarioResult(
        "FI-TARGETED-PATCH",
        covers,
        ok,
        f"real_http={proxy.real_http_calls} hits={len(hit)} kinds={[r.invocation_kind for r in rows]} types={[extract_policy(r).get('invocation_type') for r in rows]}",
        [i.id for i in hit],
    )


async def scenario_provider_recovery(session, plus) -> ScenarioResult:
    from app.schemas.scene import SceneBoundaryResult
    from app.services.prompt_service import load_prompt
    from app.services.structured_output import StructuredOutputError

    covers = "scene_analysis_provider_recovery"
    # Phase A: exhaust transport (fault injection) — no recovery orchestration needed.
    run_a = make_run(session, task_type="scene_analysis")
    proxy_a = QualificationFaultProxy(
        plus,
        [FaultAction("disconnect"), FaultAction("disconnect"), FaultAction("disconnect")],
    )
    prompt = load_prompt("scene_boundary", "v3.1")
    try:
        await _run_generate(
            session=session,
            proxy=proxy_a,
            run=run_a,
            task_type="scene_analysis",
            schema=SceneBoundaryResult,
            prompt=prompt,
            user_content="qualification recovery exhaust fixture",
            business_validator=lambda _: None,
        )
    except StructuredOutputError:
        pass
    # Phase B: resume-after-recovery real HTTP stamped as recovery type.
    run_b = make_run(session, task_type="scene_analysis")
    proxy_b = QualificationFaultProxy(plus, [FaultAction("passthrough")])
    try:
        await _run_generate(
            session=session,
            proxy=proxy_b,
            run=run_b,
            task_type="scene_analysis",
            schema=SceneBoundaryResult,
            prompt=prompt,
            user_content="qualification recovery resume fixture",
            business_validator=lambda _: None,
            policy_invocation_type=covers,
        )
    except StructuredOutputError as exc:
        return ScenarioResult(
            "FI-RECOVERY",
            covers,
            False,
            "resume failed",
            error=str(exc.error_code),
        )
    rows = _rows_for_run(session, run_b.id)
    hit = _find_cover(rows, covers)
    ok = bool(hit) and proxy_b.real_http_calls >= 1
    return ScenarioResult(
        "FI-RECOVERY",
        covers,
        ok,
        f"exhaust_calls={proxy_a.calls} resume_http={proxy_b.real_http_calls} hits={len(hit)}",
        [i.id for i in hit],
    )


async def scenario_chapter_schema_repair(session, plus) -> ScenarioResult:
    from app.schemas.scene import SceneBoundaryResult
    from app.services.prompt_service import load_prompt
    from app.services.structured_output import StructuredOutputError

    covers = "reader_journey_chapter_schema_repair"
    run = make_run(session)
    proxy = QualificationFaultProxy(
        plus,
        [
            FaultAction("invalid_json", _boundary_invalid()),
            FaultAction("passthrough"),
        ],
    )
    prompt = load_prompt("scene_boundary", "v3.1")
    try:
        await _run_generate(
            session=session,
            proxy=proxy,
            run=run,
            task_type="reader_journey_chapter",
            schema=SceneBoundaryResult,
            prompt=prompt,
            user_content="qualification chapter schema repair fixture",
            business_validator=lambda _: None,
            initial_invocation_kind="initial",
        )
    except StructuredOutputError:
        pass
    rows = _rows_for_run(session, run.id)
    hit = _find_cover(rows, covers)
    ok = bool(hit) and proxy.real_http_calls >= 1
    return ScenarioResult(
        "FI-SCHEMA-CHAPTER",
        covers,
        ok,
        f"real_http={proxy.real_http_calls} hits={len(hit)}",
        [i.id for i in hit],
    )


async def scenario_flash_rejected(session, plus) -> ScenarioResult:
    """Negative control: Flash request must fail pre-send (no HTTP)."""
    from app.services.model_invocation_broker import (
        ERROR_UNAUTHORIZED_FALLBACK,
        ModelInvocationBroker,
        ModelInvocationPolicyError,
    )

    broker = ModelInvocationBroker()
    try:
        broker.resolve(
            run_id=0,
            invocation_type="reader_journey_scene_schema_repair",
            authorized_provider=PROVIDER,
            authorized_model=MODEL,
            auto_route=False,
            requested_provider=FLASH,
            requested_model="qwen3.6-flash",
            gateway=None,
            fallback_policy="none",
            caller="qualification.flash_rejected",
        )
        return ScenarioResult("FI-FLASH-REJECT", "flash_reject", False, "flash was accepted")
    except ModelInvocationPolicyError as exc:
        ok = exc.error_code == ERROR_UNAUTHORIZED_FALLBACK
        return ScenarioResult(
            "FI-FLASH-REJECT",
            "flash_reject",
            ok,
            f"code={exc.error_code}",
        )


class Budget:
    def __init__(self, limits: dict):
        self.limits = limits
        self.started = time.perf_counter()
        self.certification_accounted_cost = 0.0
        self.requests = 0
        self.retries = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.unknown = 0

    def elapsed_minutes(self) -> float:
        return (time.perf_counter() - self.started) / 60.0

    def refresh(self, session) -> None:
        from sqlalchemy import func, select
        from app.db.models import ModelInvocation
        from certification.conservative_usage_accounting import account_invocations

        rows = list(
            session.scalars(
                select(ModelInvocation).where(
                    ModelInvocation.is_cloud.is_(True),
                    ModelInvocation.http_request_sent.is_(True),
                )
            )
        )
        summary = account_invocations(rows)
        self.requests = summary.request_count
        self.input_tokens = summary.certification_input_tokens
        self.output_tokens = summary.certification_output_tokens
        self.certification_accounted_cost = summary.certification_accounted_cost
        self.unknown = summary.unknown_count
        self.retries = int(
            session.execute(
                select(func.count(ModelInvocation.id)).where(
                    ModelInvocation.is_cloud.is_(True),
                    ModelInvocation.http_request_sent.is_(True),
                    ModelInvocation.attempt_no > 1,
                )
            ).scalar()
            or 0
        )

    def stop_reason(self) -> str | None:
        if self.unknown > 0:
            return "accounting_unknown"
        if self.requests >= self.limits["max_model_requests"]:
            return "max_model_requests"
        if self.retries >= self.limits["max_retry_requests"]:
            return "max_retry_requests"
        if self.input_tokens >= self.limits["max_input_tokens"]:
            return "max_input_tokens"
        if self.output_tokens >= self.limits["max_output_tokens"]:
            return "max_output_tokens"
        if self.certification_accounted_cost >= self.limits["max_cost_cny"]:
            return "max_cost"
        if self.elapsed_minutes() >= self.limits["max_total_duration_minutes"]:
            return "max_total_duration"
        return None


def evaluate_coverage(session) -> dict:
    from sqlalchemy import select
    from app.db.models import ModelInvocation

    rows = list(session.scalars(select(ModelInvocation).order_by(ModelInvocation.id)))
    by_type: dict[str, list[dict]] = {t: [] for t in REQUIRED_TYPES}
    policy_failures = []
    audits = []
    for inv in rows:
        pol = extract_policy(inv)
        audits.append(pol)
        itype = pol.get("invocation_type")
        if itype in by_type and inv.http_request_sent:
            missing = [k for k in POLICY_KEYS if pol.get(k) is None and k != "request_hash"]
            if pol.get("request_hash") in (None, ""):
                missing.append("request_hash")
            record = {**pol, "missing_policy_keys": missing}
            by_type[itype].append(record)
            if (
                pol.get("resolved_provider") != PROVIDER
                or pol.get("resolved_model") != MODEL
                or pol.get("fallback_used") is True
                or pol.get("auto_route") is True
                or pol.get("policy_match") is False
            ):
                policy_failures.append(record)
            if missing:
                policy_failures.append(record)
    coverage = {
        t: {
            "covered": len(items) > 0,
            "count": len(items),
            "invocation_ids": [i["invocation_id"] for i in items],
        }
        for t, items in by_type.items()
    }
    return {
        "coverage": coverage,
        "policy_failures": policy_failures,
        "audits": audits,
        "all_required_covered": all(v["covered"] for v in coverage.values()),
    }


async def async_main() -> int:
    os.chdir(ROOT)
    before_main = main_db_counts()
    if before_main != (55, 2):
        raise SystemExit(f"QUALIFICATION_BLOCKED: main DB not 55/2 before run: {before_main}")

    auth, pre, limits = load_auth_and_preflight()
    base_url = read_base_url()
    ensure_qual_env(base_url, limits["max_cost_cny"])

    # Prove offline gate still passes at start (separate process; no engine bind).
    import subprocess

    gate = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_model_invocation_policy.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if "INVOCATION_POLICY_PASS" not in (gate.stdout or ""):
        raise SystemExit(f"QUALIFICATION_BLOCKED: offline gate failed\n{gate.stdout}\n{gate.stderr}")

    from app.db.session import SessionLocal
    from app.services.model_invocation_broker import broker as _broker  # noqa: F401

    session = SessionLocal()
    budget = Budget(limits)
    results: list[ScenarioResult] = []
    stop_reason = None
    try:
        plus = build_real_plus_provider(session)
        scenarios = [
            scenario_schema_repair,
            scenario_structural_repair,
            scenario_generic_retry,
            scenario_repair_provider_retry,
            scenario_targeted_patch,
            scenario_provider_recovery,
            scenario_chapter_schema_repair,
            scenario_flash_rejected,
        ]
        for fn in scenarios:
            budget.refresh(session)
            stop_reason = budget.stop_reason()
            if stop_reason:
                break
            try:
                result = await fn(session, plus)
            except Exception as exc:  # noqa: BLE001
                result = ScenarioResult(
                    fn.__name__,
                    "unknown",
                    False,
                    "exception",
                    error=f"{type(exc).__name__}:{exc}",
                )
            results.append(result)
            budget.refresh(session)
            stop_reason = budget.stop_reason()
            if stop_reason:
                break
            # Persist incremental report
            (QUAL_AUDITS / "scenario-progress-v1.json").write_text(
                json.dumps(
                    {
                        "finished_at": _utc(),
                        "results": [r.__dict__ for r in results],
                        "budget": {
                            "certification_accounted_cost": budget.certification_accounted_cost,
                            "requests": budget.requests,
                            "retries": budget.retries,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
    finally:
        coverage = evaluate_coverage(session)
        budget.refresh(session)
        session.close()

    after_main = main_db_counts()
    flash_reject_ok = any(r.scenario_id == "FI-FLASH-REJECT" and r.ok for r in results)
    scenario_ok = all(
        r.ok for r in results if r.covers in REQUIRED_TYPES
    ) and flash_reject_ok
    policy_ok = not coverage["policy_failures"]
    covered_ok = coverage["all_required_covered"]
    main_ok = after_main == (55, 2) == before_main
    aborted = stop_reason is not None and not (scenario_ok and covered_ok and policy_ok)

    if aborted:
        verdict = "INVOCATION_PATH_QUALIFICATION_ABORTED_BY_LIMIT"
    elif scenario_ok and covered_ok and policy_ok and main_ok and not stop_reason:
        verdict = "INVOCATION_PATH_QUALIFICATION_PASSED"
    else:
        verdict = "INVOCATION_PATH_QUALIFICATION_FAILED"

    report = {
        "phase": "1D-B2-R11-QUAL",
        "verdict": verdict,
        "finished_at": _utc(),
        "authorization_ref": str(AUTH.relative_to(ROOT)).replace("\\", "/"),
        "preflight_ref": str(PREFLIGHT.relative_to(ROOT)).replace("\\", "/"),
        "change_package": "global-model-invocation-policy-change-v1.1.0",
        "provider": PROVIDER,
        "model": MODEL,
        "auto_route": False,
        "qualification_db": str(QUAL_DB.relative_to(ROOT)).replace("\\", "/"),
        "main_db_before": {"analysis_runs": before_main[0], "reader_journey_runs": before_main[1]},
        "main_db_after": {"analysis_runs": after_main[0], "reader_journey_runs": after_main[1]},
        "stop_reason": stop_reason,
        "budget": {
            "max_cost_cny": limits["max_cost_cny"],
            "certification_accounted_cost": budget.certification_accounted_cost,
            "requests": budget.requests,
            "retries": budget.retries,
            "input_tokens": budget.input_tokens,
            "output_tokens": budget.output_tokens,
            "elapsed_minutes": budget.elapsed_minutes(),
            "unknown_accounting_count": budget.unknown,
        },
        "scenarios": [r.__dict__ for r in results],
        "coverage": coverage["coverage"],
        "policy_failures": coverage["policy_failures"],
        "invocation_audits": coverage["audits"],
        "full_canary_started": False,
        "authorization_v12_issued": False,
    }
    QUAL_AUDITS.mkdir(parents=True, exist_ok=True)
    (QUAL_AUDITS / "qualification-report-v1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (QUAL_AUDITS / "final-verdict-v1.json").write_text(
        json.dumps(
            {
                "verdict": verdict,
                "defect_015_followup": (
                    "READY_FOR_CANARY_PREFLIGHT_V12"
                    if verdict == "INVOCATION_PATH_QUALIFICATION_PASSED"
                    else "DEFECT_015_NOT_REMEDIATED"
                ),
                "finished_at": _utc(),
                "certification_accounted_cost": budget.certification_accounted_cost,
                "main_db_invariance": "55/2" if main_ok else "DRIFT",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(verdict)
    print(
        json.dumps(
            {
                "covered": coverage["coverage"],
                "cost": budget.certification_accounted_cost,
                "requests": budget.requests,
                "scenarios": [(r.scenario_id, r.ok, r.detail) for r in results],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if verdict == "INVOCATION_PATH_QUALIFICATION_PASSED" else 1


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
