"""Seed isolated MG DB for CHG-20260731-023 final acceptance (browser E2E).

Fixture A (B0231): interrupted journey, all scenes remaining, can resume — success path.
Fixture B (B0232): same shape — launcher injects deterministic resume failure.

Provider: aliyun_qwen_plus / qwen-plus (real gateway name; smoke-fake at API launch).
NO product journey_execution_scenario hooks.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent
REPO_ROOT = API_ROOT.parents[1]
sys.path.insert(0, str(API_ROOT))

MG_DIR_NAME = "storylens-mg-chg023-final"
mg_root = Path(os.environ.get("STORYLENS_MG_ROOT") or Path(os.environ["TEMP"]) / MG_DIR_NAME)
mg_root.mkdir(parents=True, exist_ok=True)
db_path = mg_root / "storylens.db"
if db_path.exists():
    db_path.unlink()
for suffix in ("-wal", "-shm"):
    side = Path(str(db_path) + suffix)
    if side.exists():
        side.unlink()

os.environ["STORYLENS_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
os.environ.setdefault("STORYLENS_PROVIDER", "aliyun_qwen_plus")
os.environ.pop("STORYLENS_ALLOW_FAKE_PROVIDER", None)
os.environ.pop("STORYLENS_SETTINGS_CACHE", None)

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db.models import (  # noqa: E402
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    ApplicationSetting,
    Book,
    BoundaryReviewSession,
    BoundaryRevision,
    Chapter,
    Paragraph,
    ReaderJourneyRun,
    Scene,
)
from app.db.session import create_db, get_session_factory  # noqa: E402
from app.schemas.settings import CloudBudgetUpdate  # noqa: E402
from app.services.reader_journey_recovery import JOURNEY_INTERRUPTED  # noqa: E402

PROVIDER = "aliyun_qwen_plus"
MODEL = "qwen-plus"
SCENE_COUNT = 4
FAILURE_DETAILS = {
    "scene_contract_version": "2.0",
    "source_mode": "v2_native",
}


def _enable_cloud(session) -> None:
    session.merge(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True)))
    payload = CloudBudgetUpdate().model_dump()
    payload.update(
        {
            "daily_request_limit": 500,
            "daily_token_limit": 2_000_000,
            "daily_cost_limit": 50.0,
        }
    )
    session.merge(
        ApplicationSetting(key="cloud_budget_settings", value_json=json.dumps(payload))
    )
    session.commit()


def _set_budget(session, *, requests: int = 50, tokens: int = 2_000_000, cost: float = 50.0) -> None:
    payload = CloudBudgetUpdate().model_dump()
    payload["cloud_daily_request_limit"] = requests
    payload["cloud_daily_token_limit"] = tokens
    payload["cloud_daily_estimated_cost_limit"] = cost
    session.merge(
        ApplicationSetting(key="cloud_budget_settings", value_json=json.dumps(payload))
    )
    session.merge(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True)))
    session.commit()


def _scene_payload(scene: Scene, paragraphs: list[Paragraph]) -> str:
    ids: list[str] = []
    collecting = False
    for item in paragraphs:
        if item.id == scene.start_paragraph_id:
            collecting = True
        if collecting:
            ids.append(item.id)
        if item.id == scene.end_paragraph_id:
            break
    first, last = ids[0], ids[-1]

    def field(summary: str, evidence: list[str]) -> dict:
        return {"summary": summary, "evidence_paragraph_ids": evidence}

    return json.dumps(
        {
            "scene_id": scene.scene_key,
            "entry_state": field(f"进入-{scene.ordinal}", [first]),
            "goal": field(f"目标-{scene.ordinal}", [first]),
            "obstacle": field("", []),
            "key_actions": [
                {"summary": f"行动-{scene.ordinal}", "evidence_paragraph_ids": [first]}
            ],
            "turning_point": field("", []),
            "outcome": field(f"结果-{scene.ordinal}", [last]),
            "unresolved_question": field("", []),
            "function_tags": ["事件推进"],
            "confidence": 0.8,
        },
        ensure_ascii=False,
    )

def _failure_details_json() -> str:
    payload = dict(FAILURE_DETAILS)
    assert "execution_scenario" not in payload
    return json.dumps(payload, ensure_ascii=False)


def _seed_confirmed(
    session,
    *,
    book_title: str,
    source_hash: str,
    book_code: str,
    input_hash: str,
    scene_count: int = SCENE_COUNT,
):
    book = Book(
        title=book_title,
        source_file_name=f"{book_code}.txt",
        source_file_hash=source_hash,
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title="第一章",
        display_title="第一章",
        section_type="chapter",
    )
    session.add(chapter)
    session.flush()
    paragraphs = []
    for index in range(1, scene_count * 2 + 1):
        row = Paragraph(
            id=f"{book_code}-C0001-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=f"段落正文{index}" * 4,
            normalized_text=f"段落正文{index}" * 4,
            char_start=index * 10,
            char_end=index * 10 + 8,
        )
        session.add(row)
        paragraphs.append(row)
    run = AnalysisRun(
        task_type="scene_pipeline",
        provider=PROVIDER,
        model=MODEL,
        prompt_version="v3.5",
        schema_version="v1",
        input_hash=input_hash,
        status="succeeded",
        subject_type="chapter",
        subject_id=str(chapter.id),
        prompt_hash="c" * 64,
        progress_current=scene_count,
        progress_total=scene_count,
        analysis_mode="assisted_boundary_review",
        execution_mode="local",
        cloud_consent=True,
        cloud_consent_at=datetime.now(timezone.utc),
        sends_content_to_cloud=False,
        status_version=1,
        book_id=book.id,
        start_chapter_id=chapter.id,
        end_chapter_id=chapter.id,
    )
    session.add(run)
    session.flush()
    review = BoundaryReviewSession(
        book_id=book.id,
        chapter_id=chapter.id,
        analysis_run_id=run.id,
        prompt_version="v3.5",
        provider=PROVIDER,
        model=MODEL,
        status="confirmed",
        candidate_count=0,
        accepted_count=0,
        rejected_count=0,
        manually_added_count=scene_count - 1,
        confirmed_by="tester",
        completed_at=datetime.now(timezone.utc),
    )
    session.add(review)
    session.flush()
    revision = BoundaryRevision(
        review_session_id=review.id,
        chapter_id=chapter.id,
        analysis_run_id=run.id,
        revision_number=1,
        final_boundaries_json=json.dumps(
            [
                {
                    "after_paragraph_id": paragraphs[index * 2 - 1].id,
                    "source": "user_added",
                }
                for index in range(1, scene_count)
            ],
            ensure_ascii=False,
        ),
        confirmed_by="tester",
        confirmed_at=datetime.now(timezone.utc),
        coverage_rate=1.0,
    )
    session.add(revision)
    session.flush()
    scenes = []
    for index in range(scene_count):
        start = paragraphs[index * 2]
        end = paragraphs[-1] if index == scene_count - 1 else paragraphs[index * 2 + 1]
        scene = Scene(
            scene_key=f"{book_code}-C0001-R0001-S{index + 1:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            ordinal=index + 1,
            start_paragraph_id=start.id,
            end_paragraph_id=end.id,
            content_hash="d" * 64,
            created_by_run_id=run.id,
            boundary_confidence=0.9,
            boundary_detected=True,
            boundary_revision_id=revision.id,
            boundary_source="user_added" if index < scene_count - 1 else None,
        )
        session.add(scene)
        scenes.append(scene)
    session.flush()
    for scene in scenes:
        art = AnalysisArtifact(
            run_id=run.id,
            artifact_type="scene_analysis",
            subject_type="scene",
            subject_id=str(scene.id),
            schema_version="v1",
            prompt_version="v1",
            payload_json=_scene_payload(scene, paragraphs),
            confidence=0.9,
            validation_status="valid",
        )
        session.add(art)
        session.flush()
        session.add(
            AnalysisEvidence(
                artifact_id=art.id,
                field_path="goal.evidence",
                paragraph_id=scene.start_paragraph_id,
                paragraph_hash="e" * 64,
            )
        )
    session.flush()
    return book, chapter, run, revision, scenes


def _seed_interrupted_all_remaining(
    session,
    *,
    book_title: str,
    source_hash: str,
    book_code: str,
    input_hash: str,
    client_request_id: str,
):
    book, chapter, run, rev, scenes = _seed_confirmed(
        session,
        book_title=book_title,
        source_hash=source_hash,
        book_code=book_code,
        input_hash=input_hash,
    )
    journey = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="scene_profiles_partial",
        current_stage="reader_journey_scene_profiles",
        provider_name=PROVIDER,
        model_name=MODEL,
        formula_version="v1",
        scene_prompt_version="v2.0",
        chapter_prompt_version="v2.0",
        scene_contract_version="2.0",
        chapter_contract_version="2.0",
        planner_version="1.1",
        client_request_id=client_request_id,
        cloud_consent=True,
        scene_revision_id=rev.id,
        scene_revision_no=rev.revision_number,
        retryable=True,
        root_error_code=JOURNEY_INTERRUPTED,
        root_error_message="fixture recoverable interrupt (all scenes remaining)",
        completed_scene_count=0,
        total_scene_count=len(scenes),
        remaining_scene_count=len(scenes),
        completed_scene_ids_json="[]",
        remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
        failure_details_json=_failure_details_json(),
        started_at=datetime.now(timezone.utc),
    )
    session.add(journey)
    session.flush()
    return book, chapter, run, rev, journey, scenes


def _copy_launcher() -> Path:
    src = (
        REPO_ROOT
        / "release/evidence/hotfix/1.1.2/CHG-20260731-023/acceptance/launch_api_accept.py"
    )
    if not src.is_file():
        raise SystemExit(f"Launcher missing: {src}")
    dst = mg_root / "launch_api_accept.py"
    shutil.copy2(src, dst)
    return dst


def main() -> None:
    assert MG_DIR_NAME in get_settings().database_url
    launcher = _copy_launcher()
    create_db()
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        _enable_cloud(session)
        _set_budget(session)

        book_a, chapter_a, run_a, rev_a, journey_a, _scenes_a = _seed_interrupted_all_remaining(
            session,
            book_title="CHG023 Final Resume Success",
            source_hash="a" * 64,
            book_code="B0231",
            input_hash="1" * 64,
            client_request_id="chg023-final-success",
        )
        book_b, chapter_b, run_b, rev_b, journey_b, _scenes_b = _seed_interrupted_all_remaining(
            session,
            book_title="CHG023 Final Resume Failure",
            source_hash="b" * 64,
            book_code="B0232",
            input_hash="2" * 64,
            client_request_id="chg023-final-fail",
        )
        session.commit()

        api = os.environ.get("STORYLENS_MG_API_URL", "http://127.0.0.1:18067")
        fe = os.environ.get("STORYLENS_MG_FE_URL", "http://127.0.0.1:1467")
        fixtures = {
            "change_id": "CHG-20260731-023",
            "database": str(db_path),
            "mg_root": str(mg_root),
            "launcher": str(launcher),
            "api_url": api,
            "frontend_url": fe,
            "provider": PROVIDER,
            "model": MODEL,
            "scene_count": SCENE_COUNT,
            "fail_journey_run_id": journey_b.id,
            "resume_success": {
                "book_code": "B0231",
                "book_id": book_a.id,
                "chapter_id": chapter_a.id,
                "analysis_run_id": run_a.id,
                "journey_run_id": journey_a.id,
                "confirmed_revision_id": rev_a.id,
                "client_request_id": "chg023-final-success",
                "url": (
                    f"{fe}/books/{book_a.id}?chapter={chapter_a.id}"
                    f"&analysisRun={run_a.id}&journeyRun={journey_a.id}"
                    f"&view=progress&tab=reader-journey"
                ),
            },
            "resume_failure": {
                "book_code": "B0232",
                "book_id": book_b.id,
                "chapter_id": chapter_b.id,
                "analysis_run_id": run_b.id,
                "journey_run_id": journey_b.id,
                "confirmed_revision_id": rev_b.id,
                "client_request_id": "chg023-final-fail",
                "url": (
                    f"{fe}/books/{book_b.id}?chapter={chapter_b.id}"
                    f"&analysisRun={run_b.id}&journeyRun={journey_b.id}"
                    f"&view=progress&tab=reader-journey"
                ),
            },
            "real_provider_calls": 0,
            "formal_db_writes": 0,
        }

    out = (
        REPO_ROOT
        / "release/evidence/hotfix/1.1.2/CHG-20260731-023/acceptance/MANUAL_FIXTURES.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(fixtures, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
