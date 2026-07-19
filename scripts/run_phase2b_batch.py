import asyncio
import hashlib
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    ApplicationSetting,
    Chapter,
    ModelInvocation,
    Paragraph,
    ProviderConfiguration,
    RequestGateDecision,
    Scene,
)
from app.db.session import SessionLocal
from app.model_gateway.base import ModelProvider, ModelRequest, ModelResponse, ProviderHealth
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.schemas.scene import (
    CompactTransitionClassificationResultV35,
    BoundaryCandidateAdjudicationResult,
    SceneAnalysisResult,
)
from app.schemas.settings import CloudBudgetUpdate
from app.services.cloud_budget import RequestBlockedError, daily_usage
from app.services.budget_reservation import release_reservation, reserve_budget
from app.services.cloud_pricing import estimate_cost, pricing_status
from app.services.credentials.keyring_store import KeyringCredentialStore
from app.services.prompt_service import load_prompt
from app.services.scene_pipeline import (
    evidence_fields,
    execute_scene_pipeline,
    validate_scene_analysis,
)
from app.services.structured_output import generate_validated
from app.services.fixture_service import get_or_create_fixture_book
from app.services.scene_transitions import build_adjacent_transitions
from app.services.transition_batch_planner import plan_transition_batches
from app.services.scene_boundary_adjudicator import (
    adjudicated_to_canonical,
    adjudication_snapshot,
    plan_adjudication_batches,
    validate_adjudication,
    validate_candidate_detection,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "fixtures" / "local_model_calibration"
OUTPUT = ROOT / "data" / "runtime" / "aliyun" / "phase2b_batch.json"
PRICING = ROOT / "config" / "cloud_pricing.json"
NAMES = [
    "no_boundary",
    "clear_location_change",
    "goal_change",
    "prompt_injection_text",
    "time_jump_same_location",
    "dialogue_continuation",
    "short_flashback",
    "object_triggered_goal_change",
]
MAX_REQUESTS, MAX_TOKENS, MAX_COST = 58, 120000, 0.70
TARGET_NAMES = ["goal_change", "time_jump_same_location", "object_triggered_goal_change"]
REGRESSION_NAMES = [
    "no_boundary",
    "clear_location_change",
    "prompt_injection_text",
    "dialogue_continuation",
    "short_flashback",
]


class BatchBudgetExceeded(RequestBlockedError):
    pass


class BatchState:
    def __init__(self, pricing_version: str):
        self.requests = self.input_tokens = self.output_tokens = self.total_tokens = 0
        self.cost = 0.0
        self.latencies: list[int] = []
        self.pricing_version = pricing_version
        self.http_failures = 0
        self.results: dict[str, object] = {"fixtures": []}

    def checkpoint(self):
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        self.results["batch_usage"] = {
            "requests": self.requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.cost,
            "latencies_ms": self.latencies,
        }
        OUTPUT.write_text(json.dumps(self.results, ensure_ascii=False, indent=2), encoding="utf-8")

    def before(self):
        if (
            self.requests >= MAX_REQUESTS
            or self.total_tokens >= MAX_TOKENS
            or self.cost >= MAX_COST
        ):
            with SessionLocal() as s:
                s.add(
                    RequestGateDecision(
                        allowed=False,
                        reason_code="BATCH_VALIDATION_BUDGET_EXCEEDED",
                        budget_snapshot_json=json.dumps(
                            {
                                "requests": self.requests,
                                "tokens": self.total_tokens,
                                "cost": self.cost,
                            }
                        ),
                    )
                )
                s.commit()
            raise BatchBudgetExceeded("BATCH_VALIDATION_BUDGET_EXCEEDED")
        with SessionLocal() as s:
            cloud = s.get(ApplicationSetting, "cloud_enabled")
            budget_row = s.get(ApplicationSetting, "cloud_budget_settings")
            enabled = bool(json.loads(cloud.value_json)) if cloud else False
            budget = CloudBudgetUpdate.model_validate(
                json.loads(budget_row.value_json) if budget_row else {}
            ).model_dump()
            pricing = pricing_status(PRICING)
            usage = daily_usage(s, budget, enabled, pricing)
            if (
                not enabled
                or not budget["cloud_request_budget_enabled"]
                or not pricing["enabled"]
                or not usage["within_budget"]
            ):
                s.add(
                    RequestGateDecision(
                        allowed=False,
                        reason_code="CLOUD_BUDGET_EXCEEDED",
                        budget_snapshot_json=json.dumps(usage, ensure_ascii=False),
                    )
                )
                s.commit()
                raise BatchBudgetExceeded("BATCH_VALIDATION_BUDGET_EXCEEDED")
            s.add(
                RequestGateDecision(
                    allowed=True,
                    reason_code="REQUEST_ALLOWED",
                    budget_snapshot_json=json.dumps(usage, ensure_ascii=False),
                )
            )
            s.commit()
        self.requests += 1
        self.checkpoint()

    def after(self, response: ModelResponse, model_for_price: str, latency: int):
        self.input_tokens += response.input_tokens or 0
        self.output_tokens += response.output_tokens or 0
        self.total_tokens += response.total_tokens or 0
        cost, _, _ = estimate_cost(
            model_for_price, response.input_tokens, response.output_tokens, PRICING
        )
        self.cost += cost or 0.0
        self.latencies.append(latency)
        self.http_failures = 0
        self.checkpoint()
        if self.total_tokens > MAX_TOKENS or self.cost > MAX_COST:
            raise BatchBudgetExceeded("BATCH_VALIDATION_BUDGET_EXCEEDED")


class ControlledProvider(ModelProvider):
    def __init__(self, delegate: OpenAICompatibleProvider, state: BatchState):
        self.delegate, self.state = delegate, state
        self.name, self.default_model = delegate.name, delegate.default_model

    def capabilities(self):
        return self.delegate.capabilities()

    async def health(self):
        return ProviderHealth(provider_name=self.name, status="healthy")

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.state.before()
        started = time.perf_counter()
        try:
            response = await self.delegate.generate(request)
        except Exception:
            self.state.http_failures += 1
            self.state.latencies.append(int((time.perf_counter() - started) * 1000))
            self.state.checkpoint()
            if self.state.http_failures >= 2:
                raise BatchBudgetExceeded("two consecutive provider failures")
            raise
        self.state.after(response, self.default_model, int((time.perf_counter() - started) * 1000))
        return response


def fixture_payload(path: Path):
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return lines[0], [
        {"id": f"B0001-C0001-P{i:04d}", "text": line} for i, line in enumerate(lines[1:], 1)
    ]


def expectations(name: str, count: int):
    data = json.loads((FIXTURES / f"{name}.expected.json").read_text(encoding="utf-8"))
    if "expected_after_paragraph_indexes" in data:
        expected = {f"B0001-C0001-P{i:04d}" for i in data["expected_after_paragraph_indexes"]}
    else:
        expected = set(
            data.get("expected_boundaries", data.get("expected_internal_boundaries", []))
        )
    allowed = set(data.get("allowed_boundaries", expected))
    forbidden = set(data.get("forbidden_boundaries", []))
    valid = {f"B0001-C0001-P{i:04d}" for i in range(1, count + 1)}
    return expected, allowed, forbidden, valid


def new_run(session, name: str, model: str, subject_type="fixture", subject_id=None):
    run = AnalysisRun(
        task_type="phase2b_calibration",
        subject_type=subject_type,
        subject_id=subject_id or name,
        provider="aliyun_qwen_plus",
        model=model,
        prompt_version="v3.5",
        schema_version="v1",
        input_hash=hashlib.sha256(name.encode()).hexdigest(),
        prompt_hash="phase2b-v3.5",
        status="running",
        execution_mode="cloud",
        cloud_consent=True,
        cloud_consent_at=datetime.now(timezone.utc),
        sends_content_to_cloud=True,
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.commit()
    return run


def invocation_stats(session, run_id):
    rows = list(
        session.scalars(
            select(ModelInvocation)
            .where(ModelInvocation.run_id == run_id)
            .order_by(ModelInvocation.id)
        )
    )
    first = rows[0] if rows else None
    return rows, {
        "invocation_count": sum(r.http_request_sent for r in rows),
        "audit_record_count": len(rows),
        "pre_send_failure_count": sum(not r.http_request_sent for r in rows),
        "repair_count": sum(
            r.invocation_kind
            in {
                "json_repair",
                "schema_repair",
                "evidence_repair",
                "business_repair",
                "truncation_retry",
            }
            for r in rows
        ),
        "truncation_retry_count": sum(
            r.invocation_kind == "truncation_retry" for r in rows
        ),
        "json_repair_count": sum(r.invocation_kind == "json_repair" for r in rows),
        "schema_repair_count": sum(r.invocation_kind == "schema_repair" for r in rows),
        "evidence_repair_count": sum(
            r.invocation_kind == "evidence_repair" for r in rows
        ),
        "business_repair_count": sum(
            r.invocation_kind == "business_repair" for r in rows
        ),
        "candidate_detection_count": sum(
            r.invocation_kind == "boundary_candidate_detection" for r in rows
        ),
        "candidate_adjudication_count": sum(
            r.invocation_kind == "boundary_candidate_adjudication" for r in rows
        ),
        "first_json_valid": bool(first and first.parsed_response_json),
        "first_schema_valid": bool(
            first
            and first.parsed_response_json
            and first.error_code
            not in {
                "VALIDATION_ERROR",
                "SCHEMA_VALIDATION_FAILED",
                "OUTPUT_TRUNCATED",
            }
        ),
        "input_tokens": sum(r.input_tokens or 0 for r in rows),
        "output_tokens": sum(r.output_tokens or 0 for r in rows),
        "total_tokens": sum(r.total_tokens or 0 for r in rows),
        "latency_ms": sum(r.latency_ms for r in rows),
        "estimated_cost": sum(r.estimated_cost or 0 for r in rows),
    }


async def run_fixture(state, gateway, name):
    title, paragraphs = fixture_payload(FIXTURES / f"{name}.txt")
    expected, allowed, forbidden, valid = expectations(name, len(paragraphs))
    prompt = load_prompt("scene_boundary", "v3.5")
    candidates = build_adjacent_transitions([item["id"] for item in paragraphs])
    batches = plan_transition_batches(candidates, contract_version="3.5")
    paragraph_by_id = {item["id"]: item for item in paragraphs}
    with SessionLocal() as s:
        run = new_run(s, name, gateway.get("aliyun_qwen_plus").default_model)
        result = None
        failure = None
        decisions = []
        adjudication_audit = []
        batch_audit = []
        try:
            for batch in batches:
                owned = [
                    item
                    for item in candidates
                    if item.transition_id in batch.owned_transition_ids
                ]
                snapshot = {
                    "chapter_id": "B0001-C0001",
                    "title": title,
                    "paragraphs": [
                        paragraph_by_id[item]
                        for item in batch.context_paragraph_ids
                        if item in paragraph_by_id
                    ],
                    "transitions": [item.as_dict() for item in owned],
                    "owned_transition_ids": list(batch.owned_transition_ids),
                }
                before_count = s.scalar(
                    select(func.count())
                    .select_from(ModelInvocation)
                    .where(ModelInvocation.run_id == run.id)
                )
                compact_result = await generate_validated(
                    session=s,
                    gateway=gateway,
                    run_id=run.id,
                    provider_name="aliyun_qwen_plus",
                    task_type="scene_boundary",
                    prompt=prompt,
                    schema=CompactTransitionClassificationResultV35,
                    input_snapshot=snapshot,
                    user_content=prompt.user_template.format(
                        input_json=json.dumps(snapshot, ensure_ascii=False)
                    ),
                    business_validator=lambda value, batch=batch: validate_candidate_detection(
                        value.decisions, list(batch.owned_transition_ids)
                    ),
                    initial_invocation_kind="boundary_candidate_detection",
                )
                decisions.extend(compact_result.decisions)
                after_count = s.scalar(
                    select(func.count())
                    .select_from(ModelInvocation)
                    .where(ModelInvocation.run_id == run.id)
                )
                batch_audit.append(
                    {
                        "owned_transition_ids": list(batch.owned_transition_ids),
                        "request_count": after_count - before_count,
                        "worst_case_output_tokens": batch.worst_case_output_tokens,
                    }
                )
            candidate_ids = [
                item.transition_id for item in decisions if item.boundary_candidate
            ]
            adjudication_batches = plan_adjudication_batches(
                candidate_ids,
                candidates,
                {item["id"]: item["text"] for item in paragraphs},
            )
            verdicts = []
            adjudication_prompt = load_prompt("scene_boundary_adjudication", "v1")
            for adjudication_batch in adjudication_batches:
                adjudication_input = adjudication_snapshot(
                    chapter_id="B0001-C0001",
                    title=title,
                    batch=adjudication_batch,
                    candidates=candidates,
                    decisions=decisions,
                    paragraph_text={item["id"]: item["text"] for item in paragraphs},
                )
                adjudicated = await generate_validated(
                    session=s,
                    gateway=gateway,
                    run_id=run.id,
                    provider_name="aliyun_qwen_plus",
                    task_type="scene_boundary_adjudication",
                    prompt=adjudication_prompt,
                    schema=BoundaryCandidateAdjudicationResult,
                    input_snapshot=adjudication_input,
                    user_content=adjudication_prompt.user_template.format(
                        input_json=json.dumps(adjudication_input, ensure_ascii=False)
                    ),
                    business_validator=lambda value, adjudication_batch=adjudication_batch: validate_adjudication(
                        value, list(adjudication_batch.candidate_transition_ids)
                    ),
                    initial_invocation_kind="boundary_candidate_adjudication",
                )
                verdicts.extend(adjudicated.verdicts)
                adjudication_audit.append(
                    {
                        "candidate_transition_ids": list(
                            adjudication_batch.candidate_transition_ids
                        ),
                        "context_paragraph_ids": list(
                            adjudication_batch.context_paragraph_ids
                        ),
                        "verdicts": [item.model_dump(mode="json") for item in adjudicated.verdicts],
                    }
                )
            result = adjudicated_to_canonical(
                chapter_id="B0001-C0001",
                decisions=decisions,
                verdicts=BoundaryCandidateAdjudicationResult(
                    contract_version="1.0", verdicts=verdicts
                ),
                candidates=candidates,
                allowed_paragraph_ids={item["id"] for item in paragraphs},
            )
            run.status = "succeeded"
        except Exception as exc:
            failure = type(exc).__name__
            run.status = "failed"
            run.root_error_code = failure
        run.completed_at = datetime.now(timezone.utc)
        s.commit()
        actual = {b.after_paragraph_id for b in result.boundaries} if result else set()
        illegal = actual - valid
        rows, stats = invocation_stats(s, run.id)
        row = {
            "name": name,
            "expected_boundaries": sorted(expected),
            "allowed_boundaries": sorted(allowed),
            "forbidden_boundaries": sorted(forbidden),
            "predicted_boundaries": sorted(actual),
            "tp": len(actual & expected),
            "fp": len(actual - allowed),
            "fn": len(expected - actual),
            "illegal_paragraph_ids": sorted(illegal),
            "final_json_valid": result is not None,
            "final_schema_valid": result is not None,
            "scene_coverage_rate": 1.0 if result is not None else 0.0,
            "prompt_injection_safe": name != "prompt_injection_text" or not illegal,
            "passed": result is not None and not (actual - allowed) and not (expected - actual),
            "failure": failure,
            "transition_count": len(candidates),
            "batch_count": len(batches),
            "batch_audit": batch_audit,
            "first_pass_candidates": [
                item.model_dump(mode="json") for item in decisions if item.boundary_candidate
            ],
            "adjudication_audit": adjudication_audit,
            "transition_coverage_rate": (
                sum(len(item["owned_transition_ids"]) for item in batch_audit)
                / len(candidates)
                if candidates
                else 1.0
            ),
            "merge_conflict_count": 0,
            **stats,
        }
        state.results["fixtures"].append(row)
        state.checkpoint()


def validate_fixture_boundary(value, paragraphs, valid):
    if value.chapter_id != "B0001-C0001":
        raise ValueError("chapter id mismatch")
    ids = [b.after_paragraph_id for b in value.boundaries]
    if (
        len(ids) != len(set(ids))
        or any(i not in valid for i in ids)
        or (paragraphs and ids and ids[-1] == paragraphs[-1]["id"])
    ):
        raise ValueError("invalid paragraph id")
    for boundary in value.boundaries:
        if not boundary.reason_code or not boundary.reason_summary.strip():
            raise ValueError("boundary reason contract incomplete")
        if (
            not boundary.previous_scene_end_state.strip()
            or not boundary.next_scene_start_state.strip()
        ):
            raise ValueError("boundary transition contract incomplete")


async def run_scene_analysis(state, gateway):
    title, paragraphs = fixture_payload(FIXTURES / "no_boundary.txt")
    scene_id = "B0001-C0001-S0001"
    prompt = load_prompt("scene_analysis", "v3.1")
    snapshot = {"scene_id": scene_id, "title": title, "paragraphs": paragraphs}
    with SessionLocal() as s:
        run = new_run(s, "scene_analysis_original", gateway.get("aliyun_qwen_plus").default_model)
        result = None
        failure = None
        try:
            result = await generate_validated(
                session=s,
                gateway=gateway,
                run_id=run.id,
                provider_name="aliyun_qwen_plus",
                task_type="scene_analysis",
                prompt=prompt,
                schema=SceneAnalysisResult,
                input_snapshot=snapshot,
                user_content=prompt.user_template.format(
                    input_json=json.dumps(snapshot, ensure_ascii=False)
                ),
                business_validator=lambda value: validate_scene_analysis(
                    value, scene_id, {p["id"] for p in paragraphs}, True
                ),
            )
            run.status = "succeeded"
        except Exception as exc:
            failure = type(exc).__name__
            run.status = "failed"
            run.root_error_code = failure
        run.completed_at = datetime.now(timezone.utc)
        s.commit()
        _, stats = invocation_stats(s, run.id)
        evidence = [pid for _, pid in evidence_fields(result)] if result else []
        state.results["scene_analysis"] = {
            "passed": result is not None,
            "fields_complete": bool(
                result
                and result.entry_state
                and result.goal
                and result.obstacle
                and result.key_actions
                and result.turning_point
                and result.outcome
                and result.unresolved_question
                and result.function_tags
            ),
            "illegal_evidence": sorted(set(evidence) - {p["id"] for p in paragraphs}),
            "failure": failure,
            **stats,
        }
        state.checkpoint()


def seed_story(session, model):
    path = ROOT / "data" / "fixtures" / "cloud_validation" / "original_short_story.txt"
    title, items = fixture_payload(path)
    book, _ = get_or_create_fixture_book(
        session,
        fixture_name="phase2b_original_short_story",
        fixture_version="1",
        title=title,
        paragraphs=[item["text"] for item in items],
        source_file_name=path.name,
    )
    chapter = session.scalar(
        select(Chapter).where(Chapter.book_id == book.id, Chapter.chapter_index == 1)
    )
    run = new_run(session, "original_short_story", model, "chapter", str(chapter.id))
    run.task_type = "scene_pipeline"
    session.commit()
    return run


async def run_full_pipeline(state, gateway):
    with SessionLocal() as s:
        run = seed_story(s, gateway.get("aliyun_qwen_plus").default_model)
        run_id = run.id
    await execute_scene_pipeline(SessionLocal, gateway, run_id)
    with SessionLocal() as s:
        run = s.get(AnalysisRun, run_id)
        scenes = list(
            s.scalars(
                select(Scene).where(Scene.created_by_run_id == run_id).order_by(Scene.ordinal)
            )
        )
        inv, stats = invocation_stats(s, run_id)
        paragraphs = list(
            s.scalars(
                select(Paragraph)
                .where(Paragraph.chapter_id == int(run.subject_id))
                .order_by(Paragraph.paragraph_index)
            )
        )
        covered = []
        pos = {p.id: i for i, p in enumerate(paragraphs)}
        for scene in scenes:
            covered.extend(
                paragraphs[pos[scene.start_paragraph_id] : pos[scene.end_paragraph_id] + 1]
            )
        artifacts = (
            s.scalar(
                select(func.count())
                .select_from(AnalysisArtifact)
                .where(AnalysisArtifact.run_id == run_id)
            )
            or 0
        )
        evidence = list(
            s.scalars(
                select(AnalysisEvidence)
                .join(AnalysisArtifact)
                .where(AnalysisArtifact.run_id == run_id)
            )
        )
        valid_ids = {p.id for p in paragraphs}
        state.results["full_run"] = {
            "run_id": run_id,
            "status": run.status,
            "scene_count": len(scenes),
            "continuous_coverage": [p.id for p in covered] == [p.id for p in paragraphs],
            "artifact_count": artifacts,
            "evidence_count": len(evidence),
            "illegal_evidence": sum(e.paragraph_id not in valid_ids for e in evidence),
            "cloud_consent": run.cloud_consent,
            "failed_stage": run.failed_stage,
            "root_error_code": run.root_error_code,
            "failed_invocation_id": run.failed_invocation_id,
            "retryable": run.retryable,
            "user_action_hint": run.user_action_hint,
            **stats,
        }
        state.checkpoint()


def metrics(state):
    rows = state.results["fixtures"]
    tp = sum(r["tp"] for r in rows)
    fp = sum(r["fp"] for r in rows)
    fn = sum(r["fn"] for r in rows)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    lats = sorted(state.latencies)

    def pct(fraction):
        return lats[min(len(lats) - 1, round((len(lats) - 1) * fraction))] if lats else 0

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
        "first_json_valid_rate": statistics.mean(r["first_json_valid"] for r in rows),
        "final_json_valid_rate": statistics.mean(r["final_json_valid"] for r in rows),
        "first_schema_valid_rate": statistics.mean(r["first_schema_valid"] for r in rows),
        "final_schema_valid_rate": statistics.mean(r["final_schema_valid"] for r in rows),
        "average_invocations": statistics.mean(r["invocation_count"] for r in rows),
        "repair_rate": statistics.mean(r["repair_count"] > 0 for r in rows),
        "truncation_retry_rate": statistics.mean(
            r["truncation_retry_count"] > 0 for r in rows
        ),
        "illegal_evidence_count": sum(len(r["illegal_paragraph_ids"]) for r in rows),
        "scene_coverage_rate": statistics.mean(r["scene_coverage_rate"] for r in rows),
        "prompt_injection_protection_rate": next(
            (
                r["prompt_injection_safe"]
                for r in rows
                if r["name"] == "prompt_injection_text"
            ),
            None,
        ),
        "p50_latency_ms": pct(0.5),
        "p95_latency_ms": pct(0.95),
    }


async def main():
    if os.getenv("STORYLENS_RUN_ALIYUN_TESTS") != "1":
        raise SystemExit("paid test authorization missing")
    with SessionLocal() as s:
        cfg = s.scalar(
            select(ProviderConfiguration).where(
                ProviderConfiguration.provider_name == "aliyun_qwen_plus"
            )
        )
        key = KeyringCredentialStore().get("aliyun_qwen_plus")
        if not cfg or not cfg.enabled or cfg.disconnected or not key:
            raise SystemExit("provider gate failed")
    pricing = pricing_status(PRICING)
    if not pricing["enabled"]:
        raise SystemExit("pricing gate failed")
    state = BatchState(str(pricing["pricing_version"]))
    def reserve_stage(requests, tokens, cost):
        with SessionLocal() as s:
            cloud = s.get(ApplicationSetting, "cloud_enabled")
            budget_row = s.get(ApplicationSetting, "cloud_budget_settings")
            budget = CloudBudgetUpdate.model_validate(
                json.loads(budget_row.value_json)
            ).model_dump()
            usage = daily_usage(s, budget, bool(json.loads(cloud.value_json)), pricing)
            return reserve_budget(
                s,
                run_id=None,
                required_requests=requests,
                required_tokens=tokens,
                required_cost=cost,
                remaining_requests=usage["remaining_requests"],
                remaining_tokens=usage["remaining_tokens"],
                remaining_cost=usage["remaining_estimated_cost"],
            )

    reservations = []
    fixture_batch_count = 0
    for fixture_name in NAMES:
        _, fixture_paragraphs = fixture_payload(FIXTURES / f"{fixture_name}.txt")
        fixture_batch_count += len(
            plan_transition_batches(
                build_adjacent_transitions([item["id"] for item in fixture_paragraphs])
                , contract_version="3.5"
            )
        )
    story_path = ROOT / "data" / "fixtures" / "cloud_validation" / "original_short_story.txt"
    _, story_paragraphs = fixture_payload(story_path)
    story_batch_count = len(
        plan_transition_batches(
            build_adjacent_transitions([item["id"] for item in story_paragraphs])
            , contract_version="3.5"
        )
    )
    with SessionLocal() as s:
        prior_fixture_scene_count = (
            s.scalar(
                select(func.count())
                .select_from(Scene)
                .join(AnalysisRun, Scene.created_by_run_id == AnalysisRun.id)
                .where(
                    AnalysisRun.task_type == "scene_pipeline",
                    AnalysisRun.status == "succeeded",
                    AnalysisRun.prompt_version.in_(["v3.1", "v3.2"]),
                )
            )
            or 0
        )
    if prior_fixture_scene_count <= 0:
        raise SystemExit("no audited prior fixture scene count for worst-case reservation")
    adjudication_worst_batches = len(NAMES) + 1
    worst_requests = 2 * (
        fixture_batch_count
        + story_batch_count
        + adjudication_worst_batches
        + prior_fixture_scene_count
    )
    if worst_requests > MAX_REQUESTS:
        raise SystemExit("calculated worst-case requests exceed batch hard limit")
    goal_batch_count = len(
        plan_transition_batches(
            build_adjacent_transitions(
                [
                    item["id"]
                    for item in fixture_payload(FIXTURES / "goal_change.txt")[1]
                ]
            ),
            contract_version="3.5",
        )
    )
    first_stage_requests = goal_batch_count * 2 + 2
    second_stage_requests = worst_requests - first_stage_requests
    if first_stage_requests > 8 or second_stage_requests > 50:
        raise SystemExit("calculated stage worst-case requests exceed Phase 2B.8 limits")
    reservation = reserve_stage(8, 20000, 0.10)
    reservations.append(reservation.id)
    base = (
        cfg.base_url
        or f"https://{cfg.workspace_id}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    )

    def provider(name, model, manual=False):
        return ControlledProvider(
            OpenAICompatibleProvider(
                name=name,
                base_url=base,
                api_key=key,
                default_model=model,
                timeout_seconds=cfg.timeout_seconds,
                max_context_tokens=1_000_000,
                enabled=True,
                manual_only=manual,
                structured_output_mode="json_object",
                supports_thinking_control=True,
                cloud=True,
                provider_family="aliyun_qwen",
                supports_json_object=True,
                sends_content_to_cloud=True,
                region=cfg.region,
            ),
            state,
        )

    gateway = ModelGateway(
        [
            provider("aliyun_qwen_plus", cfg.plus_model),
            provider("aliyun_qwen_flash", cfg.flash_model, True),
        ]
    )
    try:
        await run_fixture(state, gateway, "goal_change")
        state.results["stage_one_passed"] = state.results["fixtures"][0]["passed"]
        with SessionLocal() as s:
            release_reservation(s, reservation.id)
        if not state.results["stage_one_passed"]:
            state.results["metrics"] = metrics(state)
            state.checkpoint()
            print(json.dumps(state.results, ensure_ascii=False))
            return
        reservation = reserve_stage(50, 100000, 0.60)
        reservations.append(reservation.id)
        for name in [
            "no_boundary",
            "clear_location_change",
            "prompt_injection_text",
            "time_jump_same_location",
            "dialogue_continuation",
            "short_flashback",
            "object_triggered_goal_change",
        ]:
            await run_fixture(state, gateway, name)
        await run_full_pipeline(state, gateway)
        state.results["metrics"] = metrics(state)
        state.checkpoint()
        print(json.dumps(state.results, ensure_ascii=False))
    finally:
        with SessionLocal() as s:
            for reservation_id in reservations:
                release_reservation(s, reservation_id)


if __name__ == "__main__":
    asyncio.run(main())
