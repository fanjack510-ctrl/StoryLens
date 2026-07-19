# -*- coding: utf-8 -*-
"""Read-only checker for invocation-path qualification artifacts."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDITS = ROOT / "audits" / "single-chapter-pipeline" / "invocation-path-qualification-v1"
MAIN_DB = ROOT / "data" / "storylens.db"
REQUIRED_TYPES = [
    "reader_journey_scene_schema_repair",
    "reader_journey_structural_repair",
    "generic_provider_retry",
    "repair_provider_retry",
    "reader_journey_targeted_evidence_patch",
    "scene_analysis_provider_recovery",
    "reader_journey_chapter_schema_repair",
]


def main() -> int:
    checks = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    report_path = AUDITS / "qualification-report-v1.json"
    verdict_path = AUDITS / "final-verdict-v1.json"
    auth_path = AUDITS / "authorization-qualification-v1.json"
    add("report_present", report_path.exists(), str(report_path))
    add("verdict_present", verdict_path.exists(), str(verdict_path))
    add("auth_present", auth_path.exists(), str(auth_path))
    if not report_path.exists():
        print("INVOCATION_PATH_QUALIFICATION_CHECK_FAIL")
        return 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    auth = json.loads(auth_path.read_text(encoding="utf-8")) if auth_path.exists() else {}
    add("operator_approved", bool(auth.get("operator_approved")), str(auth.get("operator_approved")))
    add("scope_qualification", auth.get("scope") == "invocation_path_qualification", str(auth.get("scope")))
    add("no_full_canary", auth.get("allows_full_canary") is False, str(auth.get("allows_full_canary")))
    add("provider_plus", report.get("provider") == "aliyun_qwen_plus", str(report.get("provider")))
    add("model_plus", report.get("model") == "qwen3.7-plus", str(report.get("model")))
    add("auto_route_false", report.get("auto_route") is False, str(report.get("auto_route")))
    add("full_canary_not_started", report.get("full_canary_started") is False, "ok")
    add("auth_v12_not_issued", report.get("authorization_v12_issued") is False, "ok")
    cov = report.get("coverage") or {}
    for t in REQUIRED_TYPES:
        item = cov.get(t) or {}
        add(f"covered_{t}", bool(item.get("covered")), str(item))
    add("no_policy_failures", not report.get("policy_failures"), str(len(report.get("policy_failures") or [])))
    conn = sqlite3.connect(str(MAIN_DB))
    try:
        a = conn.execute("select count(*) from analysis_runs").fetchone()[0]
        j = conn.execute("select count(*) from reader_journey_runs").fetchone()[0]
    finally:
        conn.close()
    add("main_db_55_2", (a, j) == (55, 2), f"{a}/{j}")
    add(
        "verdict_passed",
        report.get("verdict") == "INVOCATION_PATH_QUALIFICATION_PASSED",
        str(report.get("verdict")),
    )
    failed = [c for c in checks if not c["ok"]]
    out = {
        "gate": "check_invocation_path_qualification",
        "verdict": (
            "INVOCATION_PATH_QUALIFICATION_CHECK_FAIL"
            if failed
            else "INVOCATION_PATH_QUALIFICATION_CHECK_PASS"
        ),
        "checks": checks,
        "failed": [c["name"] for c in failed],
    }
    (AUDITS / "qualification-check-v1.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(out["verdict"])
    for c in checks:
        print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
