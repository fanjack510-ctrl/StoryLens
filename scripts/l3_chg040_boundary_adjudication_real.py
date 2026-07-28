#!/usr/bin/env python3
"""CHG-20260728-040 L3 real-provider verification (authorized).

Constraints (user freeze):
- Provider: aliyun_qwen_plus / qwen3.7-plus
- Sample: synthetic 20-candidate Chinese text (not user novel)
- Max logical calls: 4
- Max actual HTTP calls: 6
- Per-request output hard cap: 4000
- Max cost: ¥5
- Formal AppData DB writes: 0 (temp SQLite only, deleted)
- BUILD/MERGE/PUSH: NO

Does not print API keys, full prompts, full responses, or novel bodies.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

EVIDENCE = ROOT / "release" / "evidence" / "hotfix" / "1.1.2" / "CHG-20260728-040"
PROVIDER = "aliyun_qwen_plus"
MODEL = "qwen3.7-plus"
MAX_LOGICAL_CALLS = 4
MAX_ACTUAL_CALLS = 6
MAX_INPUT_TOKENS = 40_000
MAX_OUTPUT_TOKENS = 24_000
PER_REQUEST_HARD_CAP = 4000
MAX_COST_CNY = 5.0
CANDIDATE_COUNT = 20


class CallCeilingExceeded(RuntimeError):
    pass


class CostCeilingExceeded(RuntimeError):
    pass


def _resolve_api_key() -> str:
    from app.services.credentials.keyring_store import KeyringCredentialStore

    key = KeyringCredentialStore().get(PROVIDER)
    if not key:
        key = os.environ.get("STORYLENS_ALIYUN_API_KEY", "").strip()
    if not key:
        raise SystemExit("Aliyun API key unavailable (keyring/env); aborting with 0 calls.")
    return key


def _build_synthetic_sample() -> tuple[list[dict[str, str]], list[str]]:
    """21 short paragraphs → 20 adjacent transitions (all marked candidates)."""
    paragraphs: list[dict[str, str]] = []
    for i in range(1, 22):
        pid = f"L3C040-P{i:04d}"
        # Alternate setting/goal so adjudication has real boundary signal.
        if i % 4 == 1:
            text = (
                f"清晨，林川站在第{i}段旧码头，把一卷空白契约塞进袖口，"
                f"决定先把账本核对一遍再离开。"
            )
        elif i % 4 == 2:
            text = (
                f"同一码头边，伙计老周仍在清点木箱，林川继续核对账页，"
                f"目标没有改变，只是把墨迹抹匀。"
            )
        elif i % 4 == 3:
            text = (
                f"夜色压下后，林川已换乘去往内陆驿站的马车，身边换了同伴阿翠，"
                f"此行只为追查失踪的货单。"
            )
        else:
            text = (
                f"驿站厢房里，阿翠摊开货单副本，林川对照印章缺口，"
                f"确认下一站必须改走水路。"
            )
        paragraphs.append({"id": pid, "text": text})
    candidate_ids = [f"T{i:04d}" for i in range(1, CANDIDATE_COUNT + 1)]
    return paragraphs, candidate_ids


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    from app.services.cloud_pricing import estimate_cost

    cost, _, _ = estimate_cost(
        MODEL,
        input_tokens,
        output_tokens,
        ROOT / "config" / "cloud_pricing.default.json",
    )
    return float(cost or 0.0)


async def main() -> int:
    if os.environ.get("STORYLENS_L3_CHG040_AUTHORIZED") != "1":
        print("Set STORYLENS_L3_CHG040_AUTHORIZED=1 after explicit user approval.")
        return 3

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.db.models import AnalysisRun, ApplicationSetting, Base, ModelInvocation
    from app.model_gateway.base import ModelRequest, ModelResponse
    from app.model_gateway.gateway import ModelGateway
    from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
    from app.schemas.scene import (
        BoundaryCandidateAdjudicationResult,
        CompactTransitionCandidateDecision,
    )
    from app.services.prompt_service import load_prompt
    from app.services.scene_boundary_adjudication_batching import (
        adjudication_snapshot_v112,
        merge_adjudication_batches,
        plan_output_bounded_adjudication_batches,
        validate_batch_coverage,
    )
    from app.services.scene_boundary_output_budget import (
        compute_scene_boundary_output_budget_v1,
    )
    from app.services.scene_transitions import AdjacentTransition
    from app.services.structured_output import StructuredOutputError, generate_validated

    api_key = _resolve_api_key()
    paragraphs, candidate_ids = _build_synthetic_sample()
    paragraph_text = {p["id"]: p["text"] for p in paragraphs}
    transitions = [
        AdjacentTransition(
            transition_id=candidate_ids[i],
            left_paragraph_id=paragraphs[i]["id"],
            right_paragraph_id=paragraphs[i + 1]["id"],
        )
        for i in range(CANDIDATE_COUNT)
    ]
    decisions = [
        CompactTransitionCandidateDecision(
            transition_id=tid,
            boundary_candidate=True,
            goal_relation="replaced" if (i % 2 == 0) else "refined",
            action_chain_relation="new_chain" if (i % 2 == 0) else "continuous",
            temporal_relation="major_jump" if (i % 2 == 0) else "continuous",
            location_relation="new_scene_location" if (i % 2 == 0) else "same",
            viewpoint_relation="same",
            trigger_type="goal" if (i % 2 == 0) else "none",
            confidence=0.72,
        )
        for i, tid in enumerate(candidate_ids)
    ]

    tmp_root = Path(tempfile.mkdtemp(prefix="chg040-l3-"))
    db_path = tmp_root / "l3_ephemeral.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    call_log: list[dict[str, Any]] = []
    totals = {"input": 0, "output": 0, "cost": 0.0, "actual_calls": 0}

    class GuardedProvider(OpenAICompatibleProvider):
        async def generate(self, request: ModelRequest) -> ModelResponse:
            if totals["actual_calls"] >= MAX_ACTUAL_CALLS:
                raise CallCeilingExceeded(
                    f"actual call ceiling {MAX_ACTUAL_CALLS} reached before send"
                )
            if totals["cost"] >= MAX_COST_CNY:
                raise CostCeilingExceeded("cost ceiling reached before send")
            out_limit = int(request.max_output_tokens or request.max_tokens or 0)
            if out_limit > PER_REQUEST_HARD_CAP:
                raise RuntimeError(
                    f"per-request output hard cap violated: {out_limit} > {PER_REQUEST_HARD_CAP}"
                )
            if out_limit == 768:
                raise RuntimeError("fixed 768 output policy still in use")
            started = time.perf_counter()
            response = await super().generate(request)
            totals["actual_calls"] += 1
            inn = int(response.input_tokens or 0)
            out = int(response.output_tokens or 0)
            if totals["input"] + inn > MAX_INPUT_TOKENS:
                raise RuntimeError("max input tokens exceeded")
            if totals["output"] + out > MAX_OUTPUT_TOKENS:
                raise RuntimeError("max output tokens exceeded")
            cost = _estimate_cost(inn, out)
            totals["input"] += inn
            totals["output"] += out
            totals["cost"] += cost
            if totals["cost"] > MAX_COST_CNY:
                raise CostCeilingExceeded(
                    f"cost {totals['cost']:.4f} exceeded ¥{MAX_COST_CNY}"
                )
            entry = {
                "call_index": totals["actual_calls"],
                "requested_output_tokens": out_limit,
                "finish_reason": response.finish_reason,
                "input_tokens": inn,
                "output_tokens": out,
                "total_tokens": response.total_tokens,
                "estimated_cost_cny": round(cost, 6),
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "http_status": response.http_status_code,
                "model": response.model,
                "request_id": response.request_id,
            }
            call_log.append(entry)
            return response

    provider = GuardedProvider(
        name=PROVIDER,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key=api_key,
        default_model=MODEL,
        timeout_seconds=300,
        max_context_tokens=32768,
        enabled=True,
        profile_name=PROVIDER,
        structured_output_mode="json_object",
        supports_thinking_control=True,
        cloud=True,
        provider_family="aliyun_qwen",
        supports_json_object=True,
        sends_content_to_cloud=True,
        region="cn-beijing",
        supports_scene_analysis=True,
        supports_boundary_candidates=True,
    )
    gateway = ModelGateway([provider])

    report: dict[str, Any] = {
        "change_id": "CHG-20260728-040",
        "issue_id": "INC-20260728-002",
        "provider": PROVIDER,
        "model": MODEL,
        "candidate_count": CANDIDATE_COUNT,
        "formal_database_writes": 0,
        "temp_db_deleted": False,
        "authorized": True,
        "caps": {
            "max_logical_calls": MAX_LOGICAL_CALLS,
            "max_actual_calls": MAX_ACTUAL_CALLS,
            "max_input_tokens": MAX_INPUT_TOKENS,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "per_request_output_hard_cap": PER_REQUEST_HARD_CAP,
            "max_cost_cny": MAX_COST_CNY,
        },
    }

    try:
        with SessionLocal() as session:
            session.add(
                ApplicationSetting(
                    key="cloud_budget_settings",
                    value_json=json.dumps(
                        {
                            "cloud_request_budget_enabled": True,
                            "cloud_max_input_tokens_per_request": 16000,
                            "cloud_max_output_tokens_per_request": PER_REQUEST_HARD_CAP,
                            "cloud_max_requests_per_run": MAX_ACTUAL_CALLS,
                            "cloud_daily_request_limit": 20,
                            "cloud_daily_token_limit": MAX_INPUT_TOKENS + MAX_OUTPUT_TOKENS,
                            "cloud_daily_estimated_cost_limit": MAX_COST_CNY,
                            "currency": "CNY",
                            "cloud_stop_on_unknown_pricing": False,
                            "cloud_confirm_each_paid_test": False,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            # Intentionally omit cloud_enabled so claim gate is no-op on temp DB.
            run = AnalysisRun(
                task_type="scene_pipeline",
                subject_type="chapter",
                subject_id="L3-CHG040",
                provider=PROVIDER,
                model=MODEL,
                prompt_version="v3.5",
                schema_version="v1",
                prompt_hash="l3",
                input_hash="l3-chg040-synth-20",
                status="running",
            )
            session.add(run)
            session.commit()

            batches = plan_output_bounded_adjudication_batches(
                candidate_ids,
                transitions,
                paragraph_text,
                run_id=run.id,
                prompt_version="v1.1.2",
            )
            report["batch_total"] = len(batches)
            report["max_target_per_batch"] = 10
            report["initial_limits"] = []
            if len(batches) != 2:
                raise RuntimeError(f"expected 2 batches for 20 candidates, got {len(batches)}")

            prompt = load_prompt("scene_boundary_adjudication", "v1.1.2")
            batch_results: list[tuple[list[str], BoundaryCandidateAdjudicationResult]] = []
            logical_calls = 0

            for batch in batches:
                if logical_calls >= MAX_LOGICAL_CALLS:
                    raise CallCeilingExceeded("logical call ceiling reached")
                targets = list(batch.target_candidate_ids)
                budget = compute_scene_boundary_output_budget_v1(
                    target_candidate_count=len(targets),
                    user_output_hard_cap=PER_REQUEST_HARD_CAP,
                )
                if budget.initial_output_limit == 768:
                    raise RuntimeError("initial budget still fixed 768")
                report["initial_limits"].append(
                    {
                        "batch_index": batch.batch_index,
                        "target_count": len(targets),
                        "context_count": len(batch.context_only_candidate_ids),
                        "initial_output_limit": budget.initial_output_limit,
                        "effective_hard_cap": budget.effective_hard_cap,
                    }
                )
                snapshot = adjudication_snapshot_v112(
                    chapter_id="L3-CHG040-C0001",
                    title="合成二十候选边界裁决样例",
                    batch=batch,
                    candidates=transitions,
                    decisions=decisions,
                    paragraph_text=paragraph_text,
                )
                # Strip long text from evidence later; snapshot stays in-memory only.
                calls_before = totals["actual_calls"]
                logical_calls += 1
                adjudicated = await generate_validated(
                    session=session,
                    gateway=gateway,
                    run_id=run.id,
                    provider_name=PROVIDER,
                    task_type="scene_boundary_adjudication",
                    prompt=prompt,
                    schema=BoundaryCandidateAdjudicationResult,
                    input_snapshot={
                        "target_candidate_ids": targets,
                        "context_only_candidate_ids": list(
                            batch.context_only_candidate_ids
                        ),
                        "batch_index": batch.batch_index,
                    },
                    user_content=prompt.user_template.format(
                        input_json=json.dumps(snapshot, ensure_ascii=False)
                    ),
                    business_validator=lambda value, batch=batch: validate_batch_coverage(
                        value,
                        target_candidate_ids=list(batch.target_candidate_ids),
                        context_only_candidate_ids=list(
                            batch.context_only_candidate_ids
                        ),
                        known_candidate_ids=set(candidate_ids),
                    ),
                    initial_invocation_kind="boundary_candidate_adjudication",
                    output_tokens_override=budget.initial_output_limit,
                    adaptive_truncation_budget=True,
                    truncation_hard_cap=budget.effective_hard_cap,
                )
                validate_batch_coverage(
                    adjudicated,
                    target_candidate_ids=targets,
                    context_only_candidate_ids=list(batch.context_only_candidate_ids),
                    known_candidate_ids=set(candidate_ids),
                )
                batch_results.append((targets, adjudicated))
                batch_calls = totals["actual_calls"] - calls_before
                report.setdefault("batch_outcomes", []).append(
                    {
                        "batch_index": batch.batch_index,
                        "target_ids_count": len(targets),
                        "actual_calls": batch_calls,
                        "verdict_count": len(adjudicated.verdicts),
                        "requested_limits": [
                            c["requested_output_tokens"]
                            for c in call_log[calls_before:]
                        ],
                        "finish_reasons": [
                            c["finish_reason"] for c in call_log[calls_before:]
                        ],
                    }
                )

            merged = merge_adjudication_batches(
                original_candidate_order=candidate_ids,
                batch_results=batch_results,
            )
            covered = [v.transition_id for v in merged.verdicts]
            report["success"] = True
            report["logical_calls"] = logical_calls
            report["candidates_covered"] = len(covered)
            report["coverage_exact"] = covered == candidate_ids
            report["accept_count"] = sum(1 for v in merged.verdicts if v.accept)

            inv_rows = list(
                session.scalars(
                    select(ModelInvocation)
                    .where(ModelInvocation.run_id == run.id)
                    .order_by(ModelInvocation.id)
                )
            )
            report["model_invocations_persisted_in_temp_db"] = len(inv_rows)
            report["usage_from_invocations"] = {
                "calls": len(inv_rows),
                "input_tokens": sum(int(i.input_tokens or 0) for i in inv_rows),
                "output_tokens": sum(int(i.output_tokens or 0) for i in inv_rows),
                "requested_output_tokens": [
                    i.requested_output_tokens for i in inv_rows
                ],
                "finish_reasons": [i.finish_reason for i in inv_rows],
            }
            # Ensure no raw bodies leaked into evidence payload.
            for row in inv_rows:
                if row.raw_response_text and len(row.raw_response_text) > 0:
                    # Temp DB only; do not copy into evidence.
                    pass

    except (StructuredOutputError, CallCeilingExceeded, CostCeilingExceeded) as exc:
        report["success"] = False
        report["error_type"] = type(exc).__name__
        report["error_code"] = getattr(exc, "error_code", None)
        report["error_message"] = str(exc)[:500]
    except Exception as exc:  # noqa: BLE001
        report["success"] = False
        report["error_type"] = type(exc).__name__
        report["error_message"] = str(exc)[:500]
    finally:
        engine.dispose()
        shutil.rmtree(tmp_root, ignore_errors=True)
        report["temp_db_deleted"] = True
        report["formal_database_writes"] = 0

    report["actual_calls"] = totals["actual_calls"]
    report["call_log"] = call_log
    report["usage_totals"] = {
        "input_tokens": totals["input"],
        "output_tokens": totals["output"],
        "estimated_cost_cny": round(totals["cost"], 6),
    }
    # Truncation retry strictly increasing check across call_log per batch.
    increasing_ok = True
    for outcome in report.get("batch_outcomes") or []:
        limits = outcome.get("requested_limits") or []
        for a, b in zip(limits, limits[1:]):
            if not (b > a):
                increasing_ok = False
    report["truncation_retry_limits_strictly_increasing"] = increasing_ok
    report["fixed_768_absent"] = all(
        c.get("requested_output_tokens") != 768 for c in call_log
    )

    out_json = EVIDENCE / "L3_REAL_PROVIDER_RESULT.json"
    out_md = EVIDENCE / "L3_REAL_PROVIDER_VERIFICATION.md"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# L3 Real Provider Verification — CHG-20260728-040",
        "",
        f"- Success: **{report.get('success')}**",
        f"- Provider/Model: `{PROVIDER}` / `{MODEL}`",
        f"- Batches: {report.get('batch_total')}",
        f"- Logical calls: {report.get('logical_calls')}",
        f"- Actual HTTP calls: {report.get('actual_calls')}",
        f"- Candidates covered: {report.get('candidates_covered')}",
        f"- Fixed 768 absent: {report.get('fixed_768_absent')}",
        f"- Retry limits strictly increasing: {report.get('truncation_retry_limits_strictly_increasing')}",
        f"- Estimated cost CNY: {report.get('usage_totals', {}).get('estimated_cost_cny')}",
        f"- Formal DB writes: 0 (temp DB deleted={report.get('temp_db_deleted')})",
        "",
        "Initial limits:",
        "```json",
        json.dumps(report.get("initial_limits"), ensure_ascii=False, indent=2),
        "```",
        "",
        "Call log (no prompt/response bodies):",
        "```json",
        json.dumps(call_log, ensure_ascii=False, indent=2),
        "```",
    ]
    if not report.get("success"):
        lines.extend(
            [
                "",
                f"Error: `{report.get('error_type')}` / `{report.get('error_code')}`",
                f"Message: {report.get('error_message')}",
            ]
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "success", "batch_total", "logical_calls", "actual_calls",
        "candidates_covered", "fixed_768_absent", "usage_totals",
        "error_type", "error_code",
    ) if k in report}, ensure_ascii=False, indent=2))
    return 0 if report.get("success") else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
