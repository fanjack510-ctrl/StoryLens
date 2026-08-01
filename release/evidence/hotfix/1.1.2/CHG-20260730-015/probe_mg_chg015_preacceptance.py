#!/usr/bin/env python3
"""CHG-015 auto pre-acceptance + wait-gate probe (Fake Provider only).

D_success_wait_gate stays awaiting for manual UI.
D_auto_wait_gate is consumed by this probe for SCENE WAIT GATE evidence.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent
MANIFEST = EVIDENCE / "FIXTURE_MANIFEST.json"
API = os.environ.get("MG_API_BASE", "http://127.0.0.1:18049")


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{API}{path}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _run(run_id: int) -> dict:
    return _get(f"/api/v1/analysis-runs/{run_id}")


def _journey_progress(journey_id: int) -> dict:
    return _get(f"/api/v1/reader-journey-runs/{journey_id}/progress")


def check_scene_failure(fx: dict) -> dict:
    run = _run(fx["run_id"])
    ok = (
        run.get("status") == "failed_structural"
        and run.get("failed_stage") == "scene_analysis"
        and run.get("root_error_code") == "STRUCTURAL_VALIDATION_FAILED"
        and int(run.get("completed_scene_count") or run.get("progress_current") or 0) == 0
        and int(run.get("total_scene_count") or run.get("progress_total") or 3) == 3
        and not run.get("journey_status")
        and run.get("journey_error_code") not in {"JOURNEY_INTERRUPTED"}
    )
    return {
        "pass": ok,
        "run": {
            "status": run.get("status"),
            "failed_stage": run.get("failed_stage"),
            "root_error_code": run.get("root_error_code"),
            "completed_scene_count": run.get("completed_scene_count"),
            "total_scene_count": run.get("total_scene_count"),
            "journey_status": run.get("journey_status"),
            "journey_error_code": run.get("journey_error_code"),
            "effective_status": run.get("effective_status"),
        },
    }


def check_synthesis_failure(fx: dict) -> dict:
    run = _run(fx["run_id"])
    progress = _journey_progress(fx["journey_run_id"])
    stage = str(progress.get("failed_stage") or progress.get("current_stage") or "")
    ok = (
        int(run.get("completed_scene_count") or 0) >= 3
        and run.get("journey_status") == "failed"
        and (
            run.get("journey_error_code") == "JOURNEY_SYNTHESIS_FAILED"
            or progress.get("root_error_code") == "JOURNEY_SYNTHESIS_FAILED"
        )
        and "synth" in stage.lower()
    )
    return {
        "pass": ok,
        "run": {
            "status": run.get("status"),
            "journey_status": run.get("journey_status"),
            "journey_error_code": run.get("journey_error_code"),
            "completed_scene_count": run.get("completed_scene_count"),
            "total_scene_count": run.get("total_scene_count"),
            "effective_status": run.get("effective_status"),
        },
        "progress": {
            "failed_stage": progress.get("failed_stage"),
            "root_error_code": progress.get("root_error_code"),
            "status": progress.get("status"),
            "completed_scene_count": progress.get("completed_scene_count"),
        },
    }


def check_recoverable(fx: dict) -> dict:
    run = _run(fx["run_id"])
    progress = _journey_progress(fx["journey_run_id"])
    ok = (
        (
            run.get("journey_error_code") == "JOURNEY_INTERRUPTED"
            or progress.get("root_error_code") == "JOURNEY_INTERRUPTED"
        )
        and (
            run.get("journey_retryable") is True
            or progress.get("retryable") is True
            or progress.get("recovery_safe") is True
        )
        and int(progress.get("completed_scene_count") or 0) >= 1
    )
    return {
        "pass": ok,
        "run": {
            "status": run.get("status"),
            "journey_status": run.get("journey_status"),
            "journey_error_code": run.get("journey_error_code"),
            "journey_run_id": run.get("journey_run_id"),
            "journey_retryable": run.get("journey_retryable"),
            "effective_status": run.get("effective_status"),
        },
        "progress": {
            "status": progress.get("status"),
            "root_error_code": progress.get("root_error_code"),
            "retryable": progress.get("retryable"),
            "recovery_safe": progress.get("recovery_safe"),
            "completed_scene_count": progress.get("completed_scene_count"),
            "remaining_scene_count": progress.get("remaining_scene_count"),
        },
    }


def probe_success_wait_gate(fx: dict) -> dict:
    """Confirm 3 scenes on auto twin and assert wait-gate then auto journey success."""
    chapter_id = fx["chapter_id"]
    draft_id = fx["draft_revision_id"]
    etag = fx["draft_etag"]
    analysis_run_id = fx["run_id"]

    confirm_path = (
        f"/api/v1/chapters/{chapter_id}/scene-boundaries/draft/{draft_id}/confirm"
    )
    try:
        confirm = _post(
            confirm_path,
            {"expected_etag": etag, "start_journey": True},
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"pass": False, "error": f"confirm HTTP {exc.code}: {body}"}

    revision_id = confirm.get("confirmed_revision_id") or confirm.get("revision_id")
    journey_id = confirm.get("journey_run_id")
    waiting_seen = False
    incomplete_seen = False
    scene_stage_completed_before_commit = False
    scene_analysis_phase_seen = False
    statuses = []
    final = None
    journey_ids = set()
    if journey_id:
        journey_ids.add(int(journey_id))

    deadline = time.time() + 240
    while time.time() < deadline:
        run = _run(analysis_run_id)
        jid = run.get("journey_run_id") or journey_id
        progress = None
        if jid:
            journey_ids.add(int(jid))
            try:
                progress = _journey_progress(int(jid))
            except Exception:
                progress = None
        row = {
            "t": time.time(),
            "status": run.get("status"),
            "effective_status": run.get("effective_status"),
            "journey_status": run.get("journey_status"),
            "journey_error_code": run.get("journey_error_code"),
            "completed_scene_count": run.get("completed_scene_count"),
            "total_scene_count": run.get("total_scene_count"),
            "journey_run_id": jid,
            "progress_root_error_code": (progress or {}).get("root_error_code"),
            "progress_status": (progress or {}).get("status"),
            "progress_completed": (progress or {}).get("completed_scene_count"),
        }
        statuses.append(row)

        eff = str(run.get("effective_status") or "")
        jerr = run.get("journey_error_code")
        perr = (progress or {}).get("root_error_code")
        if (
            perr == "WAITING_SCENE_ANALYSIS"
            or jerr == "WAITING_SCENE_ANALYSIS"
            or eff == "scene_analysis"
            or run.get("status") == "scene_analysis_running"
        ):
            waiting_seen = True
            scene_analysis_phase_seen = True
        if perr == "SCENE_ANALYSIS_INCOMPLETE" or jerr == "SCENE_ANALYSIS_INCOMPLETE":
            incomplete_seen = True
        # Scene stage marked complete while still missing scene results.
        if (
            run.get("status") == "succeeded"
            and int(run.get("completed_scene_count") or 0) < 3
            and eff not in {"scene_analysis", "awaiting_scene_boundary_confirmation"}
        ):
            scene_stage_completed_before_commit = True

        if (
            run.get("journey_status") == "succeeded"
            or run.get("chapter_complete") is True
            or eff == "completed"
        ):
            final = run
            break
        if run.get("journey_status") == "failed" and (jerr or perr) not in {
            None,
            "WAITING_SCENE_ANALYSIS",
        }:
            final = run
            break
        time.sleep(0.35)

    if final is None:
        final = _run(analysis_run_id)

    ok = (
        (waiting_seen or scene_analysis_phase_seen)
        and not incomplete_seen
        and not scene_stage_completed_before_commit
        and final.get("journey_status") == "succeeded"
        and int(final.get("total_scene_count") or 3) == 3
        and len(journey_ids) == 1
    )
    return {
        "pass": ok,
        "confirm": confirm,
        "waiting_seen": waiting_seen,
        "scene_analysis_phase_seen": scene_analysis_phase_seen,
        "incomplete_seen": incomplete_seen,
        "scene_stage_completed_before_commit": scene_stage_completed_before_commit,
        "journey_start_count": len(journey_ids),
        "duplicate_runs": max(0, len(journey_ids) - 1),
        "confirmed_revision_id": revision_id,
        "journey_run_id": final.get("journey_run_id") or journey_id,
        "analysis_run_id": analysis_run_id,
        "final": {
            "status": final.get("status"),
            "effective_status": final.get("effective_status"),
            "journey_status": final.get("journey_status"),
            "journey_error_code": final.get("journey_error_code"),
            "completed_scene_count": final.get("completed_scene_count"),
            "total_scene_count": final.get("total_scene_count"),
            "chapter_complete": final.get("chapter_complete"),
        },
        "status_trace_tail": statuses[:12] + statuses[-8:],
    }


def snapshot_all(manifest: dict) -> dict:
    snaps = {}
    for key, fx in manifest["fixtures"].items():
        run_id = fx.get("run_id")
        if not run_id:
            continue
        run = _run(run_id)
        snaps[key] = {
            "run_id": run_id,
            "status": run.get("status"),
            "effective_status": run.get("effective_status"),
            "journey_status": run.get("journey_status"),
            "journey_error_code": run.get("journey_error_code"),
            "journey_run_id": run.get("journey_run_id"),
            "completed_scene_count": run.get("completed_scene_count"),
            "total_scene_count": run.get("total_scene_count"),
        }
    return snaps


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report = {
        "change_id": "CHG-20260730-015",
        "api": API,
        "scene_failure": check_scene_failure(manifest["fixtures"]["A_scene_failure"]),
        "synthesis_failure": check_synthesis_failure(
            manifest["fixtures"]["B_synthesis_failure"]
        ),
        "recoverable": check_recoverable(manifest["fixtures"]["C_recoverable"]),
        "manual_success_fixture": {
            "status": manifest["fixtures"]["D_success_wait_gate"].get("status"),
            "url": manifest["urls"]["SUCCESS"],
            "awaiting_confirm": True,
        },
        "success_wait_gate": None,
        "snapshot_before_success": snapshot_all(manifest),
    }
    auto_fx = manifest["fixtures"].get("D_auto_wait_gate") or manifest["fixtures"][
        "D_success_wait_gate"
    ]
    report["success_wait_gate"] = probe_success_wait_gate(auto_fx)
    sw = report["success_wait_gate"]
    if sw.get("pass"):
        auto_fx.update(
            {
                "confirmed_revision_id": sw.get("confirmed_revision_id"),
                "journey_run_id": sw.get("journey_run_id"),
                "status": "succeeded_auto_probe",
                "scene_count": 3,
            }
        )
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    out = EVIDENCE / "AUTO_PREACCEPTANCE.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    fails = [
        k
        for k, v in {
            "scene_failure": report["scene_failure"],
            "synthesis_failure": report["synthesis_failure"],
            "recoverable": report["recoverable"],
            "success_wait_gate": report["success_wait_gate"],
        }.items()
        if not v.get("pass")
    ]
    if fails:
        print(f"FAILED: {fails}", file=sys.stderr)
        sys.exit(1)
    print("AUTO PREACCEPTANCE: PASS")


if __name__ == "__main__":
    main()
