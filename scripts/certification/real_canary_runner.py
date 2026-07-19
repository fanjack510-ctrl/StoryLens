# -*- coding: utf-8 -*-
"""Phase 1D-B2: Real API Single-Chapter Journey Canary runner.

Produces real model HTTP. Requires operator authorization file.
Does not write to data/storylens.db.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "apps" / "api") not in sys.path:
    sys.path.insert(0, str(ROOT / "apps" / "api"))

ART = ROOT / "artifacts" / "single-chapter-pipeline-certification" / "real-canary"
CANARY_DB = ART / "canary-v13.sqlite3"
OLD_CANARY_DB = ART / "canary-v12.sqlite3"
AUDITS = ROOT / "audits" / "single-chapter-pipeline" / "real-canary-v13"
OLD_AUDITS = ROOT / "audits" / "single-chapter-pipeline" / "real-canary-v12"
AUTH = AUDITS / "authorization-v13.json"
MAIN_DB = ROOT / "data" / "storylens.db"
PREFLIGHT = ROOT / "audits" / "single-chapter-pipeline" / "real-canary-preflight-v13.json"
FORBIDDEN_RESUME_BATCHES = (
    "phase-1db2-20260718T115555Z",
    "phase-1db2-r1-20260718T130551Z",
    "phase-1db2-r2-20260718T135023Z",
    "phase-1db2-r3-20260718T142546Z",
    "phase-1db2-r4-20260718T144746Z",
    "phase-1db2-r5-20260718T151121Z",
    "phase-1db2-r6-20260718T153541Z",
    "phase-1db2-r7-20260718T155450Z",
    "phase-1db2-r8-20260718T161902Z",
    "phase-1db2-r9-20260718T165459Z",
    "phase-1db2-r10-20260719T000923Z",
    "phase-1db2-r11-20260719T014426Z",
)
CHANGE_PACKAGE = "reader-journey-evidence-budget-change-v1.1.1"
FLASH_PROVIDER = "aliyun_qwen_flash"

PROVIDER = "aliyun_qwen_plus"
MODEL = "qwen3.7-plus"

# Canary order: C3 first (DEFECT-016 holdout), A2 second, then remaining + repeats
CANARY_PLAN = [
    {"run_index": 1, "fixture_id": "C3-long-action", "repeat_of": None},
    {"run_index": 2, "fixture_id": "A2-medium-action", "repeat_of": None},
    {"run_index": 3, "fixture_id": "B2-medium-description", "repeat_of": None},
    {"run_index": 4, "fixture_id": "A1-short-dialogue", "repeat_of": None},
    {"run_index": 5, "fixture_id": "B3-long-payoff", "repeat_of": None},
    {"run_index": 6, "fixture_id": "C1-short-info", "repeat_of": None},
    {"run_index": 7, "fixture_id": "C3-long-action", "repeat_of": 1},
    {"run_index": 8, "fixture_id": "B3-long-payoff", "repeat_of": 5},
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_main_db(label: str) -> dict:
    if not MAIN_DB.exists():
        return {"label": label, "exists": False}
    digest = sha256_file(MAIN_DB)
    size = MAIN_DB.stat().st_size
    mtime = MAIN_DB.stat().st_mtime
    import sqlite3

    uri = MAIN_DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    cur = con.cursor()
    analysis = cur.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0]
    journey = cur.execute("SELECT COUNT(*) FROM reader_journey_runs").fetchone()[0]
    run55 = cur.execute("SELECT status FROM analysis_runs WHERE id=55").fetchone()
    jr2 = cur.execute("SELECT status FROM reader_journey_runs WHERE id=2").fetchone()
    con.close()
    return {
        "label": label,
        "exists": True,
        "path": MAIN_DB.as_posix(),
        "sha256": digest,
        "size": size,
        "mtime": mtime,
        "analysis_run_count": analysis,
        "reader_journey_run_count": journey,
        "run_55_status": run55[0] if run55 else None,
        "journey_run_2_status": jr2[0] if jr2 else None,
        "captured_at": utc_now(),
        "open_mode": "ro",
    }


def load_auth_and_limits() -> tuple[dict, dict]:
    if not AUTH.exists():
        raise SystemExit("AUTHORIZATION_REQUIRED: missing authorization-v13.json")
    if not PREFLIGHT.exists():
        raise SystemExit("REAL_CANARY_BLOCKED: missing real-canary-preflight-v13.json")
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    pre = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if not pre.get("execution_allowed"):
        raise SystemExit("REAL_CANARY_BLOCKED: preflight-v13 execution_allowed!=true")
    if pre.get("status") != "OPERATOR_AUTHORIZED":
        raise SystemExit("REAL_CANARY_BLOCKED: preflight-v13 not OPERATOR_AUTHORIZED")
    if not auth.get("operator_approved"):
        raise SystemExit("AUTHORIZATION_REQUIRED: operator_approved!=true")
    note = str(auth.get("operator_approval_note") or "").strip()
    if not note:
        raise SystemExit("AUTHORIZATION_REQUIRED: operator_approval_note required")
    if auth.get("batch_generation") != "v13":
        raise SystemExit("AUTHORIZATION_REQUIRED: authorization must be batch_generation=v13")
    # Never reuse older authorizations.
    for forbidden_gen in (
        "v1",
        "v2",
        "v3",
        "v4",
        "v5",
        "v6",
        "v7",
        "v8",
        "v9",
        "v10",
        "v11",
        "v12",
    ):
        if auth.get("batch_generation") == forbidden_gen:
            raise SystemExit(
                f"AUTHORIZATION_REQUIRED: authorization-{forbidden_gen} must not be reused"
            )
        if f"authorization-{forbidden_gen}" in str(auth.get("preflight_ref") or ""):
            raise SystemExit(
                f"AUTHORIZATION_REQUIRED: authorization-{forbidden_gen} must not be reused"
            )
    if "authorization-qualification-v1" in note and "不得复用" not in note:
        raise SystemExit(
            "AUTHORIZATION_REQUIRED: must not reuse authorization-qualification-v1"
        )
    if "preflight-v13" not in note and "real-canary-preflight-v13" not in note:
        raise SystemExit(
            "AUTHORIZATION_REQUIRED: approval note must bind real-canary-preflight-v13"
        )
    if "reader-journey-evidence-budget-change-v1.1.1" not in note:
        raise SystemExit(
            "AUTHORIZATION_REQUIRED: approval note must bind evidence-budget-change-v1.1.1"
        )
    qual_report = (
        ROOT
        / "audits"
        / "single-chapter-pipeline"
        / "invocation-path-qualification-v1"
        / "qualification-report-v1.json"
    )
    if not qual_report.exists():
        raise SystemExit("REAL_CANARY_BLOCKED: missing qualification-report-v1.json")
    qual = json.loads(qual_report.read_text(encoding="utf-8"))
    if qual.get("verdict") != "INVOCATION_PATH_QUALIFICATION_PASSED":
        raise SystemExit(
            f"REAL_CANARY_BLOCKED: qualification not passed ({qual.get('verdict')})"
        )
    budget_gate = (
        ROOT / "audits" / "single-chapter-pipeline" / "reader-journey-output-budget-v1.json"
    )
    if not budget_gate.exists():
        raise SystemExit("REAL_CANARY_BLOCKED: missing reader-journey-output-budget-v1.json")
    budget_audit = json.loads(budget_gate.read_text(encoding="utf-8"))
    if budget_audit.get("all_pass") is not True:
        raise SystemExit("REAL_CANARY_BLOCKED: output budget audit all_pass!=true")
    if (pre.get("hard_limits") or {}).get("max_cost") is None:
        raise SystemExit("REAL_CANARY_BLOCKED: preflight-v13 max_cost is null")
    max_cost = float(auth["operator_max_cost_cny"])
    if max_cost <= 0:
        raise SystemExit("AUTHORIZATION_REQUIRED: max_cost must be > 0")
    worst = (pre.get("aggregate_estimates") or {}).get("estimated_cost_cny_worst")
    if worst is None:
        raise SystemExit("REAL_CANARY_BLOCKED: preflight worst cost unset")
    if max_cost < float(worst):
        raise SystemExit(
            f"REAL_CANARY_BLOCKED: max_cost {max_cost} < preflight worst {worst}"
        )
    # Never resume or overwrite failed prior batch audits/DB.
    old_verdict = OLD_AUDITS / "final-verdict-v1.json"
    if old_verdict.exists():
        old = json.loads(old_verdict.read_text(encoding="utf-8"))
        if old.get("batch_id") in FORBIDDEN_RESUME_BATCHES and old.get("verdict") not in {
            "REAL_CANARY_FAILED",
            "REAL_CANARY_ABORTED_BY_LIMIT",
            "REAL_CANARY_BLOCKED",
        }:
            raise SystemExit("REAL_CANARY_BLOCKED: unexpected old-batch verdict mutation")
        if old.get("batch_id") == "phase-1db2-r11-20260719T014426Z" and old.get(
            "verdict"
        ) != "REAL_CANARY_FAILED":
            raise SystemExit(
                "REAL_CANARY_BLOCKED: prior r11 verdict must remain REAL_CANARY_FAILED"
            )
    if OLD_CANARY_DB.exists() and CANARY_DB.resolve() == OLD_CANARY_DB.resolve():
        raise SystemExit("REAL_CANARY_BLOCKED: refusing to reuse canary-v12.sqlite3")
    if auth.get("canary_database") and "canary-v13.sqlite3" not in str(auth["canary_database"]):
        raise SystemExit("AUTHORIZATION_REQUIRED: auth must bind canary-v13.sqlite3")
    if auth.get("change_package_ref") and CHANGE_PACKAGE not in str(auth["change_package_ref"]):
        raise SystemExit(
            f"AUTHORIZATION_REQUIRED: auth must bind {CHANGE_PACKAGE}"
        )
    if auth.get("reader_journey_scene_prompt") not in (None, "v1.6"):
        raise SystemExit("AUTHORIZATION_REQUIRED: reader_journey_scene_prompt must be v1.6")
    if auth.get("evidence_paragraph_ids_max_items") not in (None, 16):
        raise SystemExit(
            "AUTHORIZATION_REQUIRED: evidence_paragraph_ids_max_items must remain 16"
        )
    if auth.get("run_1_fixture_id") != "C3-long-action":
        raise SystemExit("AUTHORIZATION_REQUIRED: run_1_fixture_id must be C3-long-action")
    if auth.get("run_2_fixture_id") != "A2-medium-action":
        raise SystemExit("AUTHORIZATION_REQUIRED: run_2_fixture_id must be A2-medium-action")
    if (
        CANARY_PLAN[0]["fixture_id"] != "C3-long-action"
        or CANARY_PLAN[1]["fixture_id"] != "A2-medium-action"
    ):
        raise SystemExit("REAL_CANARY_BLOCKED: CANARY_PLAN run order must be C3 then A2")
    limits = {
        "max_full_pipeline_runs": 8,
        "max_model_requests": int(
            (pre.get("hard_limits") or {}).get(
                "max_model_requests",
                (pre.get("aggregate_estimates") or {}).get("estimated_model_requests_worst", 480),
            )
        ),
        "max_input_tokens": int(
            (pre.get("hard_limits") or {}).get(
                "max_input_tokens",
                (pre.get("aggregate_estimates") or {}).get("estimated_input_tokens_worst", 6_500_000),
            )
        ),
        "max_output_tokens": int(
            (pre.get("hard_limits") or {}).get(
                "max_output_tokens",
                (pre.get("aggregate_estimates") or {}).get("estimated_output_tokens_worst", 500_000),
            )
        ),
        "max_retry_requests": int((pre.get("hard_limits") or {}).get("max_retry_requests", 96)),
        "max_cost_cny": max_cost,
        "max_total_duration_minutes": int(
            (pre.get("hard_limits") or {}).get("max_total_duration_minutes", 300)
        ),
        "worst_cost_cny": float(worst),
        "nominal_cost_cny": float(
            (pre.get("aggregate_estimates") or {}).get("estimated_cost_cny_nominal") or 0
        ),
    }
    return auth, limits


def ensure_canary_env() -> str:
    ART.mkdir(parents=True, exist_ok=True)
    AUDITS.mkdir(parents=True, exist_ok=True)
    (AUDITS / "defects").mkdir(parents=True, exist_ok=True)
    rel = (
        "sqlite:///./artifacts/single-chapter-pipeline-certification/"
        "real-canary/canary-v13.sqlite3"
    )
    os.environ["STORYLENS_DATABASE_URL"] = rel
    # Frozen output budgets (reader-journey-output-budget-v1 / DEFECT-016).
    # Do not raise these during the batch to bypass truncation failures.
    os.environ.setdefault("STORYLENS_CLOUD_OUTPUT_READER_JOURNEY_SCENE", "3500")
    os.environ.setdefault("STORYLENS_CLOUD_OUTPUT_READER_JOURNEY_CHAPTER", "3000")
    os.environ.setdefault("STORYLENS_CLOUD_OUTPUT_READER_JOURNEY_BUSINESS_REPAIR", "3500")
    os.environ.setdefault("STORYLENS_CLOUD_OUTPUT_READER_JOURNEY_EVIDENCE_REPAIR", "1600")
    os.environ.setdefault("STORYLENS_CLOUD_OUTPUT_READER_JOURNEY_SCHEMA_REPAIR", "3500")
    # Prevent accidental main DB bind from cached settings in same process.
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    url = settings.database_url
    if "storylens.db" in url and "canary-v13" not in url:
        raise SystemExit("REAL_CANARY_BLOCKED: database URL points at main DB")
    if "canary-v13.sqlite3" not in url:
        raise SystemExit(f"REAL_CANARY_BLOCKED: unexpected database URL {url}")
    if settings.cloud_output_reader_journey_scene < 3000:
        raise SystemExit(
            "REAL_CANARY_BLOCKED: journey scene output limit too low for real canary"
        )
    if settings.cloud_output_reader_journey_evidence_repair != 1600:
        raise SystemExit(
            "REAL_CANARY_BLOCKED: evidence_repair output must stay at frozen 1600"
        )
    if settings.cloud_output_reader_journey_schema_repair < 3000:
        raise SystemExit(
            "REAL_CANARY_BLOCKED: schema_repair output limit too low for real canary"
        )
    return url


class BatchBudget:
    def __init__(self, limits: dict) -> None:
        self.limits = limits
        self.started = time.perf_counter()
        self.requests = 0
        self.retries = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost = 0.0
        self.actual_reported_cost = 0.0
        self.conservative_estimated_cost = 0.0
        self.certification_accounted_cost = 0.0
        self.unknown_accounting_count = 0
        self.latest_accounting_summary: dict | None = None

    def elapsed_minutes(self) -> float:
        return (time.perf_counter() - self.started) / 60.0

    def check_before_run(self, estimated_next_cost: float = 2.0) -> str | None:
        if self.unknown_accounting_count > 0:
            return "accounting_unknown"
        if self.requests >= self.limits["max_model_requests"]:
            return "max_model_requests"
        if self.retries >= self.limits["max_retry_requests"]:
            return "max_retry_requests"
        if self.input_tokens >= self.limits["max_input_tokens"]:
            return "max_input_tokens"
        if self.output_tokens >= self.limits["max_output_tokens"]:
            return "max_output_tokens"
        if self.certification_accounted_cost + estimated_next_cost > self.limits["max_cost_cny"]:
            return "max_cost"
        if self.elapsed_minutes() >= self.limits["max_total_duration_minutes"]:
            return "max_total_duration"
        return None

    def refresh_from_db(self, session) -> None:
        from sqlalchemy import func, select

        from app.db.models import ModelInvocation
        from certification.conservative_usage_accounting import account_invocations

        rows = list(
            session.scalars(
                select(ModelInvocation)
                .where(
                    ModelInvocation.is_cloud.is_(True),
                    ModelInvocation.http_request_sent.is_(True),
                )
                .order_by(ModelInvocation.id)
            )
        )
        summary = account_invocations(rows)
        self.requests = summary.request_count
        self.input_tokens = summary.certification_input_tokens
        self.output_tokens = summary.certification_output_tokens
        self.actual_reported_cost = summary.actual_reported_cost
        self.conservative_estimated_cost = summary.conservative_estimated_cost
        self.certification_accounted_cost = summary.certification_accounted_cost
        self.cost = summary.certification_accounted_cost
        self.unknown_accounting_count = summary.unknown_count
        self.latest_accounting_summary = summary.to_dict()
        retry_rows = session.execute(
            select(func.count(ModelInvocation.id)).where(
                ModelInvocation.is_cloud.is_(True),
                ModelInvocation.http_request_sent.is_(True),
                ModelInvocation.attempt_no > 1,
            )
        ).scalar()
        self.retries = int(retry_rows or 0)


def append_ledger(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_run_failure_defect(
    *,
    batch_id: str,
    run_index: int,
    fixture_id: str,
    analysis_run_id: int | None,
    journey_run_id: int | None,
    stage: str,
    session_factory,
) -> str:
    """Persist failure with full error causality (DEFECT-010 requirement)."""
    from sqlalchemy import select, text

    from app.db.models import ModelInvocation, ReaderJourneyRun

    defect_id = f"DEFECT-CANARY-RUN{run_index:02d}"

    with session_factory() as session:
        jr = session.get(ReaderJourneyRun, journey_run_id) if journey_run_id else None
        invs = []
        if analysis_run_id is not None:
            invs = list(
                session.scalars(
                    select(ModelInvocation)
                    .where(ModelInvocation.run_id == analysis_run_id)
                    .order_by(ModelInvocation.id)
                )
            )
        journey_invs = [
            i
            for i in invs
            if str(i.task_type or "").startswith("reader_journey")
        ]
        failed = [i for i in invs if i.status == "failed"]
        details = {}
        if jr and jr.failure_details_json:
            try:
                details = json.loads(jr.failure_details_json)
            except json.JSONDecodeError:
                details = {"raw": jr.failure_details_json}
        active_reservations = session.execute(
            text("SELECT COUNT(*) FROM cloud_budget_reservations WHERE status='active'")
        ).scalar()
        profile_count = 0
        if journey_run_id is not None:
            from app.db.models import SceneReaderJourneyProfile

            profile_count = len(
                list(
                    session.scalars(
                        select(SceneReaderJourneyProfile).where(
                            SceneReaderJourneyProfile.reader_journey_run_id == journey_run_id
                        )
                    )
                )
            )

        root_code = (jr.root_error_code if jr else None) or (
            failed[-1].error_code if failed else "UNKNOWN"
        )
        payload = {
            "id": defect_id,
            "severity": "P1",
            "batch_id": batch_id,
            "fixture": fixture_id,
            "run_index": run_index,
            "stage": stage or (jr.failed_stage if jr else "unknown"),
            "error_code": root_code,
            "actual": (jr.root_error_message if jr else None)
            or (failed[-1].error_message if failed else None),
            "primary_error": details.get("primary_error"),
            "transport_error": details.get("transport_error"),
            "failure_details": details,
            "analysis_status": None,
            "journey_status": jr.status if jr else None,
            "retryable": bool(jr.retryable) if jr else None,
            "data_risk": False,
            "cost_risk": True,
            "failed_invocations": [
                {
                    "id": i.id,
                    "task_type": i.task_type,
                    "invocation_kind": i.invocation_kind,
                    "status": i.status,
                    "error_code": i.error_code,
                    "error_message": i.error_message,
                    "finish_reason": i.finish_reason,
                    "attempt_no": i.attempt_no,
                    "latency_ms": i.latency_ms,
                    "input_tokens": i.input_tokens,
                    "output_tokens": i.output_tokens,
                    "estimated_cost": i.estimated_cost,
                    "request_hash": i.request_hash,
                }
                for i in failed
            ],
            "reader_journey_invocations": [
                {
                    "id": i.id,
                    "attempt_no": i.attempt_no,
                    "kind": i.invocation_kind,
                    "status": i.status,
                    "code": i.error_code,
                    "latency_ms": i.latency_ms,
                    "hash": i.request_hash,
                    "tokens": [i.input_tokens, i.output_tokens],
                    "cost": i.estimated_cost,
                    "sent_at": i.sent_at.isoformat() if i.sent_at else None,
                }
                for i in journey_invs
            ],
            "failed_run_profile_count": profile_count,
            "active_reservations": int(active_reservations or 0),
            "notes": (
                "Batch stopped on first full-pipeline failure. "
                "Do not resume this batch. Error causality preserved in failure_details."
            ),
            "recommended_next": "Do not resume; diagnose from defect + ledger; new batch only after remediation if needed.",
        }
    write_json(AUDITS / "defects" / f"{defect_id}.json", payload)
    return defect_id


def _extract_invocation_policy(inv) -> dict:
    params: dict = {}
    if inv.request_parameters_json:
        try:
            params = json.loads(inv.request_parameters_json)
        except json.JSONDecodeError:
            params = {}
    return {
        "invocation_type": params.get("invocation_type"),
        "requested_provider": params.get("requested_provider"),
        "requested_model": params.get("requested_model"),
        "resolved_provider": params.get("resolved_provider") or inv.provider_name,
        "resolved_model": params.get("resolved_model") or inv.model_name,
        "route_source": params.get("route_source"),
        "fallback_used": params.get("fallback_used"),
        "auto_route": params.get("auto_route"),
        "provider_enabled": params.get("provider_enabled"),
        "policy_match": params.get("policy_match"),
        "request_hash": inv.request_hash or params.get("request_hash"),
    }


def assert_invocation_policy_ok(session) -> str | None:
    """Return stop reason if any invocation violates frozen Plus policy."""
    from sqlalchemy import select

    from app.db.models import ModelInvocation
    from app.services.model_invocation_broker import REGISTERED_INVOCATION_TYPES

    rows = list(session.scalars(select(ModelInvocation).order_by(ModelInvocation.id)))
    for inv in rows:
        pol = _extract_invocation_policy(inv)
        provider = pol.get("resolved_provider") or inv.provider_name
        model = pol.get("resolved_model") or inv.model_name
        if provider == FLASH_PROVIDER or inv.provider_name == FLASH_PROVIDER:
            return "MODEL_UNAUTHORIZED_FALLBACK"
        if inv.http_request_sent:
            if provider != PROVIDER or model != MODEL:
                return "MODEL_INVOCATION_POLICY_VIOLATION"
            if pol.get("fallback_used") is True:
                return "MODEL_UNAUTHORIZED_FALLBACK"
            if pol.get("auto_route") is True:
                return "MODEL_INVOCATION_POLICY_VIOLATION"
            if pol.get("policy_match") is False:
                return "MODEL_INVOCATION_POLICY_VIOLATION"
            itype = pol.get("invocation_type")
            if itype is not None and itype not in REGISTERED_INVOCATION_TYPES:
                return "MODEL_INVOCATION_TYPE_UNREGISTERED"
        if inv.error_code in {
            "MODEL_INVOCATION_POLICY_VIOLATION",
            "MODEL_UNAUTHORIZED_FALLBACK",
            "MODEL_INVOCATION_TYPE_UNREGISTERED",
            "MODEL_PROVIDER_DISABLED_PRECHECK",
        }:
            return str(inv.error_code)
    return None


def apply_post_sync_guards(session, budget: "BatchBudget") -> str | None:
    """Policy + accounting hard stops after ledger sync. Returns stop_reason or None."""
    policy_hit = assert_invocation_policy_ok(session)
    if policy_hit:
        return policy_hit
    budget.refresh_from_db(session)
    if budget.unknown_accounting_count > 0:
        return "accounting_unknown"
    hit = budget.check_before_run(estimated_next_cost=0.0)
    if hit == "max_cost":
        return "max_cost"
    return None


def sync_invocations_to_ledger(
    session,
    *,
    batch_id: str,
    fixture_id: str,
    book_fixture_id: str,
    chapter_fixture_id: str,
    analysis_run_id: int | None,
    reader_journey_run_id: int | None,
    ledger_path: Path,
    seen_ids: set[int],
) -> None:
    from sqlalchemy import select

    from app.db.models import ModelInvocation
    from certification.conservative_usage_accounting import account_invocation_row

    rows = list(session.scalars(select(ModelInvocation).order_by(ModelInvocation.id)))
    for inv in rows:
        if inv.id in seen_ids:
            continue
        seen_ids.add(inv.id)
        accounting = account_invocation_row(inv)
        pol = _extract_invocation_policy(inv)
        append_ledger(
            ledger_path,
            {
                "batch_id": batch_id,
                "fixture_id": fixture_id,
                "book_fixture_id": book_fixture_id,
                "chapter_fixture_id": chapter_fixture_id,
                "analysis_run_id": analysis_run_id or inv.run_id,
                "reader_journey_run_id": reader_journey_run_id,
                "pipeline_stage": inv.task_type,
                "provider": inv.provider_name,
                "model": inv.model_name,
                "prompt_version": inv.prompt_version,
                "contract_version": inv.schema_version,
                "request_attempt": inv.attempt_no,
                "request_start": inv.sent_at.isoformat() if inv.sent_at else (
                    inv.created_at.isoformat() if inv.created_at else None
                ),
                "request_end": inv.created_at.isoformat() if inv.created_at else None,
                "latency_ms": inv.latency_ms,
                # Legacy mirrored fields (reported-only; never invent tokens here).
                "input_tokens": inv.input_tokens,
                "output_tokens": inv.output_tokens,
                "estimated_or_reported_cost": inv.estimated_cost,
                "reported_input_tokens": accounting.reported_input_tokens,
                "reported_output_tokens": accounting.reported_output_tokens,
                "reported_cost": accounting.reported_cost,
                "estimated_input_tokens": accounting.estimated_input_tokens,
                "estimated_output_tokens": accounting.estimated_output_tokens,
                "estimated_cost": accounting.estimated_cost,
                "accounting_status": accounting.accounting_status,
                "usage_source": accounting.usage_source,
                "estimate_reason": accounting.estimate_reason,
                "reservation_amount": accounting.reservation_amount,
                "settled_amount": accounting.settled_amount,
                "certification_cost": accounting.certification_cost,
                "cost_currency": inv.currency or "CNY",
                "retry_reason": inv.error_code if (inv.attempt_no or 1) > 1 else None,
                "response_hash": inv.content_hash or inv.request_hash,
                "final_status": inv.status,
                "reservation_id": None,
                "model_invocation_id": inv.id,
                "http_request_sent": inv.http_request_sent,
                "error_code": inv.error_code,
                "invocation_type": pol.get("invocation_type"),
                "requested_provider": pol.get("requested_provider"),
                "requested_model": pol.get("requested_model"),
                "resolved_provider": pol.get("resolved_provider"),
                "resolved_model": pol.get("resolved_model"),
                "route_source": pol.get("route_source"),
                "fallback_used": pol.get("fallback_used"),
                "auto_route": pol.get("auto_route"),
                "provider_enabled": pol.get("provider_enabled"),
                "policy_match": pol.get("policy_match"),
                "request_hash": pol.get("request_hash"),
            },
        )


def seed_canary_settings(session, *, max_cost_cny: float, base_url: str) -> None:
    import json as _json

    from app.db.models import ApplicationSetting, ProviderConfiguration
    from app.schemas.settings import CloudBudgetUpdate

    session.merge(ApplicationSetting(key="cloud_enabled", value_json=_json.dumps(True)))
    budget = CloudBudgetUpdate().model_dump()
    budget.update(
        {
            "cloud_daily_request_limit": 500,
            "cloud_daily_token_limit": 8_000_000,
            "cloud_daily_estimated_cost_limit": float(max_cost_cny),
            "cloud_max_requests_per_run": 200,
            "cloud_max_input_tokens_per_request": 16000,
            "cloud_max_output_tokens_per_request": 4000,
            "cloud_stop_on_unknown_pricing": True,
        }
    )
    session.merge(
        ApplicationSetting(key="cloud_budget_settings", value_json=_json.dumps(budget))
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
            timeout_seconds=300,
            max_retries=3,
            enabled=True,
            disconnected=False,
            allow_auto_route=False,
            raw_logging_enabled=False,
            credential_reference=f"keyring:{PROVIDER}",
        )
    )
    session.commit()


def main() -> int:
    os.chdir(ROOT)
    auth, limits = load_auth_and_limits()
    batch_id = f"phase-1db2-r13-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    if any(forbidden == batch_id for forbidden in FORBIDDEN_RESUME_BATCHES):
        raise SystemExit("REAL_CANARY_BLOCKED: refusing forbidden resume batch id")
    if batch_id.startswith("phase-1db2-r11-"):
        raise SystemExit("REAL_CANARY_BLOCKED: refusing to mint r11 resume batch id")

    # Credential presence (never print value)
    from app.services.credentials.keyring_store import KeyringCredentialStore

    store = KeyringCredentialStore()
    secret = store.get(PROVIDER)
    if not secret or not str(secret).strip():
        write_json(
            AUDITS / "final-verdict-v1.json",
            {
                "verdict": "REAL_CANARY_BLOCKED",
                "reason": "credential_missing",
                "batch_id": batch_id,
            },
        )
        print("REAL_CANARY_BLOCKED: credential missing")
        return 2

    # Main provider base_url (RO) — same source as certified canary seed, then
    # normalize through shared resolve_aliyun_compatible_base_url.
    import sqlite3

    from app.services.aliyun_endpoint import resolve_aliyun_compatible_base_url

    uri = MAIN_DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    base_url_row = con.execute(
        "SELECT base_url, workspace_id, region FROM provider_configurations WHERE provider_name=?",
        (PROVIDER,),
    ).fetchone()
    con.close()
    if not base_url_row or not (base_url_row[0] or base_url_row[1]):
        print("REAL_CANARY_BLOCKED: provider base_url/workspace missing on main config")
        return 2
    base_url = resolve_aliyun_compatible_base_url(
        base_url=base_url_row[0] or "",
        workspace_id=base_url_row[1] or "",
        region=base_url_row[2] or "cn-beijing",
        allow_region_public_default=False,
    )
    if not base_url:
        print("REAL_CANARY_BLOCKED: resolved provider base_url empty")
        return 2

    before = snapshot_main_db("before")
    write_json(AUDITS / "main-database-invariance-v1.json", {"before": before})

    if CANARY_DB.exists():
        CANARY_DB.unlink()

    db_url = ensure_canary_env()
    print(f"batch_id={batch_id}")
    print(f"database_url={db_url}")
    print(f"max_cost_cny={limits['max_cost_cny']} worst_preflight={limits['worst_cost_cny']}")

    # Import app after env
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.db.models import (
        AnalysisArtifact,
        AnalysisRun,
        BoundaryReviewDecision,
        BoundaryReviewSession,
        Chapter,
        Paragraph,
        ReaderJourneyRun,
        Scene,
        SceneReaderJourneyProfile,
    )
    from app.db.session import SessionLocal, create_db, engine
    from app.main import app
    from app.services.book_service import import_book

    sys.path.insert(0, str(ROOT / "scripts"))
    from certification.chapter_fixtures import build_cert_chapter_specs

    # Safety: engine must not point at main
    if "storylens.db" in str(engine.url) and "canary-v13" not in str(engine.url):
        raise SystemExit("REAL_CANARY_BLOCKED: engine bound to main DB")
    if "canary-v13" not in str(engine.url):
        raise SystemExit(f"REAL_CANARY_BLOCKED: engine not bound to canary-v13 ({engine.url})")

    create_db()
    with SessionLocal() as session:
        seed_canary_settings(session, max_cost_cny=limits["max_cost_cny"], base_url=base_url)

    specs = {s.fixture_id: s for s in build_cert_chapter_specs()}
    ledger_path = AUDITS / "model-call-ledger-v1.jsonl"
    if ledger_path.exists():
        ledger_path.unlink()

    chapter_matrix = []
    fixture_to_chapter: dict[str, dict] = {}
    seen_inv: set[int] = set()
    budget = BatchBudget(limits)
    run_results: list[dict] = []
    stop_reason: str | None = None
    verdict = "REAL_CANARY_PASSED"

    write_json(
        AUDITS / "batch-manifest-v1.json",
        {
            "batch_id": batch_id,
            "provider": PROVIDER,
            "model": MODEL,
            "allow_auto_route": False,
            "limits": limits,
            "authorization": {
                "operator_approved": True,
                "operator_max_cost_cny": auth["operator_max_cost_cny"],
            },
            "canary_db": CANARY_DB.as_posix(),
            "prior_failed_batch_archived": "real-canary-v12/batches/phase-1db2-r11-20260719T014426Z",
            "change_package": CHANGE_PACKAGE,
            "import_mode": "narrative_text_only",
            "plan": CANARY_PLAN,
            "started_at": utc_now(),
        },
    )

    # Do not let background StructuredOutputError abort the whole batch process.
    client = TestClient(app, raise_server_exceptions=False)

    # Import unique fixtures once (6 chapters)
    unique_fixtures = []
    for item in CANARY_PLAN:
        if item["fixture_id"] not in unique_fixtures:
            unique_fixtures.append(item["fixture_id"])

    with SessionLocal() as session:
        for fid in unique_fixtures:
            spec = specs[fid]
            # Import narrative text only. Stamp lines as separate paragraphs cause the
            # boundary model to isolate them as Scene #1 and fail scene_analysis on
            # non-narrative content (DEFECT-CANARY-001 residual / canary-v2 run1).
            stamped = spec.text.encode("utf-8")
            book = import_book(session, f"{fid}.txt", stamped)
            book.title = spec.book_title
            # Provenance lives in certification matrix/ledger, not chapter body.
            if hasattr(book, "source_path"):
                pass
            session.commit()
            chapters = list(
                session.scalars(
                    select(Chapter)
                    .where(Chapter.book_id == book.id)
                    .order_by(Chapter.chapter_index)
                )
            )
            if not chapters:
                raise RuntimeError(f"no chapter imported for {fid}")

            def _chapter_paragraph_count(chapter_id: int) -> int:
                return len(
                    list(
                        session.scalars(
                            select(Paragraph)
                            .where(Paragraph.chapter_id == chapter_id)
                            .order_by(Paragraph.paragraph_index)
                        )
                    )
                )

            # Prefer the narrative chapter (most paragraphs / numbered heading), never
            # the stamp-only front-matter split created when a title line is present.
            numbered = [c for c in chapters if c.chapter_number_normalized is not None]
            if numbered:
                chapter = max(numbered, key=lambda c: _chapter_paragraph_count(c.id))
            else:
                chapter = max(chapters, key=lambda c: _chapter_paragraph_count(c.id))
            if chapter is None:
                raise RuntimeError(f"no chapter imported for {fid}")
            # Ensure analyzable chapter section (import may tag untitled single-file as front_matter)
            if getattr(chapter, "section_type", None) != "chapter":
                chapter.section_type = "chapter"
            if not chapter.title or chapter.chapter_number_normalized is None:
                chapter.title = spec.chapter_title
            if hasattr(chapter, "display_title") and (
                not chapter.display_title or chapter.chapter_number_normalized is None
            ):
                chapter.display_title = spec.chapter_title
            if hasattr(chapter, "chapter_title") and not chapter.chapter_title:
                chapter.chapter_title = spec.chapter_title
            session.commit()
            paragraphs = list(
                session.scalars(
                    select(Paragraph)
                    .where(Paragraph.chapter_id == chapter.id)
                    .order_by(Paragraph.paragraph_index)
                )
            )
            if len(paragraphs) < 3:
                raise RuntimeError(
                    f"canary fixture {fid} resolved to metadata-thin chapter "
                    f"id={chapter.id} paragraphs={len(paragraphs)}; aborting"
                )
            text_hash = hashlib.sha256(
                "\n".join(p.normalized_text for p in paragraphs).encode()
            ).hexdigest()
            row = {
                "fixture_id": fid,
                "book_fixture_id": spec.book_key,
                "chapter_fixture_id": fid,
                "book_id": book.id,
                "chapter_id": chapter.id,
                "book_title": spec.book_title,
                "chapter_title": spec.chapter_title,
                "char_count": sum(len(p.raw_text or "") for p in paragraphs),
                "paragraph_count": len(paragraphs),
                "normalized_text_hash": text_hash,
                "narrative": list(spec.narrative_tags),
                "length_band": spec.length_band,
                "certification_purpose": "real_api_full_pipeline",
            }
            chapter_matrix.append(row)
            fixture_to_chapter[fid] = row
        session.commit()
    write_json(AUDITS / "chapter-matrix-v1.json", {"batch_id": batch_id, "chapters": chapter_matrix})

    def wait_run_status(run_id: int, wanted: set[str], timeout_s: float) -> str:
        deadline = time.time() + timeout_s
        last = ""
        while time.time() < deadline:
            with SessionLocal() as session:
                run = session.get(AnalysisRun, run_id)
                last = run.status
                if run.status in wanted or run.status in {
                    "failed",
                    "cancelled",
                    "scene_analysis_partial",
                }:
                    # awaiting_provider_recovery is a recoverable pause — keep polling
                    # until succeeded or a terminal partial/failed status.
                    return run.status
            time.sleep(2)
        return last

    def wait_journey(jid: int, timeout_s: float) -> str:
        deadline = time.time() + timeout_s
        last = ""
        while time.time() < deadline:
            with SessionLocal() as session:
                jr = session.get(ReaderJourneyRun, jid)
                last = jr.status
                if jr.status in {"succeeded", "failed", "cancelled", "scene_profiles_partial"}:
                    return jr.status
            time.sleep(2)
        return last

    def accept_all_boundaries(review_id: int) -> None:
        with SessionLocal() as session:
            decisions = list(
                session.scalars(
                    select(BoundaryReviewDecision).where(
                        BoundaryReviewDecision.review_session_id == review_id,
                        BoundaryReviewDecision.model_candidate.is_(True),
                    )
                )
            )
            for d in decisions:
                body: dict = {"user_decision": "accept"}
                if d.semantic_conflict:
                    body["manual_reason_type"] = "other_manual_boundary"
                    body["user_reason"] = "canary auto-accept with conflict reason"
                resp = client.put(
                    f"/api/v1/boundary-reviews/{review_id}/decisions/{d.transition_id}",
                    json=body,
                )
                if resp.status_code >= 400:
                    # Fall back to reject if accept blocked
                    resp2 = client.put(
                        f"/api/v1/boundary-reviews/{review_id}/decisions/{d.transition_id}",
                        json={"user_decision": "reject"},
                    )
                    if resp2.status_code >= 400:
                        raise RuntimeError(
                            f"decision failed {d.transition_id}: {resp.status_code} {resp.text}"
                        )

    try:
        for plan in CANARY_PLAN:
            run_index = plan["run_index"]
            fid = plan["fixture_id"]
            meta = fixture_to_chapter[fid]
            print(f"=== Canary run {run_index}/8 fixture={fid} ===", flush=True)

            with SessionLocal() as session:
                budget.refresh_from_db(session)
            hit = budget.check_before_run(estimated_next_cost=max(2.0, limits["worst_cost_cny"] / 8))
            if hit:
                stop_reason = hit
                verdict = "REAL_CANARY_ABORTED_BY_LIMIT"
                print(f"LIMIT_REACHED: {hit}", flush=True)
                break

            # Resolve provider_state_version then preflight + create analysis
            providers = client.get("/api/v1/model-providers")
            if providers.status_code >= 400:
                raise RuntimeError(f"providers failed: {providers.status_code} {providers.text}")
            plus = next(p for p in providers.json() if p["name"] == PROVIDER)
            state_ver = plus["provider_state_version"]
            if not plus.get("manual_boundary_candidate_eligible", plus.get("eligible_for_automatic_analysis")):
                # Prefer manual eligibility field when present
                blockers = plus.get("manual_selection_blockers") or plus.get("blockers") or []
                if blockers:
                    raise RuntimeError(f"provider not eligible: {blockers}")

            pre = client.post(
                "/api/v1/analysis-runs/preflight",
                json={
                    "chapter_id": meta["chapter_id"],
                    "provider": PROVIDER,
                    "execution_mode": "cloud",
                    "analysis_mode": "assisted_boundary_review",
                    "cloud_consent": True,
                    "capability_schema_version": "1c-a-2",
                    "provider_state_version": state_ver,
                },
            )
            if pre.status_code >= 400:
                raise RuntimeError(f"preflight failed: {pre.status_code} {pre.text}")
            pre_body = pre.json()
            if not pre_body.get("eligible", True) and pre_body.get("blockers"):
                raise RuntimeError(f"preflight blockers: {pre_body.get('blockers')}")
            create = client.post(
                f"/api/v1/chapters/{meta['chapter_id']}/analysis-runs",
                json={
                    "provider_name": PROVIDER,
                    "execution_mode": "cloud",
                    "analysis_mode": "assisted_boundary_review",
                    "cloud_consent": True,
                    "capability_schema_version": "1c-a-2",
                    "provider_state_version": pre_body.get("provider_state_version") or state_ver,
                    "selected_provider": PROVIDER,
                    "force": True,
                    "client_request_id": f"{batch_id}-r{run_index}-{fid}"[:64],
                },
            )
            if create.status_code >= 400:
                raise RuntimeError(f"create run failed: {create.status_code} {create.text}")
            analysis_run_id = create.json()["run_id"]
            status = wait_run_status(
                analysis_run_id,
                {"awaiting_boundary_review"},
                timeout_s=45 * 60,
            )
            with SessionLocal() as session:
                sync_invocations_to_ledger(
                    session,
                    batch_id=batch_id,
                    fixture_id=fid,
                    book_fixture_id=meta["book_fixture_id"],
                    chapter_fixture_id=meta["chapter_fixture_id"],
                    analysis_run_id=analysis_run_id,
                    reader_journey_run_id=None,
                    ledger_path=ledger_path,
                    seen_ids=seen_inv,
                )
                guard = apply_post_sync_guards(session, budget)
                if guard:
                    stop_reason = guard
                    if guard.startswith("MODEL_"):
                        verdict = "REAL_CANARY_FAILED"
                    else:
                        verdict = "REAL_CANARY_ABORTED_BY_LIMIT"
                    print(f"BATCH_STOP: {guard}", flush=True)
                    break

            if status != "awaiting_boundary_review":
                run_results.append(
                    {
                        "run_index": run_index,
                        "fixture_id": fid,
                        "analysis_run_id": analysis_run_id,
                        "status": "FAIL",
                        "analysis_status": status,
                        "stage": "boundary_candidates",
                    }
                )
                verdict = "REAL_CANARY_FAILED"
                write_run_failure_defect(
                    batch_id=batch_id,
                    run_index=run_index,
                    fixture_id=fid,
                    analysis_run_id=analysis_run_id,
                    journey_run_id=None,
                    stage="boundary_candidates",
                    session_factory=SessionLocal,
                )
                break

            with SessionLocal() as session:
                review = session.scalar(
                    select(BoundaryReviewSession).where(
                        BoundaryReviewSession.analysis_run_id == analysis_run_id
                    )
                )
                review_id = review.id
            accept_all_boundaries(review_id)
            conf = client.post(
                f"/api/v1/boundary-reviews/{review_id}/confirm",
                json={"confirmed_by": "phase-1db2-canary"},
            )
            if conf.status_code >= 400:
                raise RuntimeError(f"confirm failed: {conf.status_code} {conf.text}")

            status = wait_run_status(
                analysis_run_id, {"succeeded"}, timeout_s=60 * 60
            )
            with SessionLocal() as session:
                sync_invocations_to_ledger(
                    session,
                    batch_id=batch_id,
                    fixture_id=fid,
                    book_fixture_id=meta["book_fixture_id"],
                    chapter_fixture_id=meta["chapter_fixture_id"],
                    analysis_run_id=analysis_run_id,
                    reader_journey_run_id=None,
                    ledger_path=ledger_path,
                    seen_ids=seen_inv,
                )
                guard = apply_post_sync_guards(session, budget)
                if guard:
                    stop_reason = guard
                    if guard.startswith("MODEL_"):
                        verdict = "REAL_CANARY_FAILED"
                    else:
                        verdict = "REAL_CANARY_ABORTED_BY_LIMIT"
                    print(f"BATCH_STOP: {guard}", flush=True)
                    break
            if status != "succeeded":
                run_results.append(
                    {
                        "run_index": run_index,
                        "fixture_id": fid,
                        "analysis_run_id": analysis_run_id,
                        "status": "FAIL",
                        "analysis_status": status,
                        "stage": "scene_analysis",
                    }
                )
                verdict = "REAL_CANARY_FAILED"
                write_run_failure_defect(
                    batch_id=batch_id,
                    run_index=run_index,
                    fixture_id=fid,
                    analysis_run_id=analysis_run_id,
                    journey_run_id=None,
                    stage="scene_analysis",
                    session_factory=SessionLocal,
                )
                break

            # Reader journey
            jpre = client.post(
                f"/api/v1/analysis-runs/{analysis_run_id}/reader-journey/preflight",
                json={"cloud_consent": True, "provider_name": PROVIDER},
            )
            if jpre.status_code >= 400:
                raise RuntimeError(f"journey preflight failed: {jpre.status_code} {jpre.text}")
            jbody = jpre.json()
            jcreate = client.post(
                f"/api/v1/analysis-runs/{analysis_run_id}/reader-journey",
                json={
                    "cloud_consent": True,
                    "provider_name": PROVIDER,
                    "provider_state_version": jbody.get("provider_state_version"),
                    "confirmed": True,
                    "force_new_version": True,
                    "client_request_id": f"{batch_id}-j-r{run_index}-{fid}"[:64],
                },
            )
            if jcreate.status_code >= 400:
                raise RuntimeError(f"journey create failed: {jcreate.status_code} {jcreate.text}")
            journey_id = jcreate.json()["journey_run_id"]
            jstatus = wait_journey(journey_id, timeout_s=60 * 60)
            with SessionLocal() as session:
                sync_invocations_to_ledger(
                    session,
                    batch_id=batch_id,
                    fixture_id=fid,
                    book_fixture_id=meta["book_fixture_id"],
                    chapter_fixture_id=meta["chapter_fixture_id"],
                    analysis_run_id=analysis_run_id,
                    reader_journey_run_id=journey_id,
                    ledger_path=ledger_path,
                    seen_ids=seen_inv,
                )
                guard = apply_post_sync_guards(session, budget)
                if guard:
                    stop_reason = guard
                    if guard.startswith("MODEL_"):
                        verdict = "REAL_CANARY_FAILED"
                    else:
                        verdict = "REAL_CANARY_ABORTED_BY_LIMIT"
                    print(f"BATCH_STOP: {guard}", flush=True)
                    break
                scenes = list(
                    session.scalars(
                        select(Scene).where(Scene.created_by_run_id == analysis_run_id)
                    )
                )
                analyses = list(
                    session.scalars(
                        select(AnalysisArtifact).where(
                            AnalysisArtifact.run_id == analysis_run_id,
                            AnalysisArtifact.artifact_type == "scene_analysis",
                        )
                    )
                )
                profiles = list(
                    session.scalars(
                        select(SceneReaderJourneyProfile).where(
                            SceneReaderJourneyProfile.reader_journey_run_id == journey_id
                        )
                    )
                )
                integrity = {
                    "scene_count": len(scenes),
                    "scene_analysis_count": len(analyses),
                    "profile_count": len(profiles),
                    "analysis_status": status,
                    "journey_status": jstatus,
                }

            ok = (
                jstatus == "succeeded"
                and integrity["scene_count"] > 0
                and integrity["scene_analysis_count"] == integrity["scene_count"]
                and integrity["profile_count"] == integrity["scene_count"]
            )
            run_results.append(
                {
                    "run_index": run_index,
                    "fixture_id": fid,
                    "repeat_of": plan["repeat_of"],
                    "analysis_run_id": analysis_run_id,
                    "reader_journey_run_id": journey_id,
                    "status": "PASS" if ok else "FAIL",
                    "analysis_status": status,
                    "journey_status": jstatus,
                    "integrity": integrity,
                    "cost_so_far": budget.cost,
                    "requests_so_far": budget.requests,
                }
            )
            print(
                f"run {run_index} {'PASS' if ok else 'FAIL'} "
                f"scenes={integrity['scene_count']} cost={budget.cost:.4f}",
                flush=True,
            )
            if not ok:
                verdict = "REAL_CANARY_FAILED"
                defect_written = write_run_failure_defect(
                    batch_id=batch_id,
                    run_index=run_index,
                    fixture_id=fid,
                    analysis_run_id=analysis_run_id,
                    journey_run_id=journey_id,
                    stage="reader_journey",
                    session_factory=SessionLocal,
                )
                run_results[-1]["defect"] = defect_written
                break

            # DEFECT-009: inter-run cooldown to reduce clustered remote disconnects
            from app.core.config import get_settings

            cooldown = float(get_settings().canary_inter_run_cooldown_seconds)
            if cooldown > 0 and run_index < 8:
                print(f"inter-run cooldown {cooldown:.1f}s", flush=True)
                time.sleep(cooldown)

            # Main DB invariant mid-batch
            live = snapshot_main_db("mid")
            if live["analysis_run_count"] != 55 or live["reader_journey_run_count"] != 2:
                stop_reason = "main_db_mutated"
                verdict = "REAL_CANARY_FAILED"
                write_json(
                    AUDITS / "defects" / "DEFECT-CANARY-001.json",
                    {
                        "id": "DEFECT-CANARY-001",
                        "severity": "P0",
                        "batch_id": batch_id,
                        "stage": "main_db_guard",
                        "expected": "AnalysisRun=55 JourneyRun=2",
                        "actual": live,
                        "data_risk": True,
                        "cost_risk": True,
                    },
                )
                break

    except Exception as exc:  # noqa: BLE001
        verdict = "REAL_CANARY_FAILED"
        stop_reason = f"exception:{type(exc).__name__}"
        write_json(
            AUDITS / "defects" / "DEFECT-CANARY-002.json",
            {
                "id": "DEFECT-CANARY-002",
                "severity": "P1",
                "batch_id": batch_id,
                "stage": "runner",
                "reproduction": "scripts/run_single_chapter_real_canary.py",
                "expected": "complete 8 runs",
                "actual": str(exc)[:2000],
                "data_risk": False,
                "cost_risk": True,
            },
        )
        print(f"FAIL exception: {exc}", flush=True)

    after = snapshot_main_db("after")
    write_json(
        AUDITS / "main-database-invariance-v1.json",
        {
            "before": before,
            "after": after,
            "unchanged_counts": after.get("analysis_run_count") == 55
            and after.get("reader_journey_run_count") == 2,
            "sha_equal": before.get("sha256") == after.get("sha256"),
        },
    )
    write_json(AUDITS / "run-results-v1.json", {"batch_id": batch_id, "runs": run_results})
    write_json(
        AUDITS / "cost-report-v1.json",
        {
            "batch_id": batch_id,
            "requests": budget.requests,
            "retries": budget.retries,
            "input_tokens": budget.input_tokens,
            "output_tokens": budget.output_tokens,
            "estimated_cost_cny": budget.cost,
            "actual_reported_cost": budget.actual_reported_cost,
            "conservative_estimated_cost": budget.conservative_estimated_cost,
            "certification_accounted_cost": budget.certification_accounted_cost,
            "max_cost_cny": limits["max_cost_cny"],
            "within_budget": budget.certification_accounted_cost <= limits["max_cost_cny"],
            "elapsed_minutes": budget.elapsed_minutes(),
            "stop_reason": stop_reason,
            "unknown_accounting_count": budget.unknown_accounting_count,
            "accounting_summary": {
                "reported_count": (budget.latest_accounting_summary or {}).get("reported_count"),
                "conservative_count": (budget.latest_accounting_summary or {}).get(
                    "conservative_count"
                ),
                "unknown_count": budget.unknown_accounting_count,
            },
        },
    )

    if len([r for r in run_results if r.get("status") == "PASS"]) < 8 and verdict == "REAL_CANARY_PASSED":
        verdict = "REAL_CANARY_FAILED"
    if stop_reason and (
        stop_reason.startswith("max_") or stop_reason in {"accounting_unknown", "token_stats_missing"}
    ):
        verdict = "REAL_CANARY_ABORTED_BY_LIMIT"

    defect_files = sorted((AUDITS / "defects").glob("DEFECT-CANARY-*.json"))
    defect_id = defect_files[-1].stem if defect_files else None

    # Archive this batch under batches/<batch_id>/ and keep top-level mirrors.
    batch_dir = AUDITS / "batches" / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "defects").mkdir(parents=True, exist_ok=True)
    for name in (
        "authorization-v13.json",
        "batch-manifest-v1.json",
        "chapter-matrix-v1.json",
        "model-call-ledger-v1.jsonl",
        "run-results-v1.json",
        "cost-report-v1.json",
        "main-database-invariance-v1.json",
    ):
        src = AUDITS / name
        if src.exists():
            (batch_dir / name).write_bytes(src.read_bytes())
    # authorization already in AUDITS
    if AUTH.exists():
        (AUDITS / "authorization-v13.json").write_bytes(AUTH.read_bytes())
        (batch_dir / "authorization-v13.json").write_bytes(AUTH.read_bytes())
    for defect in (AUDITS / "defects").glob("*.json"):
        (batch_dir / "defects" / defect.name).write_bytes(defect.read_bytes())

    final_payload = {
        "batch_id": batch_id,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "completed_pass_runs": len([r for r in run_results if r.get("status") == "PASS"]),
        "planned_runs": 8,
        "provider": PROVIDER,
        "model": MODEL,
        "allow_auto_route": False,
        "max_cost_cny": limits["max_cost_cny"],
        "actual_cost_cny": budget.cost,
        "actual_reported_cost": budget.actual_reported_cost,
        "conservative_estimated_cost": budget.conservative_estimated_cost,
        "certification_accounted_cost": budget.certification_accounted_cost,
        "phase_1d_c_allowed": verdict == "REAL_CANARY_PASSED",
        "finished_at": utc_now(),
        "defect": defect_id,
        "superseded_by_future_batch": False,
        "change_package": CHANGE_PACKAGE,
        "progress_summary": {
            "completed_pass_runs": len([r for r in run_results if r.get("status") == "PASS"]),
            "failed_run": next(
                (r.get("fixture_id") for r in run_results if r.get("status") == "FAIL"),
                None,
            ),
            "reader_journey_evidence_budget": "v1.1.1",
            "reader_journey_scene_prompt": "v1.6",
            "global_model_invocation_policy": "v1.1.0",
            "scene_analysis_provider_recovery": "v1.0.9",
            "canary_conservative_usage_accounting": "v1.0.8",
            "journey_adaptive_phase_contract": "v1.0.7",
            "reader_journey_chapter_prompt": "v1.2",
            "reader_journey_chapter_contract": "1.2",
            "evidence_paragraph_ids_max_items": 16,
        },
    }
    write_json(AUDITS / "final-verdict-v1.json", final_payload)
    write_json(batch_dir / "final-verdict-v1.json", final_payload)
    print(f"FINAL_VERDICT={verdict}", flush=True)
    return 0 if verdict == "REAL_CANARY_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
