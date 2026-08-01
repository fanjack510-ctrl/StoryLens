# -*- coding: utf-8 -*-
"""TEST-ONLY API launcher for CHG-029/030 smoke v2. Not product code.

- Binds 127.0.0.1 only
- Uses chg029_smoke_v2.db
- Smoke-fake ON (no external network)
- Fail-inject ONLY for fail_journey_run_id from MANUAL_FIXTURES.json
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SMOKE_ROOT = Path(
    os.environ.get(
        "STORYLENS_CHG029_SMOKE_ROOT",
        Path(os.environ["TEMP"]) / "storylens-chg029-smoke-v2",
    )
)
DB = SMOKE_ROOT / "chg029_smoke_v2.db"
FIXTURES = SMOKE_ROOT / "MANUAL_FIXTURES.json"
PORT = int(os.environ.get("STORYLENS_CHG029_API_PORT", "8003"))
FE_PORT = int(os.environ.get("STORYLENS_CHG029_FE_PORT", "1423"))
PUBLIC_ROOT = Path(
    os.environ.get("STORYLENS_CHG029_PUBLIC_ROOT", r"D:\Dstorylens-wt-1.2.0-after-1.1.2")
)

if not DB.is_file():
    raise SystemExit(f"Smoke DB missing: {DB}")
if not FIXTURES.is_file():
    raise SystemExit(f"Fixtures missing: {FIXTURES}")

fail_journey_id = int(json.loads(FIXTURES.read_text(encoding="utf-8"))["fail_journey_run_id"])

os.environ["STORYLENS_DATABASE_URL"] = "sqlite:///" + DB.as_posix()
os.environ["STORYLENS_APP_ENV"] = "development"
os.environ["STORYLENS_APP_HOST"] = "127.0.0.1"
os.environ["STORYLENS_APP_PORT"] = str(PORT)
os.environ["STORYLENS_PROVIDER"] = "aliyun_qwen_plus"
os.environ["STORYLENS_REAL_PROVIDER_ENABLED"] = "0"
os.environ["STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED"] = "false"
os.environ["STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED"] = "true"
os.environ["STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED"] = "true"
os.environ["STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE"] = "1"
os.environ["STORYLENS_JOURNEY_FAKE_MODE"] = "success"
os.environ["STORYLENS_ALLOWED_ORIGINS"] = f"http://127.0.0.1:{FE_PORT}"
os.environ["STORYLENS_DISABLE_INSTANCE_LOCK"] = "1"
os.environ.pop("STORYLENS_WEB_PORT", None)
os.environ.pop("STORYLENS_SETTINGS_CACHE", None)
os.environ.pop("STORYLENS_ALLOW_FAKE_PROVIDER", None)

api_root = PUBLIC_ROOT / "apps" / "api"
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
    if int(journey_run_id) == int(fail_journey_id):
        with session_factory() as session:
            journey = session.get(ReaderJourneyRun, int(journey_run_id))
            if journey is not None:
                now = datetime.now(timezone.utc)
                journey.status = "failed"
                journey.current_stage = "reader_journey_scene_profiles"
                journey.root_error_code = "PIPELINE_UNEXPECTED_ERROR"
                journey.root_error_message = "chg029 deterministic resume failure"
                journey.retryable = True
                journey.failed_stage = "pipeline"
                journey.completed_at = now
                journey.updated_at = now
                session.commit()
                print(f"CHG029_SMOKE_FAIL_INJECT journey_run_id={journey_run_id}", flush=True)
                return None
    return await _orig_execute(session_factory, gateway, journey_run_id)


_rjp.execute_reader_journey = _execute_with_fixture_fail  # type: ignore[assignment]
import app.api.v1.reader_journey as _rj_api  # noqa: E402

_rj_api.execute_reader_journey = _execute_with_fixture_fail  # type: ignore[assignment]

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
_rj_api.scan_reader_journey_integrity = _acceptance_trusted_integrity  # type: ignore[assignment]

import uvicorn  # noqa: E402

if __name__ == "__main__":
    print(
        f"CHG029_SMOKE_API port={PORT} db={DB} fail_journey_id={fail_journey_id} "
        f"smoke_fake=ON localhost-only",
        flush=True,
    )
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, log_level="info", ws="none")
