# -*- coding: utf-8 -*-
"""Phase 1D-B1 pipeline certification smoke tests (offline only)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AUDITS = ROOT / "audits" / "single-chapter-pipeline"


def test_required_audit_reports_exist() -> None:
    required = [
        "pipeline-map-v1.json",
        "stage-contracts-v1.json",
        "fixture-matrix-v1.json",
        "offline-replay-report-v1.json",
        "integrity-report-v1.json",
        "persistence-recovery-report-v1.json",
        "idempotency-report-v1.json",
        "fault-injection-report-v1.json",
        "template-render-report-v1.json",
        "performance-baseline-v1.json",
        "real-canary-preflight-v1.json",
    ]
    for name in required:
        assert (AUDITS / name).exists(), name


def test_fixture_matrix_minimums() -> None:
    data = json.loads((AUDITS / "fixture-matrix-v1.json").read_text(encoding="utf-8"))
    assert len(data["fixtures"]) >= 12
    assert len({f["book_title"] for f in data["fixtures"]}) >= 3


def test_integrity_offline_pass() -> None:
    data = json.loads((AUDITS / "integrity-report-v1.json").read_text(encoding="utf-8"))
    assert data["result"] == "PASS"
    assert data["paragraph_coverage_all_100"] is True
    assert data["paragraph_duplicate_total"] == 0
    assert data["half_success_count"] == 0


def test_canary_preflight_requires_authorization_consistency() -> None:
    data = json.loads((AUDITS / "real-canary-preflight-v1.json").read_text(encoding="utf-8"))
    assert data["full_pipeline_runs"]["total_full_runs"] == 8
    auth_path = AUDITS / "real-canary" / "authorization-v1.json"
    if auth_path.exists():
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
        assert data["execution_allowed"] is True
        assert data["hard_limits"]["max_cost_configured"] is True
        assert data["hard_limits"]["max_cost"] == auth["operator_max_cost_cny"]
        assert auth["operator_approved"] is True
        assert float(auth["operator_max_cost_cny"]) > 0
    else:
        assert data["execution_allowed"] is False
        assert data["hard_limits"]["max_cost"] is None
        assert data["hard_limits"]["max_cost_configured"] is False


def test_main_db_snapshots_match_baseline_counts() -> None:
    art = ROOT / "artifacts" / "single-chapter-pipeline-certification"
    before = json.loads((art / "main_db_before.json").read_text(encoding="utf-8"))
    after = json.loads((art / "main_db_after.json").read_text(encoding="utf-8"))
    assert before["sha256"] == after["sha256"]
    assert before["analysis_run_count"] == 55
    assert before["reader_journey_run_count"] == 2
    assert after["run_55"]["status"] == "succeeded"
    assert after["journey_run_2"]["status"] == "succeeded"


def test_pipeline_reliability_checker_runs() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_single_chapter_pipeline_reliability.py"), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode in {0, 1}, proc.stderr
    payload = json.loads(proc.stdout)
    assert "engineering_verdict" in payload
    # Latest preflight wins (v6 → v5 → v4 → v3 → v1). Start allowed only when that preflight
    # is execution_allowed and has a matching authorization with max_cost.
    latest = None
    for version in ("v6", "v5", "v4", "v3"):
        path = AUDITS / f"real-canary-preflight-{version}.json"
        if path.exists():
            latest = json.loads(path.read_text(encoding="utf-8"))
            break
    if latest is None:
        latest = json.loads((AUDITS / "real-canary-preflight-v1.json").read_text(encoding="utf-8"))
    if (
        payload["engineering_verdict"] == "ENGINEERING_READY_FOR_REAL_CANARY"
        and latest.get("execution_allowed") is True
        and (latest.get("hard_limits") or {}).get("max_cost") is not None
    ):
        assert payload["canary_start_allowed"] is True
    else:
        assert payload["canary_start_allowed"] is False
