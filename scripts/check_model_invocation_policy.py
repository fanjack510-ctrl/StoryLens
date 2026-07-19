# -*- coding: utf-8 -*-
"""Offline gate: global model invocation policy (DEFECT-CANARY-015).

Zero model requests. Prints INVOCATION_POLICY_PASS or INVOCATION_POLICY_FAIL.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "api" / "app"
SERVICES = API / "services"
AUDITS = ROOT / "audits" / "single-chapter-pipeline"

CANONICAL_TYPES = [
    "scene_boundary",
    "scene_boundary_schema_repair",
    "scene_analysis",
    "scene_analysis_provider_retry",
    "scene_analysis_provider_recovery",
    "reader_journey_scene_batch",
    "reader_journey_scene_schema_repair",
    "reader_journey_structural_repair",
    "reader_journey_targeted_evidence_patch",
    "reader_journey_chapter",
    "reader_journey_chapter_schema_repair",
    "repair_provider_retry",
    "generic_provider_retry",
]

PRODUCTION_SERVICE_FILES = [
    SERVICES / "structured_output.py",
    SERVICES / "scene_pipeline.py",
    SERVICES / "reader_journey_pipeline.py",
    SERVICES / "boundary_review_service.py",
    SERVICES / "scene_analysis_provider_recovery.py",
]

ALLOWED_DIRECT_GENERATE = {
    # Connection test is explicitly non-pipeline / single-shot.
    str((SERVICES / "provider_connection_test.py").resolve()),
}


def _ok(checks: list[dict], name: str, passed: bool, detail: str) -> None:
    checks.append({"name": name, "ok": passed, "detail": detail})


def _scan_direct_gateway_generate() -> list[str]:
    offenders: list[str] = []
    for path in API.rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "gateway.generate(" not in text and ".generate(" not in text:
            continue
        rel = str(path.resolve())
        if rel in ALLOWED_DIRECT_GENERATE:
            continue
        if path.name == "model_invocation_broker.py":
            # Broker is the sole production send entry wrapping gateway.generate.
            continue
        if path.name == "openai_compatible.py":
            continue
        if "gateway.generate(" in text and path.name != "model_invocation_broker.py":
            # structured_output must not call gateway.generate directly.
            if path.name == "structured_output.py" and "gateway.generate(" in text:
                offenders.append(f"{path.relative_to(ROOT)}:gateway.generate")
        # Direct provider.generate in pipeline services (except connection test).
        if path.parent == SERVICES and path.name != "provider_connection_test.py":
            if re.search(r"\bprovider\.generate\(", text):
                offenders.append(f"{path.relative_to(ROOT)}:provider.generate")
    return offenders


def main() -> int:
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    checks: list[dict] = []

    from app.services.model_invocation_broker import (
        ERROR_UNAUTHORIZED_FALLBACK,
        REGISTERED_INVOCATION_TYPES,
        resolve_for_offline_graph,
    )

    missing_types = [t for t in CANONICAL_TYPES if t not in REGISTERED_INVOCATION_TYPES]
    _ok(checks, "all_invocation_types_registered", not missing_types, str(missing_types))

    structured = (SERVICES / "structured_output.py").read_text(encoding="utf-8")
    _ok(
        checks,
        "production_calls_use_broker",
        "model_invocation_broker" in structured
        and "model_invocation_broker.invoke" in structured
        and "model_invocation_broker.resolve" in structured,
        "structured_output wired to broker",
    )
    _ok(
        checks,
        "no_direct_provider_calls_in_pipelines",
        "gateway.generate(" not in structured,
        "structured_output has no direct gateway.generate",
    )
    offenders = _scan_direct_gateway_generate()
    _ok(checks, "no_bypass_gateway_generate", not offenders, str(offenders))

    _ok(
        checks,
        "no_flash_hardcode_in_structured_output",
        "aliyun_qwen_flash" not in structured,
        "flash absent from structured_output",
    )

    # auto_route=false → no fallback; Plus policy never resolves to Flash.
    plus_ok = True
    details = []
    for inv in CANONICAL_TYPES:
        payload = resolve_for_offline_graph(
            invocation_type=inv,
            authorized_provider="aliyun_qwen_plus",
            authorized_model="qwen3.7-plus",
            auto_route=False,
            requested_provider="aliyun_qwen_plus",
            requested_model="qwen3.7-plus",
        )
        if payload.get("resolved_provider") != "aliyun_qwen_plus":
            plus_ok = False
            details.append(f"{inv}->provider={payload.get('resolved_provider')}")
        if payload.get("resolved_model") != "qwen3.7-plus":
            plus_ok = False
            details.append(f"{inv}->model={payload.get('resolved_model')}")
        if payload.get("fallback_used"):
            plus_ok = False
            details.append(f"{inv}->fallback")
        if payload.get("error_code"):
            plus_ok = False
            details.append(f"{inv}->err={payload.get('error_code')}")
    _ok(checks, "plus_policy_no_flash", plus_ok, "; ".join(details) or "all plus")

    flash_attempt = resolve_for_offline_graph(
        invocation_type="reader_journey_scene_schema_repair",
        authorized_provider="aliyun_qwen_plus",
        authorized_model="qwen3.7-plus",
        auto_route=False,
        requested_provider="aliyun_qwen_flash",
        requested_model="qwen3.6-flash",
    )
    _ok(
        checks,
        "auto_route_false_no_fallback",
        flash_attempt.get("error_code")
        in {
            ERROR_UNAUTHORIZED_FALLBACK,
            "MODEL_INVOCATION_POLICY_VIOLATION",
            "MODEL_UNAUTHORIZED_FALLBACK",
        },
        str(flash_attempt.get("error_code")),
    )

    # Disabled provider must not resolve successfully.
    # Simulate via resolve with gateway-less path + provider_enabled=False helper.
    disabled = resolve_for_offline_graph(
        invocation_type="scene_analysis",
        authorized_provider="aliyun_qwen_plus",
        authorized_model="qwen3.7-plus",
        auto_route=False,
        provider_enabled=False,
    )
    _ok(
        checks,
        "disabled_provider_not_resolved",
        disabled.get("error_code") == "MODEL_PROVIDER_DISABLED_PRECHECK",
        str(disabled.get("error_code")),
    )

    retry = resolve_for_offline_graph(
        invocation_type="generic_provider_retry",
        authorized_provider="aliyun_qwen_plus",
        authorized_model="qwen3.7-plus",
        auto_route=False,
    )
    repair = resolve_for_offline_graph(
        invocation_type="reader_journey_scene_schema_repair",
        authorized_provider="aliyun_qwen_plus",
        authorized_model="qwen3.7-plus",
        auto_route=False,
    )
    recovery = resolve_for_offline_graph(
        invocation_type="scene_analysis_provider_recovery",
        authorized_provider="aliyun_qwen_plus",
        authorized_model="qwen3.7-plus",
        auto_route=False,
    )
    _ok(
        checks,
        "retry_no_reroute",
        retry.get("resolved_provider") == "aliyun_qwen_plus"
        and retry.get("fallback_used") is False,
        str(retry.get("resolved_provider")),
    )
    _ok(
        checks,
        "repair_no_default_flash",
        repair.get("resolved_provider") == "aliyun_qwen_plus"
        and repair.get("resolved_model") == "qwen3.7-plus",
        f"{repair.get('resolved_provider')}/{repair.get('resolved_model')}",
    )
    _ok(
        checks,
        "recovery_no_default_flash",
        recovery.get("resolved_provider") == "aliyun_qwen_plus"
        and recovery.get("resolved_model") == "qwen3.7-plus",
        f"{recovery.get('resolved_provider')}/{recovery.get('resolved_model')}",
    )

    graph_path = AUDITS / "model-invocation-graph-v1.json"
    _ok(checks, "invocation_graph_present", graph_path.exists(), str(graph_path))
    if graph_path.exists():
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes = graph.get("invocations") or []
        flash_nodes = [
            n
            for n in nodes
            if n.get("resolved_provider") == "aliyun_qwen_flash"
            and not n.get("historical_defect_replay")
        ]
        _ok(
            checks,
            "graph_no_live_flash",
            not flash_nodes,
            f"flash_nodes={len(flash_nodes)}",
        )

    change_path = (
        AUDITS / "changes" / "global-model-invocation-policy-change-v1.1.0.json"
    )
    _ok(checks, "change_package_present", change_path.exists(), str(change_path))
    if change_path.exists():
        change = json.loads(change_path.read_text(encoding="utf-8"))
        _ok(
            checks,
            "zero_real_model_requests",
            change.get("real_model_requests_this_phase") == 0,
            str(change.get("real_model_requests_this_phase")),
        )

    # AST sanity: broker module parses.
    broker_src = (SERVICES / "model_invocation_broker.py").read_text(encoding="utf-8")
    try:
        ast.parse(broker_src)
        _ok(checks, "broker_ast", True, "ok")
    except SyntaxError as exc:
        _ok(checks, "broker_ast", False, str(exc))

    failed = [c for c in checks if not c["ok"]]
    report = {
        "gate": "check_model_invocation_policy",
        "verdict": "INVOCATION_POLICY_FAIL" if failed else "INVOCATION_POLICY_PASS",
        "checks": checks,
        "failed": [c["name"] for c in failed],
    }
    out = AUDITS / "model-invocation-policy-gate-v1.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report["verdict"])
    for item in checks:
        mark = "PASS" if item["ok"] else "FAIL"
        print(f"  [{mark}] {item['name']}: {item['detail']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
