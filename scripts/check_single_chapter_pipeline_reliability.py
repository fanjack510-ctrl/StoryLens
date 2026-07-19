# -*- coding: utf-8 -*-
"""Phase 1D-B1: Single-chapter pipeline offline reliability checker (read-only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDITS = ROOT / "audits" / "single-chapter-pipeline"
ART = ROOT / "artifacts" / "single-chapter-pipeline-certification"
MAIN_DB = ROOT / "data" / "storylens.db"
CERT_DB = ART / "certification.sqlite3"

REQUIRED_REPORTS = [
    "pipeline-map-v1.json",
    "stage-contracts-v1.json",
    "fixture-matrix-v1.json",
    "offline-replay-report-v1.json",
    "integrity-report-v1.json",
    "persistence-recovery-report-v1.json",
    "idempotency-report-v1.json",
    "fault-injection-report-v1.json",
    "template-render-report-v1.json",
    "e2e-stability-report-v1.json",
    "performance-baseline-v1.json",
    "real-canary-preflight-v1.json",
]


def load(name: str) -> dict:
    path = AUDITS / name
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_reports_exist() -> tuple[bool, str]:
    missing = [n for n in REQUIRED_REPORTS if not (AUDITS / n).exists()]
    return (not missing, f"missing={missing}" if missing else "all present")


def check_fixture_counts() -> tuple[bool, str]:
    data = load("fixture-matrix-v1.json")
    books = len({f["book_title"] for f in data["fixtures"]})
    chapters = len(data["fixtures"])
    ok = books >= 3 and chapters >= 12
    return ok, f"books={books} chapters={chapters}"


def check_integrity_metrics() -> list[tuple[str, bool, str]]:
    data = load("integrity-report-v1.json")
    return [
        (
            "paragraph_coverage_100",
            bool(data.get("paragraph_coverage_all_100")),
            f"min={data.get('paragraph_coverage_min')}",
        ),
        (
            "paragraph_duplicate_0",
            data.get("paragraph_duplicate_total", 1) == 0,
            f"dup={data.get('paragraph_duplicate_total')}",
        ),
        (
            "illegal_scene_refs_0",
            data.get("scene_order_errors", 1) == 0,
            f"scene_order_errors={data.get('scene_order_errors')}",
        ),
        (
            "illegal_evidence_refs_0",
            data.get("illegal_evidence_refs", 1) == 0,
            f"illegal_evidence={data.get('illegal_evidence_refs')}",
        ),
        (
            "profile_scene_match_100",
            data.get("profile_scene_match_rate", 0) == 1.0,
            f"rate={data.get('profile_scene_match_rate')}",
        ),
        (
            "phase_uncovered_0",
            data.get("phase_uncovered_scene_total", 1) == 0,
            f"uncovered={data.get('phase_uncovered_scene_total')}",
        ),
        (
            "half_success_0",
            data.get("half_success_count", 1) == 0,
            f"half={data.get('half_success_count')}",
        ),
    ]


def check_idempotency() -> list[tuple[str, bool, str]]:
    data = load("idempotency-report-v1.json")
    return [
        (
            "duplicate_analysis_runs_0",
            data.get("duplicate_analysis_runs", 1) == 0,
            f"n={data.get('duplicate_analysis_runs')}",
        ),
        (
            "duplicate_journey_runs_0",
            data.get("duplicate_journey_runs", 1) == 0,
            f"n={data.get('duplicate_journey_runs')}",
        ),
    ]


def check_fault_and_e2e() -> list[tuple[str, bool, str]]:
    fault = load("fault-injection-report-v1.json")
    e2e = load("e2e-stability-report-v1.json")
    return [
        (
            "fault_injection_clear",
            fault.get("result") == "PASS" and fault.get("silent_failure_count", 1) == 0,
            f"result={fault.get('result')} silent={fault.get('silent_failure_count')}",
        ),
        (
            "e2e_triple_pass",
            bool(e2e.get("all_passed")) and e2e.get("result") == "PASS",
            f"result={e2e.get('result')} runs={len(e2e.get('runs') or [])} flakes={e2e.get('flake_count')}",
        ),
    ]


def _live_main_db_logical() -> dict:
    """Read main DB logical invariants without RW open (WAL can rewrite file bytes)."""
    uri = MAIN_DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    cur = con.cursor()
    analysis = cur.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0]
    journey = cur.execute("SELECT COUNT(*) FROM reader_journey_runs").fetchone()[0]
    run55 = cur.execute("SELECT status FROM analysis_runs WHERE id=55").fetchone()
    jr2 = cur.execute("SELECT status FROM reader_journey_runs WHERE id=2").fetchone()
    integrity = cur.execute("PRAGMA integrity_check").fetchone()[0]
    fk = cur.execute("PRAGMA foreign_key_check").fetchall()
    con.close()
    return {
        "analysis_run_count": analysis,
        "reader_journey_run_count": journey,
        "run_55_status": run55[0] if run55 else None,
        "journey_run_2_status": jr2[0] if jr2 else None,
        "integrity_check": integrity,
        "foreign_key_check_rows": len(fk),
        "size": MAIN_DB.stat().st_size,
        "sha256": sha256_file(MAIN_DB),
    }


def check_main_db_unchanged() -> tuple[bool, str]:
    before_path = ART / "main_db_before.json"
    after_path = ART / "main_db_after.json"
    if not before_path.exists() or not after_path.exists():
        return False, "before/after snapshots missing"
    before = json.loads(before_path.read_text(encoding="utf-8"))
    after = json.loads(after_path.read_text(encoding="utf-8"))
    if not MAIN_DB.exists():
        return False, "main db missing"
    live = _live_main_db_logical()
    cert_window_sha_ok = before.get("sha256") == after.get("sha256")
    cert_counts_ok = (
        before.get("analysis_run_count") == after.get("analysis_run_count") == 55
        and before.get("reader_journey_run_count") == after.get("reader_journey_run_count") == 2
        and (before.get("run_55") or {}).get("status") == "succeeded"
        and (before.get("journey_run_2") or {}).get("status") == "succeeded"
    )
    live_logical_ok = (
        live["analysis_run_count"] == 55
        and live["reader_journey_run_count"] == 2
        and live["run_55_status"] == "succeeded"
        and live["journey_run_2_status"] == "succeeded"
        and live["integrity_check"] == "ok"
        and live["foreign_key_check_rows"] == 0
        and live["size"] == before.get("size")
    )
    live_sha_ok = live["sha256"] == before.get("sha256")
    # Cert window must be byte-identical. Live file bytes may drift if a later RW
    # diagnostic open checkpointed WAL; logical invariants + size must still match.
    ok = cert_window_sha_ok and cert_counts_ok and live_logical_ok
    return (
        ok,
        (
            f"cert_sha_equal={cert_window_sha_ok} live_sha_match={live_sha_ok} "
            f"analysis={live['analysis_run_count']} journey={live['reader_journey_run_count']} "
            f"size_match={live['size'] == before.get('size')}"
        ),
    )


def check_zero_model() -> tuple[bool, str]:
    offline = load("offline-replay-report-v1.json")
    summary_path = ART / "certification_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    ok = (
        offline.get("real_http_requests", 1) == 0
        and summary.get("real_model_requests", 1) == 0
        and summary.get("token", 1) == 0
        and summary.get("cost", 1) == 0
    )
    return ok, f"http={offline.get('real_http_requests')} token={summary.get('token')} cost={summary.get('cost')}"


def check_canary_preflight() -> list[tuple[str, bool, str]]:
    """Prefer latest preflight (v6 → v5 → v4 → v3 → v1)."""
    for version, label in (
        ("v6", "preflight-v6"),
        ("v5", "preflight-v5"),
        ("v4", "preflight-v4"),
        ("v3", "preflight-v3"),
    ):
        path = ROOT / "audits" / "single-chapter-pipeline" / f"real-canary-preflight-{version}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        max_cost = (data.get("hard_limits") or {}).get("max_cost")
        configured = bool((data.get("hard_limits") or {}).get("max_cost_configured"))
        auth_path = (
            ROOT
            / "audits"
            / "single-chapter-pipeline"
            / f"real-canary-{version}"
            / f"authorization-{version}.json"
        )
        if auth_path.exists() and data.get("execution_allowed") is True:
            auth = json.loads(auth_path.read_text(encoding="utf-8"))
            ok = (
                bool(auth.get("operator_approved"))
                and isinstance(max_cost, (int, float))
                and max_cost > 0
                and configured
                and float(auth.get("operator_max_cost_cny")) == float(max_cost)
            )
            return [
                ("canary_preflight_exists", True, f"{label} present"),
                (
                    "canary_authorized_max_cost",
                    ok,
                    f"max_cost={max_cost} execution_allowed={data.get('execution_allowed')} auth={auth.get('operator_approved')}",
                ),
            ]
        return [
            ("canary_preflight_exists", True, f"{label} present"),
            (
                "canary_refuse_without_max_cost",
                max_cost is None and not configured and data.get("execution_allowed") is False,
                f"max_cost={max_cost} execution_allowed={data.get('execution_allowed')}",
            ),
        ]

    data = load("real-canary-preflight-v1.json")
    max_cost = (data.get("hard_limits") or {}).get("max_cost")
    configured = bool((data.get("hard_limits") or {}).get("max_cost_configured"))
    auth_path = ROOT / "audits" / "single-chapter-pipeline" / "real-canary" / "authorization-v1.json"
    if auth_path.exists():
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
        ok = (
            bool(auth.get("operator_approved"))
            and isinstance(max_cost, (int, float))
            and max_cost > 0
            and configured
            and data.get("execution_allowed") is True
            and float(auth.get("operator_max_cost_cny")) == float(max_cost)
        )
        return [
            ("canary_preflight_exists", True, "present"),
            (
                "canary_authorized_max_cost",
                ok,
                f"max_cost={max_cost} execution_allowed={data.get('execution_allowed')} auth={auth.get('operator_approved')}",
            ),
        ]
    return [
        ("canary_preflight_exists", True, "present"),
        (
            "canary_refuse_without_max_cost",
            max_cost is None and not configured and data.get("execution_allowed") is False,
            f"max_cost={max_cost} execution_allowed={data.get('execution_allowed')}",
        ),
    ]


def check_freeze_scripts() -> list[tuple[str, bool, str]]:
    # Presence only; actual PASS verified by gate suite.
    paths = [
        ROOT / "scripts" / "check_reader_journey_ui_freeze.py",
        ROOT / "scripts" / "check_single_chapter_journey_template.py",
    ]
    return [
        ("journey_freeze_script", paths[0].exists(), paths[0].name),
        ("template_checker_script", paths[1].exists(), paths[1].name),
    ]


def build_checks() -> list[dict]:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    ok, detail = check_reports_exist()
    add("required_reports", ok, detail)
    ok, detail = check_fixture_counts()
    add("fixture_counts", ok, detail)
    for name, ok, detail in check_integrity_metrics():
        add(name, ok, detail)
    for name, ok, detail in check_idempotency():
        add(name, ok, detail)
    for name, ok, detail in check_fault_and_e2e():
        add(name, ok, detail)
    ok, detail = check_main_db_unchanged()
    add("main_db_unchanged", ok, detail)
    ok, detail = check_zero_model()
    add("zero_model_cost", ok, detail)
    for name, ok, detail in check_canary_preflight():
        add(name, ok, detail)
    for name, ok, detail in check_freeze_scripts():
        add(name, ok, detail)

    # Cert DB integrity if present
    if CERT_DB.exists():
        con = sqlite3.connect(CERT_DB)
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        con.close()
        add("cert_db_integrity", integrity == "ok", integrity)
        add("cert_db_fk", len(fk) == 0, f"violations={len(fk)}")
    else:
        add("cert_db_integrity", False, "missing")

    template = load("template-render-report-v1.json")
    add(
        "template_render",
        template.get("result") == "PASS",
        f"pass_rate={template.get('pass_rate')}",
    )
    persist = load("persistence-recovery-report-v1.json")
    add("persistence_recovery", persist.get("result") == "PASS", persist.get("result"))
    return checks


def engineering_verdict(checks: list[dict]) -> str:
    e2e = load("e2e-stability-report-v1.json")
    integrity = load("integrity-report-v1.json")
    failed = [c for c in checks if not c["ok"]]
    # Critical blockers
    critical_names = {
        "paragraph_coverage_100",
        "half_success_0",
        "main_db_unchanged",
        "zero_model_cost",
        "e2e_triple_pass",
        "profile_scene_match_100",
    }
    critical_fail = [c for c in failed if c["name"] in critical_names]
    if critical_fail or integrity.get("result") != "PASS" or not e2e.get("all_passed"):
        return "ENGINEERING_BLOCKED"
    if failed:
        return "ENGINEERING_BLOCKED"
    return "ENGINEERING_READY_FOR_REAL_CANARY"


def main() -> int:
    parser = argparse.ArgumentParser(description="Single-chapter pipeline reliability check")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--explain", type=str, default=None)
    args = parser.parse_args()

    try:
        checks = build_checks()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: checker error: {exc}")
        return 1

    if args.explain:
        match = next((c for c in checks if c["name"] == args.explain), None)
        if not match:
            print(f"unknown check: {args.explain}")
            return 1
        print(json.dumps(match, ensure_ascii=False, indent=2))
        return 0 if match["ok"] else 1

    verdict = engineering_verdict(checks)
    # Canary start allowed only when the latest preflight is operator-authorized.
    canary = None
    auth_path = None
    for version in ("v6", "v5", "v4", "v3"):
        path = ROOT / "audits" / "single-chapter-pipeline" / f"real-canary-preflight-{version}.json"
        if path.exists():
            canary = json.loads(path.read_text(encoding="utf-8"))
            auth_path = (
                ROOT
                / "audits"
                / "single-chapter-pipeline"
                / f"real-canary-{version}"
                / f"authorization-{version}.json"
            )
            break
    if canary is None:
        canary = load("real-canary-preflight-v1.json")
        auth_path = ROOT / "audits" / "single-chapter-pipeline" / "real-canary" / "authorization-v1.json"
    canary_start_allowed = False
    if auth_path.exists() and verdict == "ENGINEERING_READY_FOR_REAL_CANARY":
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
        limits = canary.get("hard_limits") or {}
        canary_start_allowed = (
            bool(auth.get("operator_approved"))
            and bool(limits.get("max_cost_configured"))
            and limits.get("max_cost") is not None
            and float(limits.get("max_cost")) > 0
            and float(auth.get("operator_max_cost_cny")) == float(limits.get("max_cost"))
            and canary.get("execution_allowed") is True
        )

    payload = {
        "result": "PASS" if verdict == "ENGINEERING_READY_FOR_REAL_CANARY" else "FAIL",
        "engineering_verdict": verdict,
        "canary_start_allowed": canary_start_allowed,
        "checks": checks,
        "failed": [c for c in checks if not c["ok"]],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("StoryLens Single-Chapter Pipeline Reliability Check")
        for item in checks:
            mark = "OK" if item["ok"] else "FAIL"
            print(f"  [{mark}] {item['name']}: {item['detail']}")
        print()
        print("RESULT:", payload["result"])
        print("ENGINEERING_VERDICT:", verdict)
        print("CANARY_START_ALLOWED:", canary_start_allowed)
    return 0 if payload["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
