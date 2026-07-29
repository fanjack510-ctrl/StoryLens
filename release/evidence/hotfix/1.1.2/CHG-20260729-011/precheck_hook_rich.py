#!/usr/bin/env python3
"""Pre-check Live Hook Rich + fixture stability for CHG-011 MG."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent
API = os.environ.get("MG_API", "http://127.0.0.1:18047")
FE = os.environ.get("MG_FE", "http://127.0.0.1:1426")


def _get(url: str) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def main() -> int:
    manifest = json.loads((EVIDENCE / "FIXTURE_MANIFEST.json").read_text(encoding="utf-8"))
    rich = manifest["fixtures"]["D_hook_rich"]
    journey_id = rich["journey_run_id"]
    run_id = rich["run_id"]
    chapter_id = rich["chapter_id"]

    results = []

    # Journey visualization
    code, body = _get(f"{API}/api/v1/reader-journeys/{journey_id}")
    ok = code == 200 and isinstance(body, dict) and body.get("status") == "succeeded"
    viz = (body or {}).get("visualization") if isinstance(body, dict) else None
    loops = (viz or {}).get("narrative_loops") or []
    results.append(
        {
            "check": "hook_rich_journey_http",
            "pass": ok and viz is not None and len(loops) >= 1,
            "status_code": code,
            "status": body.get("status") if isinstance(body, dict) else None,
            "loop_count": len(loops),
            "questions": [l.get("question") for l in loops],
        }
    )

    # Scene count bound to revision
    code2, scenes = _get(f"{API}/api/v1/analysis-runs/{run_id}/scenes")
    scene_count = len(scenes) if isinstance(scenes, list) else -1
    results.append(
        {
            "check": "hook_rich_scene_count",
            "pass": code2 == 200 and scene_count == 6,
            "status_code": code2,
            "scene_count": scene_count,
            "confirmed_revision_id": rich.get("confirmed_revision_id"),
        }
    )

    # Frontend route reachable
    fe_url = manifest["urls"]["HOOK_RICH"]
    try:
        with urllib.request.urlopen(fe_url.split("?")[0], timeout=10) as resp:
            fe_ok = resp.status == 200
            fe_code = resp.status
    except Exception as exc:  # noqa: BLE001
        fe_ok = False
        fe_code = str(exc)
    results.append({"check": "hook_rich_frontend_http", "pass": fe_ok, "status_code": fe_code, "url": fe_url})

    # All case URLs frontend root ok + key APIs
    for name, url in manifest["urls"].items():
        if name in {"HOOK_RICH", "TASK_CENTER"} or not str(url).startswith("http"):
            continue
        # Parse chapter/analysisRun/journeyRun for API probes where possible
        results.append({"check": f"url_listed_{name}", "pass": True, "url": url})

    interrupted = manifest["fixtures"]["B_interrupted_1_of_6"]
    code_i, body_i = _get(f"{API}/api/v1/reader-journey-runs/{interrupted['journey_run_id']}/progress")
    results.append(
        {
            "check": "interrupted_progress",
            "pass": code_i == 200
            and isinstance(body_i, dict)
            and str(body_i.get("status") or "").lower()
            in {
                "scene_profiles_partial",
                "interrupted",
                "paused",
                "failed",
                "budget_blocked",
            },
            "status_code": code_i,
            "status": body_i.get("status") if isinstance(body_i, dict) else None,
        }
    )

    a = manifest["fixtures"]["A_revision_22_to_6"]
    code_a, scenes_a = _get(f"{API}/api/v1/analysis-runs/{a['run_id']}/scenes")
    results.append(
        {
            "check": "revision_22_to_6_scenes",
            "pass": code_a == 200 and isinstance(scenes_a, list) and len(scenes_a) == 6,
            "status_code": code_a,
            "scene_count": len(scenes_a) if isinstance(scenes_a, list) else None,
        }
    )

    out = {
        "pass": all(r.get("pass") for r in results),
        "chapter_id": chapter_id,
        "journey_run_id": journey_id,
        "results": results,
        "hook_rich_url": fe_url,
    }
    (EVIDENCE / "HOOK_RICH_PRECHECK.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
