# -*- coding: utf-8 -*-
"""Run desktop e2e three times and write stability report for Phase 1D-B1."""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "apps" / "desktop"
OUT = ROOT / "audits" / "single-chapter-pipeline" / "e2e-stability-report-v1.json"
LOG_DIR = ROOT / "artifacts" / "single-chapter-pipeline-certification" / "e2e-logs"
E2E_PORT = 1421


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def free_e2e_port() -> list[str]:
    """Stop leftover Vite/Playwright servers on the e2e port to avoid reuseExistingServer flakes."""
    notes: list[str] = []
    if os.name != "nt":
        return notes
    try:
        probe = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    f"$conns = Get-NetTCPConnection -LocalPort {E2E_PORT} -ErrorAction SilentlyContinue | "
                    "Where-Object { $_.State -eq 'Listen' }; "
                    "foreach ($c in $conns) { "
                    "  $p = Get-CimInstance Win32_Process -Filter \"ProcessId=$($c.OwningProcess)\" -ErrorAction SilentlyContinue; "
                    "  if ($null -eq $p) { continue }; "
                    "  $cmd = [string]$p.CommandLine; "
                    "  if ($cmd -match 'Dstorylens' -and ($cmd -match 'vite|playwright|test:e2e')) { "
                    f"    Stop-Process -Id $($c.OwningProcess) -Force -ErrorAction SilentlyContinue; "
                    "    Write-Output \"killed pid=$($c.OwningProcess)\" "
                    "  } else { Write-Output \"skip pid=$($c.OwningProcess)\" } "
                    "}"
                ),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        for line in (probe.stdout or "").splitlines():
            line = line.strip()
            if line:
                notes.append(line)
    except OSError as exc:
        notes.append(f"port_cleanup_error={exc}")
    # Brief settle so TIME_WAIT / bind races clear.
    time.sleep(2)
    return notes


def run_once(index: int) -> dict:
    started = time.perf_counter()
    cleanup_notes = free_e2e_port()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    # Certification isolation: workers=1 reduces shared Run #55 / API contention flakes.
    # Still a full suite (no selective retry); does not edit frozen UI or lengthen timeouts.
    proc = subprocess.run(
        "npm run test:e2e -- --workers=1",
        cwd=DESKTOP,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        shell=True,
        env=env,
    )
    elapsed = time.perf_counter() - started
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    combined = stdout + "\n" + stderr
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"e2e-run-{index}.log"
    log_path.write_text(combined, encoding="utf-8")

    summary_pass = None
    failed_titles: list[str] = []
    for line in combined.splitlines():
        stripped = line.strip()
        # Playwright failure rows look like: "x   3 e2e\..." or start with ✘
        if stripped.startswith("x ") or stripped.startswith("✘") or stripped.startswith("X "):
            failed_titles.append(stripped[:240])
    for line in combined.splitlines()[::-1]:
        if "passed" in line and ("failed" in line or " passed (" in line or line.strip().endswith("passed")):
            summary_pass = line.strip()
            break

    return {
        "run_index": index,
        "exit_code": proc.returncode,
        "elapsed_seconds": round(elapsed, 2),
        "passed": proc.returncode == 0,
        "summary_line": summary_pass,
        "timeout_mentions": combined.lower().count("timeout"),
        "retry_mentions": combined.lower().count("retry"),
        "port_cleanup": cleanup_notes,
        "log_path": log_path.as_posix(),
        "failed_line_samples": failed_titles[:20],
        "captured_at": utc_now(),
    }


def _safe_print(text: str) -> None:
    """Windows consoles may be GBK; never abort the triple on print encoding."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("utf-8", errors="replace").decode("ascii", errors="replace"), flush=True)


def main() -> int:
    # Prefer UTF-8 console when available (Python 3.7+).
    try:
        import sys

        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    runs = []
    for i in range(1, 4):
        _safe_print(f"=== E2E stability run {i}/3 ===")
        result = run_once(i)
        runs.append(result)
        _safe_print(json.dumps(result, ensure_ascii=True))
        # Continue all 3 runs for flake evidence even after a failure.

    flake_count = sum(1 for r in runs if not r["passed"])
    all_passed = all(r["passed"] for r in runs) and len(runs) == 3
    payload = {
        "runs": runs,
        "all_passed": all_passed,
        "flake_count": flake_count,
        "result": "PASS" if all_passed else "FAIL",
        "slowest_run_seconds": max((r["elapsed_seconds"] for r in runs), default=None),
        "note": (
            "Three consecutive full npm run test:e2e -- --workers=1 executions; "
            "no selective retry of failed cases; "
            "port 1421 cleaned of leftover Dstorylens vite/playwright before each run."
        ),
        "workers": 1,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not all_passed:
        flake_report = {
            "title": "E2E Flake Report",
            "result": "FAIL",
            "failed_runs": [r for r in runs if not r["passed"]],
            "policy": "Do not edit frozen UI to silence flakes in Phase 1D-B1",
            "likely_causes": [
                "playwright.config.ts reuseExistingServer=true with stale Vite on :1421",
                "machine load / Edge channel contention",
            ],
            "harness_mitigation": "scripts/run_e2e_stability_triple.py frees Dstorylens listeners on :1421 before each run",
        }
        (
            ROOT
            / "audits"
            / "single-chapter-pipeline"
            / "e2e-flake-report-v1.json"
        ).write_text(json.dumps(flake_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _safe_print("E2E stability RESULT: " + payload["result"])
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
