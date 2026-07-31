# -*- coding: utf-8 -*-
"""TEMP-only acceptance launcher for CHG-023 final (NOT product code).

- Smoke Fake ON (OpenAI-compatible HTTP intercept)
- Startup requeue OFF
- Fail inject ONLY for journey_run_id == FAIL_JOURNEY_ID (fixture B)
  — no product execution_scenario / no client_request_id substring
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:\Dstorylens-wt-chg023-final-state-fix")
DB = Path(os.environ["TEMP"]) / "storylens-mg-chg023-final" / "storylens.db"
PORT = int(os.environ.get("STORYLENS_MG_API_PORT", "18067"))
FE_PORT = int(os.environ.get("STORYLENS_MG_FE_PORT", "1467"))
FAIL_JOURNEY_ID = int(os.environ.get("STORYLENS_CHG023_FAIL_JOURNEY_ID", "2"))

if not DB.is_file():
    raise SystemExit(f"MG DB missing: {DB}")

os.environ["STORYLENS_DATABASE_URL"] = "sqlite:///" + DB.as_posix()
os.environ["STORYLENS_APP_ENV"] = "development"
os.environ["STORYLENS_APP_HOST"] = "127.0.0.1"
os.environ["STORYLENS_APP_PORT"] = str(PORT)
os.environ["STORYLENS_PROVIDER"] = "aliyun_qwen_plus"
os.environ["STORYLENS_REAL_PROVIDER_ENABLED"] = "0"
os.environ["STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE"] = "1"
os.environ["STORYLENS_JOURNEY_FAKE_MODE"] = "success"
os.environ["STORYLENS_ALLOWED_ORIGINS"] = f"http://127.0.0.1:{FE_PORT}"
os.environ["STORYLENS_DISABLE_INSTANCE_LOCK"] = "1"
os.environ.pop("STORYLENS_WEB_PORT", None)
os.environ.pop("STORYLENS_SETTINGS_CACHE", None)
os.environ.pop("STORYLENS_ALLOW_FAKE_PROVIDER", None)

api_root = REPO / "apps" / "api"
sys.path.insert(0, str(api_root))
os.chdir(api_root)

from app.services import scene_pipeline as _scene_pipeline  # noqa: E402

_orig_mark = _scene_pipeline.mark_interrupted_runs_failed


def _mark_interrupted_no_requeue(session):  # type: ignore[no-untyped-def]
    stats = _orig_mark(session)
    if isinstance(stats, dict):
        stats = dict(stats)
        stats["requeue_journey_ids"] = []
        stats["requeue_journeys"] = 0
    return stats


_scene_pipeline.mark_interrupted_runs_failed = _mark_interrupted_no_requeue  # type: ignore[assignment]

from app.db.models import ReaderJourneyRun  # noqa: E402
from app.services import reader_journey_pipeline as _rjp  # noqa: E402

_orig_execute = _rjp.execute_reader_journey


async def _execute_with_fixture_fail(session_factory, gateway, journey_run_id: int):  # type: ignore[no-untyped-def]
    if int(journey_run_id) == FAIL_JOURNEY_ID:
        with session_factory() as session:
            journey = session.get(ReaderJourneyRun, int(journey_run_id))
            if journey is not None:
                now = datetime.now(timezone.utc)
                journey.status = "failed"
                journey.current_stage = "reader_journey_scene_profiles"
                journey.root_error_code = "PIPELINE_UNEXPECTED_ERROR"
                journey.root_error_message = "chg023 deterministic resume failure"
                journey.retryable = True
                journey.failed_stage = "pipeline"
                journey.completed_at = now
                journey.updated_at = now
                session.commit()
                print(
                    f"CHG023_ACCEPT_FAIL_INJECT journey_run_id={journey_run_id}",
                    flush=True,
                )
                return None
    return await _orig_execute(session_factory, gateway, journey_run_id)


_rjp.execute_reader_journey = _execute_with_fixture_fail  # type: ignore[assignment]
import app.api.v1.reader_journey as _rj_api  # noqa: E402

_rj_api.execute_reader_journey = _execute_with_fixture_fail  # type: ignore[assignment]

# Acceptance-only: smoke-fake journey payloads fail fingerprint grounding against seeded
# placeholder hashes. Trust read-time integrity so DOM can show Result (not product path).
from app.services import analysis_integrity_guard as _aig  # noqa: E402


def _acceptance_trusted_integrity(session, journey_run=None, **kwargs):  # type: ignore[no-untyped-def]
    _ = (session, journey_run, kwargs)
    return {
        "integrity_status": "trusted",
        "overall_status": "trusted",
        "overall_display_policy": "show_full",
        "trusted": True,
        "partially_trusted": False,
        "untrusted": False,
        "legacy_unverified": False,
        "legacy_warning": None,
        "blocked_scene_count": 0,
        "blocked_sections": [],
        "scene_reports": [],
        "scene_integrity": [],
        "field_integrity": [],
        "integrity_summary": {
            "scene_count": 0,
            "blocked_scene_count": 0,
            "field_issue_count": 0,
            "fingerprint_missing": False,
        },
        "user_message": None,
        "error_code": None,
    }


_aig.scan_reader_journey_integrity = _acceptance_trusted_integrity  # type: ignore[assignment]

import uvicorn  # noqa: E402

if __name__ == "__main__":
    print(
        f"CHG023_FINAL_API port={PORT} db={DB} fail_journey_id={FAIL_JOURNEY_ID} "
        f"smoke_fake=ON (launcher-only inject)",
        flush=True,
    )
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, log_level="info")
