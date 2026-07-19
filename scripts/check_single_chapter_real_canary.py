# -*- coding: utf-8 -*-
"""Phase 1D-B2 real canary checker (read-only; no model calls)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDITS = ROOT / "audits" / "single-chapter-pipeline" / "real-canary-v13"
REQUIRED = [
    "authorization-v13.json",
    "batch-manifest-v1.json",
    "chapter-matrix-v1.json",
    "model-call-ledger-v1.jsonl",
    "run-results-v1.json",
    "cost-report-v1.json",
    "main-database-invariance-v1.json",
    "final-verdict-v1.json",
]


def load(name: str) -> dict:
    return json.loads((AUDITS / name).read_text(encoding="utf-8"))


def build_checks() -> list[dict]:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    missing = [n for n in REQUIRED if not (AUDITS / n).exists()]
    add("required_reports", not missing, f"missing={missing}" if missing else "all present")
    if missing:
        return checks

    auth = load("authorization-v13.json")
    add("operator_approved", bool(auth.get("operator_approved")), str(auth.get("operator_approved")))
    add(
        "batch_generation_v13",
        auth.get("batch_generation") == "v13",
        str(auth.get("batch_generation")),
    )
    add(
        "max_cost_positive",
        isinstance(auth.get("operator_max_cost_cny"), (int, float))
        and float(auth["operator_max_cost_cny"]) > 0,
        str(auth.get("operator_max_cost_cny")),
    )
    add(
        "run_order_holdouts",
        auth.get("run_1_fixture_id") == "C3-long-action"
        and auth.get("run_2_fixture_id") == "A2-medium-action",
        f"run1={auth.get('run_1_fixture_id')} run2={auth.get('run_2_fixture_id')}",
    )
    add(
        "prompt_v1_6",
        auth.get("reader_journey_scene_prompt") == "v1.6",
        str(auth.get("reader_journey_scene_prompt")),
    )
    add(
        "evidence_max_items_16",
        auth.get("evidence_paragraph_ids_max_items") == 16,
        str(auth.get("evidence_paragraph_ids_max_items")),
    )
    manifest = load("batch-manifest-v1.json")
    add("provider", manifest.get("provider") == "aliyun_qwen_plus", str(manifest.get("provider")))
    add("model", manifest.get("model") == "qwen3.7-plus", str(manifest.get("model")))
    add("auto_route_false", manifest.get("allow_auto_route") is False, str(manifest.get("allow_auto_route")))
    add(
        "max_cost_matches_auth",
        float((manifest.get("limits") or {}).get("max_cost_cny", -1))
        == float(auth["operator_max_cost_cny"]),
        "compared",
    )
    plan = manifest.get("plan") or []
    add(
        "plan_run1_c3",
        bool(plan) and plan[0].get("fixture_id") == "C3-long-action",
        str(plan[0].get("fixture_id") if plan else None),
    )
    add(
        "plan_run2_a2",
        len(plan) > 1 and plan[1].get("fixture_id") == "A2-medium-action",
        str(plan[1].get("fixture_id") if len(plan) > 1 else None),
    )
    add(
        "canary_db_v13",
        "canary-v13.sqlite3" in str(manifest.get("canary_db") or ""),
        str(manifest.get("canary_db")),
    )
    add(
        "change_package_v111",
        manifest.get("change_package") == "reader-journey-evidence-budget-change-v1.1.1",
        str(manifest.get("change_package")),
    )
    add(
        "batch_id_r13",
        str(manifest.get("batch_id") or "").startswith("phase-1db2-r13-"),
        str(manifest.get("batch_id")),
    )
    add(
        "not_resume_r11",
        "phase-1db2-r11-20260719T014426Z" not in str(manifest.get("batch_id") or ""),
        str(manifest.get("batch_id")),
    )

    runs = load("run-results-v1.json").get("runs") or []
    add("eight_runs", len(runs) == 8, f"n={len(runs)}")
    add("all_runs_pass", all(r.get("status") == "PASS" for r in runs) and len(runs) == 8, f"n={len(runs)}")
    add(
        "all_analysis_succeeded",
        all(r.get("analysis_status") == "succeeded" for r in runs) and len(runs) == 8,
        "ok" if runs else "empty",
    )
    add(
        "all_journey_succeeded",
        all(r.get("journey_status") == "succeeded" for r in runs) and len(runs) == 8,
        "ok" if runs else "empty",
    )

    cost = load("cost-report-v1.json")
    limits = manifest.get("limits") or {}
    accounted = float(
        cost.get("certification_accounted_cost")
        if cost.get("certification_accounted_cost") is not None
        else cost.get("estimated_cost_cny")
        or 0
    )
    add(
        "requests_within_limit",
        int(cost.get("requests") or 0) <= int(limits.get("max_model_requests") or 0),
        f"{cost.get('requests')}/{limits.get('max_model_requests')}",
    )
    add(
        "tokens_within_limit",
        int(cost.get("input_tokens") or 0) <= int(limits.get("max_input_tokens") or 0)
        and int(cost.get("output_tokens") or 0) <= int(limits.get("max_output_tokens") or 0),
        f"in={cost.get('input_tokens')} out={cost.get('output_tokens')}",
    )
    add(
        "cost_within_limit",
        accounted <= float(auth["operator_max_cost_cny"]),
        f"{accounted}/{auth['operator_max_cost_cny']}",
    )
    add(
        "no_unknown_accounting",
        int(cost.get("unknown_accounting_count") or 0) == 0
        or load("final-verdict-v1.json").get("verdict") == "REAL_CANARY_ABORTED_BY_LIMIT",
        f"unknown={cost.get('unknown_accounting_count')}",
    )

    # Policy fields on HTTP ledger rows (v1.1.0)
    ledger_path = AUDITS / "model-call-ledger-v1.jsonl"
    policy_ok = True
    policy_detail = "no http rows"
    http_rows = 0
    if ledger_path.exists():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not row.get("http_request_sent"):
                continue
            http_rows += 1
            if (
                row.get("resolved_provider") != "aliyun_qwen_plus"
                or row.get("resolved_model") != "qwen3.7-plus"
                or row.get("fallback_used") is True
                or row.get("auto_route") is True
                or "qwen_flash" in str(row.get("provider") or "")
                or "qwen_flash" in str(row.get("resolved_provider") or "")
            ):
                policy_ok = False
                policy_detail = f"inv={row.get('model_invocation_id')} provider={row.get('resolved_provider')} model={row.get('resolved_model')} fallback={row.get('fallback_used')}"
                break
        else:
            policy_detail = f"http_rows={http_rows}"
    add("invocation_policy_plus_only", policy_ok, policy_detail)

    inv = load("main-database-invariance-v1.json")
    add("main_db_counts", bool(inv.get("unchanged_counts")), str(inv.get("unchanged_counts")))

    verdict = load("final-verdict-v1.json")
    allowed = {
        "REAL_CANARY_PASSED",
        "REAL_CANARY_FAILED",
        "REAL_CANARY_BLOCKED",
        "REAL_CANARY_ABORTED_BY_LIMIT",
    }
    add("verdict_legal", verdict.get("verdict") in allowed, str(verdict.get("verdict")))
    add(
        "final_batch_r13",
        str(verdict.get("batch_id") or "").startswith("phase-1db2-r13-"),
        str(verdict.get("batch_id")),
    )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--explain", type=str, default=None)
    args = parser.parse_args()
    checks = build_checks()
    if args.explain:
        match = next((c for c in checks if c["name"] == args.explain), None)
        print(json.dumps(match, ensure_ascii=False, indent=2))
        return 0 if match and match["ok"] else 1
    failed = [c for c in checks if not c["ok"]]
    verdict_file = AUDITS / "final-verdict-v1.json"
    final = (
        json.loads(verdict_file.read_text(encoding="utf-8")).get("verdict")
        if verdict_file.exists()
        else None
    )
    payload = {
        "result": "PASS" if not failed and final == "REAL_CANARY_PASSED" else "FAIL",
        "final_verdict": final,
        "checks": checks,
        "failed": failed,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("StoryLens Single-Chapter Real Canary Check")
        for item in checks:
            print(f"  [{'OK' if item['ok'] else 'FAIL'}] {item['name']}: {item['detail']}")
        print()
        print("RESULT:", payload["result"])
        print("FINAL_VERDICT:", final)
    return 0 if payload["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
