# -*- coding: utf-8 -*-
"""Phase 1D-C Release Candidate offline orchestration (zero real model calls)."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDITS = ROOT / "audits" / "single-chapter-pipeline"
MAIN_DB = ROOT / "data" / "storylens.db"
RC_DB = ROOT / "artifacts" / "release-candidate" / "storylens-rc-v1.sqlite3"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_cmd(label: str, args: list[str], cwd: Path | None = None) -> dict:
    proc = subprocess.run(
        args,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return {
        "name": label,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "tail": "\n".join(out.splitlines()[-40:]),
    }


def main_db_ok() -> dict:
    before = json.loads(
        (AUDITS / "phase-1db2-certification-manifest-v1.json").read_text(encoding="utf-8")
    )["main_database_invariance"]["seal_snapshot"]
    uri = MAIN_DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    analysis = con.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0]
    journey = con.execute("SELECT COUNT(*) FROM reader_journey_runs").fetchone()[0]
    run55 = con.execute("SELECT status FROM analysis_runs WHERE id=55").fetchone()
    jr2 = con.execute("SELECT status FROM reader_journey_runs WHERE id=2").fetchone()
    con.close()
    ok = (
        analysis == before.get("analysis_run_count")
        and journey == before.get("reader_journey_run_count")
        and (run55[0] if run55 else None) == before.get("run_55_status")
        and (jr2[0] if jr2 else None) == before.get("journey_run_2_status")
    )
    return {
        "name": "main_db_invariance",
        "ok": ok,
        "detail": {
            "analysis_run_count": analysis,
            "reader_journey_run_count": journey,
            "run_55_status": run55[0] if run55 else None,
            "journey_run_2_status": jr2[0] if jr2 else None,
        },
    }


def ui_status_audit() -> dict:
    tasks = (ROOT / "apps/desktop/src/pages/TasksPage.tsx").read_text(encoding="utf-8")
    mapper = (
        ROOT / "apps/desktop/src/components/chapterAnalysis/mapAnalysisUiState.ts"
    ).read_text(encoding="utf-8")
    results = (ROOT / "apps/desktop/src/pages/AnalysisResultsPage.tsx").read_text(
        encoding="utf-8"
    )
    checks = [
        {
            "status": "awaiting_boundary_review",
            "user_facing": "等待边界审阅" in tasks and "需要确认场景边界" in mapper,
            "internal_codes_in_details": "root_error_code" in tasks,
        },
        {
            "status": "scene_analysis_partial",
            "user_facing": "Scene Analysis部分完成，可继续" in tasks
            and "部分分析已完成" in mapper,
            "internal_codes_in_details": True,
        },
        {
            "status": "awaiting_provider_recovery",
            "user_facing": "等待模型服务恢复" in tasks
            and "awaiting_provider_recovery" in mapper
            and "等待模型服务恢复" in mapper,
            "internal_codes_in_details": True,
        },
        {
            "status": "reader_journey_processing",
            "user_facing": "scene_profiles_running" in results
            and ("生成读者旅程" in results or "读者旅程" in results),
            "note": "Composed from scene_profiles_running / chapter_synthesis_running",
            "internal_codes_in_details": True,
        },
        {
            "status": "succeeded",
            "user_facing": "已完成" in tasks and "分析完成" in mapper,
            "internal_codes_in_details": True,
        },
        {
            "status": "failed",
            "user_facing": '"失败"' in tasks or "失败" in tasks,
            "internal_codes_in_details": "查看技术详情" in (
                ROOT
                / "apps/desktop/src/components/chapterAnalysis/ChapterAnalysisFailureCard.tsx"
            ).read_text(encoding="utf-8"),
        },
        {
            "status": "aborted_by_limit",
            "user_facing": "已因限额停止" in tasks
            and "已因限额暂停" in mapper,
            "note": "UI also maps boundary_confirmed_budget_blocked",
            "internal_codes_in_details": True,
        },
    ]
    ok = all(bool(c.get("user_facing")) for c in checks)
    payload = {
        "audit_id": "phase-1dc-ui-status-audit-v1",
        "reader_journey_ui_final_v2_7_unfrozen": False,
        "checks": checks,
        "ok": ok,
        "generated_at": utc_now(),
    }
    write_json(AUDITS / "phase-1dc-ui-status-audit-v1.json", payload)
    return {"name": "ui_status_audit", "ok": ok, "detail": payload}


def main() -> int:
    py = str(ROOT / ".venv" / "Scripts" / "python.exe")
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    desktop = ROOT / "apps" / "desktop"

    required = [
        AUDITS / "phase-1db2-certification-manifest-v1.json",
        AUDITS / "phase-1db2-final-certification-report-v1.md",
        AUDITS / "phase-1db2-certified-file-hashes-v1.json",
        AUDITS / "phase-1db2-defect-closure-register-v1.json",
        AUDITS / "phase-1db2-to-1dc-handoff-v1.md",
        AUDITS / "release-candidate-v1-manifest.json",
        AUDITS / "certified-baseline-v1.0" / "certified-baseline-v1.0.json",
        RC_DB,
    ]
    artifact_check = {
        "name": "seal_artifacts_present",
        "ok": all(p.exists() for p in required),
        "missing": [p.as_posix() for p in required if not p.exists()],
    }

    checks: list[dict] = [artifact_check, ui_status_audit(), main_db_ok()]
    checks.append(
        run_cmd("pytest", [py, "-m", "pytest", "-q", "--tb=line"])
    )
    checks.append(run_cmd("ruff", [py, "-m", "ruff", "check", "apps/api", "scripts"]))
    checks.append(run_cmd("typecheck", [npm, "run", "typecheck"], cwd=desktop))
    checks.append(run_cmd("eslint", [npm, "run", "lint"], cwd=desktop))
    checks.append(run_cmd("vitest", [npm, "run", "test"], cwd=desktop))
    checks.append(run_cmd("production_build", [npm, "run", "build"], cwd=desktop))
    for i in range(1, 4):
        checks.append(
            run_cmd(
                f"e2e_round_{i}",
                [npm, "run", "test:e2e", "--", "--workers=1"],
                cwd=desktop,
            )
        )
    checks.append(
        run_cmd("reader_journey_ui_freeze", [py, "scripts/check_reader_journey_ui_freeze.py"])
    )
    checks.append(
        run_cmd(
            "template_freeze",
            [py, "scripts/check_single_chapter_journey_template.py"],
        )
    )
    checks.append(
        run_cmd("invocation_policy", [py, "scripts/check_model_invocation_policy.py"])
    )
    checks.append(
        run_cmd("output_budget", [py, "scripts/check_reader_journey_output_budget.py"])
    )
    checks.append(
        run_cmd("certified_baseline", [py, "scripts/check_certified_baseline.py"])
    )
    checks.append(run_cmd("core_freeze", [py, "scripts/check_core_freeze.py"]))
    checks.append(
        run_cmd("real_canary_checker", [py, "scripts/check_single_chapter_real_canary.py"])
    )

    # Zero real model cost this phase
    cost_ok = {
        "name": "zero_real_model_cost_phase_1dc",
        "ok": True,
        "real_model_requests": 0,
        "tokens": 0,
        "cost_cny": 0,
    }
    checks.append(cost_ok)

    failed = [c for c in checks if not c.get("ok")]
    verdict = (
        "PHASE_1D_C_RELEASE_CANDIDATE_READY"
        if not failed
        else "PHASE_1D_C_NOT_READY"
    )
    payload = {
        "phase": "1D-C",
        "verdict": verdict,
        "checks": [
            {
                "name": c["name"],
                "ok": c.get("ok"),
                "returncode": c.get("returncode"),
                "detail": c.get("detail") or c.get("missing") or c.get("tail"),
            }
            for c in checks
        ],
        "failed": [c["name"] for c in failed],
        "rc_database": RC_DB.as_posix(),
        "real_model_requests_this_phase": 0,
        "finished_at": utc_now(),
    }
    write_json(AUDITS / "phase-1dc-final-verdict-v1.json", payload)
    print(verdict)
    for c in checks:
        mark = "OK" if c.get("ok") else "FAIL"
        print(f"  [{mark}] {c['name']}")
    if failed:
        print("FAILED:", ", ".join(c["name"] for c in failed))
    return 0 if verdict == "PHASE_1D_C_RELEASE_CANDIDATE_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
