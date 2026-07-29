#!/usr/bin/env python3
"""Seed isolated Manual Gate DB for CHG-20260729-011 (Fake Provider, zero real calls).

Does NOT touch formal AppData storylens.db.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
DEFAULT_DATA = Path(os.environ.get("TEMP", "/tmp")) / "storylens-mg-chg011-workflow-consistency"
DEFAULT_DB = DEFAULT_DATA / "database" / "storylens-mg-chg011.db"
FORMAL_DB = Path.home() / "AppData" / "Local" / "StoryLens" / "database" / "storylens.db"
API_PORT = 18047
FE_PORT = 1426


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _assert_isolated_db(db_path: Path) -> None:
    resolved = db_path.resolve()
    if resolved == FORMAL_DB.resolve():
        raise SystemExit(f"Refusing formal AppData DB: {resolved}")
    local = Path.home() / "AppData" / "Local" / "StoryLens"
    try:
        resolved.relative_to(local.resolve())
        raise SystemExit(f"Refusing write under formal StoryLens tree: {resolved}")
    except ValueError:
        pass


def _enable_cloud(session) -> None:
    from app.db.models import ApplicationSetting
    from app.schemas.settings import CloudBudgetUpdate

    session.merge(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True)))
    payload = CloudBudgetUpdate().model_dump()
    payload.update(
        {
            "cloud_daily_request_limit": 500,
            "cloud_daily_token_limit": 2_000_000,
            "cloud_daily_estimated_cost_limit": 50.0,
            "cloud_max_requests_per_run": 200,
        }
    )
    session.merge(
        ApplicationSetting(key="cloud_budget_settings", value_json=json.dumps(payload))
    )
    session.commit()


def _seed_chapter_base(session, *, book, chapter_index: int, title: str, paragraph_count: int):
    from app.db.models import Chapter, Paragraph

    chapter = Chapter(
        book_id=book.id,
        chapter_index=chapter_index,
        title=title,
        display_title=title,
        section_type="chapter",
    )
    session.add(chapter)
    session.flush()
    paragraphs: list[Paragraph] = []
    prefix = f"B{book.id:04d}-C{chapter.id:04d}"
    for index in range(1, paragraph_count + 1):
        body = f"第{index}段：{title} — CHG-011 MG 探针文本。"
        paragraph = Paragraph(
            id=f"{prefix}-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=body,
            normalized_text=body,
            char_start=index * 10,
            char_end=index * 10 + len(body),
        )
        session.add(paragraph)
        paragraphs.append(paragraph)
    session.flush()
    return chapter, paragraphs


def _seed_six_scene_run(session, book, chapter, paragraphs):
    """Confirmed 6-scene succeeded run + revision (no journey)."""
    from app.db.models import AnalysisRun, BoundaryReviewSession, BoundaryRevision

    from tests.test_chg041_scene_boundary_manual_review import _attach_scene_analysis
    from app.services.scene_boundary_manual_review import (
        confirm_scene_revision_v1,
        create_or_get_scene_boundary_draft_v1,
        ensure_ai_model_revision_after_scenes_v1,
    )

    # Reuse chg041 helper shape but scoped to our chapter/book.
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="aliyun_qwen_plus",
        model="qwen-plus",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash=hashlib.sha256(f"run-{chapter.id}".encode()).hexdigest(),
        status="succeeded",
        execution_mode="cloud",
        cloud_consent=True,
        sends_content_to_cloud=True,
        completed_at=_utc_now(),
    )
    session.add(run)
    session.flush()

    per_scene = max(1, len(paragraphs) // 6)
    from app.db.models import Scene

    scenes: list[Scene] = []
    start_idx = 0
    prefix = f"B{book.id:04d}-C{chapter.id:04d}"
    for ordinal in range(1, 7):
        end_idx = start_idx + per_scene - 1 if ordinal < 6 else len(paragraphs) - 1
        start_p = paragraphs[start_idx]
        end_p = paragraphs[end_idx]
        content = "\n".join(p.normalized_text for p in paragraphs[start_idx : end_idx + 1])
        scene = Scene(
            scene_key=f"{prefix}-S{ordinal:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            ordinal=ordinal,
            start_paragraph_id=start_p.id,
            end_paragraph_id=end_p.id,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            created_by_run_id=run.id,
            boundary_detected=True,
            boundary_confidence=0.9,
            boundary_reason_json="[]",
            included_in_journey=True,
        )
        session.add(scene)
        scenes.append(scene)
        start_idx = end_idx + 1
    session.flush()
    _attach_scene_analysis(session, run, scenes)
    revision = ensure_ai_model_revision_after_scenes_v1(session, run)
    session.commit()
    return run, revision, scenes


def _seed_awaiting_confirmation(session, book, chapter, paragraphs):
    """Fixture C: AI 17 scenes confirmed, draft saved with 6 (not confirmed)."""
    from app.db.models import AnalysisRun, Scene
    from app.services.chapter_analysis_completion import (
        mark_scenes_complete_awaiting_boundary_confirmation,
    )
    from app.services.scene_boundary_manual_review import (
        create_or_get_scene_boundary_draft_v1,
        ensure_ai_model_revision_after_scenes_v1,
        save_scene_boundary_draft_v1,
    )
    from tests.test_chg041_scene_boundary_manual_review import _attach_scene_analysis

    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="aliyun_qwen_plus",
        model="qwen-plus",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash=hashlib.sha256(f"await-{chapter.id}".encode()).hexdigest(),
        status="succeeded",
        execution_mode="cloud",
        cloud_consent=True,
        sends_content_to_cloud=True,
        completed_at=_utc_now(),
    )
    session.add(run)
    session.flush()

    scene_count = 17
    per_scene = max(1, len(paragraphs) // scene_count)
    scenes: list[Scene] = []
    start_idx = 0
    prefix = f"B{book.id:04d}-C{chapter.id:04d}"
    for ordinal in range(1, scene_count + 1):
        end_idx = start_idx + per_scene - 1 if ordinal < scene_count else len(paragraphs) - 1
        start_p = paragraphs[start_idx]
        end_p = paragraphs[end_idx]
        content = "\n".join(p.normalized_text for p in paragraphs[start_idx : end_idx + 1])
        scene = Scene(
            scene_key=f"{prefix}-S{ordinal:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            ordinal=ordinal,
            start_paragraph_id=start_p.id,
            end_paragraph_id=end_p.id,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            created_by_run_id=run.id,
            boundary_detected=True,
            boundary_confidence=0.9,
            boundary_reason_json="[]",
            included_in_journey=True,
        )
        session.add(scene)
        scenes.append(scene)
        start_idx = end_idx + 1
    session.flush()
    _attach_scene_analysis(session, run, scenes)
    model_rev = ensure_ai_model_revision_after_scenes_v1(session, run)
    mark_scenes_complete_awaiting_boundary_confirmation(session, run)
    session.commit()

    # Build 6-scene partition covering full chapter.
    draft = create_or_get_scene_boundary_draft_v1(session, chapter.id)
    session.commit()
    chunk = max(1, len(paragraphs) // 6)
    partition = []
    pidx = 0
    for order in range(1, 7):
        start_p = paragraphs[pidx]
        end_idx = pidx + chunk - 1 if order < 6 else len(paragraphs) - 1
        end_p = paragraphs[end_idx]
        partition.append(
            {
                "scene_order": order,
                "start_paragraph_id": start_p.id,
                "end_paragraph_id": end_p.id,
                "included_in_journey": True,
            }
        )
        pidx = end_idx + 1
    saved = save_scene_boundary_draft_v1(
        session, draft.id, partition, expected_etag=draft.revision_etag
    )
    session.commit()
    return run, model_rev, saved


def _add_journey_profile(session, journey, scene, *, ordinal: int | None = None) -> None:
    from app.db.models import SceneReaderJourneyProfile

    session.add(
        SceneReaderJourneyProfile(
            reader_journey_run_id=journey.id,
            scene_id=scene.id,
            scene_ordinal=ordinal or scene.ordinal,
            scene_value_summary=f"MG profile S{scene.ordinal}",
            dominant_emotion="tension",
            engagement_score=55,
            confidence=0.8,
            validation_status="valid",
            payload_json="{}",
        )
    )


def _seed_journey_state(
    session,
    *,
    run,
    revision,
    scenes,
    book,
    chapter,
    status: str,
    completed: int,
    error_code: str | None = None,
):
    from app.db.models import ReaderJourneyRun

    total = len(scenes)
    completed_ids = [scenes[i].id for i in range(completed)]
    remaining_ids = [scenes[i].id for i in range(completed, total)]
    now = _utc_now()
    journey = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status=status,
        current_stage="reader_journey_scene_profiles",
        provider_name="aliyun_qwen_plus",
        model_name="qwen-plus",
        scene_prompt_version="v2.0",
        chapter_prompt_version="v2.0",
        scene_contract_version="2.0",
        chapter_contract_version="2.0",
        formula_version="1.0",
        genre="suspense",
        planner_version="1.1",
        total_scene_count=total,
        completed_scene_count=completed,
        remaining_scene_count=total - completed,
        completed_scene_ids_json=json.dumps(completed_ids),
        remaining_scene_ids_json=json.dumps(remaining_ids),
        cloud_consent=True,
        retryable=status in {"failed", "scene_profiles_partial"},
        root_error_code=error_code,
        root_error_message=(
            "应用重启或后台任务中断，阅读旅程未完成；可从已完成检查点恢复"
            if error_code
            else None
        ),
        client_request_id=f"chg011-journey-{chapter.id}",
        failure_details_json=json.dumps(
            {"interrupt": {"code": error_code}} if error_code else {}
        ),
        scene_revision_id=revision.id,
        scene_revision_no=revision.revision_number,
        included_scene_ids_json=json.dumps([s.id for s in scenes]),
        started_at=now - timedelta(minutes=5),
        updated_at=now,
        completed_at=now if status in {"failed", "scene_profiles_partial"} else None,
    )
    session.add(journey)
    session.flush()
    return journey


def _run_fake_journey(session_factory, journey_id: int) -> None:
    from app.model_gateway.registry import get_model_gateway
    from app.services.reader_journey_pipeline import execute_reader_journey

    gateway = get_model_gateway()
    asyncio.run(execute_reader_journey(session_factory, gateway, journey_id))


def seed_all(*, data_dir: Path, db_path: Path, run_fake_journey: bool) -> dict:
    _assert_isolated_db(db_path)
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for sub in ("logs", "uploads", "exports"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)

    db_url = f"sqlite:///{db_path.as_posix()}"
    os.environ["STORYLENS_DATABASE_URL"] = db_url
    os.environ["STORYLENS_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("STORYLENS_APP_ENV", "development")
    os.environ["STORYLENS_REAL_PROVIDER_ENABLED"] = "0"
    os.environ["STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE"] = "1"
    os.environ["STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL"] = "0"
    os.environ["STORYLENS_JOURNEY_FAKE_MODE"] = "success"

    sys.path.insert(0, str(REPO / "apps" / "api"))
    from app.core import config as config_mod

    config_mod.get_settings.cache_clear()

    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Scene
    from app.db.session import create_db
    from app.services.scene_boundary_manual_review import (
        confirm_scene_revision_and_start_journey_v1,
        create_or_get_scene_boundary_draft_v1,
    )
    from tests.test_workflow_consistency_chg011 import _seed_revision_binding_fixture

    create_db()
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    manifest: dict = {
        "change_id": "CHG-20260729-011",
        "database": str(db_path),
        "api": f"http://127.0.0.1:{API_PORT}",
        "frontend": f"http://127.0.0.1:{FE_PORT}",
        "real_provider_calls": 0,
        "formal_db_writes": 0,
        "fixtures": {},
    }

    with Session() as session:
        _enable_cloud(session)

        # Fixture A — revision contamination (22 in DB, API shows 6)
        data_a = _seed_revision_binding_fixture(session)
        book = data_a["book"]
        ch_a = data_a["chapter"]
        run_a = data_a["run_b"]
        journey_a = data_a["journey"]
        total_on_run_b = session.scalar(
            select(func.count()).select_from(Scene).where(Scene.created_by_run_id == run_a.id)
        )
        manifest["fixtures"]["A_revision_22_to_6"] = {
            "book_id": book.id,
            "chapter_id": ch_a.id,
            "run_id": run_a.id,
            "journey_run_id": journey_a.id,
            "confirmed_revision_id": data_a["revision_b"].id,
            "db_scene_count_on_run": int(total_on_run_b or 0),
            "api_expected_scene_count": 6,
        }

        # Fixture B — interrupted 1/6
        ch_b, paras_b = _seed_chapter_base(
            session,
            book=book,
            chapter_index=2,
            title="第二章 中断旅程",
            paragraph_count=30,
        )
        run_b, rev_b, scenes_b = _seed_six_scene_run(session, book, ch_b, paras_b)
        journey_b = _seed_journey_state(
            session,
            run=run_b,
            revision=rev_b,
            scenes=scenes_b,
            book=book,
            chapter=ch_b,
            status="scene_profiles_partial",
            completed=1,
            error_code="JOURNEY_INTERRUPTED",
        )
        _add_journey_profile(session, journey_b, scenes_b[0])
        session.commit()
        manifest["fixtures"]["B_interrupted_1_of_6"] = {
            "book_id": book.id,
            "chapter_id": ch_b.id,
            "run_id": run_b.id,
            "journey_run_id": journey_b.id,
            "completed_scene_count": 1,
            "total_scene_count": 6,
        }

        # Fixture C — awaiting confirmation (17 AI → draft 6)
        ch_c, paras_c = _seed_chapter_base(
            session,
            book=book,
            chapter_index=3,
            title="第三章 待确认场景",
            paragraph_count=85,
        )
        run_c, model_rev_c, draft_c = _seed_awaiting_confirmation(session, book, ch_c, paras_c)
        manifest["fixtures"]["C_awaiting_confirmation_17_to_6"] = {
            "book_id": book.id,
            "chapter_id": ch_c.id,
            "run_id": run_c.id,
            "model_revision_id": model_rev_c.id,
            "model_scene_count": 17,
            "draft_revision_id": draft_c.id,
            "draft_scene_count": 6,
        }

        # Running journey 2/6
        ch_d, paras_d = _seed_chapter_base(
            session,
            book=book,
            chapter_index=4,
            title="第四章 运行中旅程",
            paragraph_count=30,
        )
        run_d, rev_d, scenes_d = _seed_six_scene_run(session, book, ch_d, paras_d)
        journey_d = _seed_journey_state(
            session,
            run=run_d,
            revision=rev_d,
            scenes=scenes_d,
            book=book,
            chapter=ch_d,
            status="scene_profiles_running",
            completed=2,
        )
        for scene in scenes_d[:2]:
            _add_journey_profile(session, journey_d, scene)
        session.commit()
        manifest["fixtures"]["running_2_of_6"] = {
            "book_id": book.id,
            "chapter_id": ch_d.id,
            "run_id": run_d.id,
            "journey_run_id": journey_d.id,
        }

        # Succeeded + hook empty (Fake journey)
        ch_e, paras_e = _seed_chapter_base(
            session,
            book=book,
            chapter_index=5,
            title="第五章 成功旅程",
            paragraph_count=30,
        )
        run_e, rev_e, scenes_e = _seed_six_scene_run(session, book, ch_e, paras_e)
        draft_e = create_or_get_scene_boundary_draft_v1(session, ch_e.id)
        session.commit()
        _revision_e, journey_e, _, err = asyncio.run(
            confirm_scene_revision_and_start_journey_v1(
                session,
                draft_e.id,
                expected_etag=draft_e.revision_etag,
                start_journey=True,
                session_factory=Session,
                gateway=None,
            )
        )
        if err is not None:
            raise RuntimeError(f"Journey start failed for chapter 5: {err}")
        session.commit()
        journey_e_id = journey_e.id
        manifest["fixtures"]["E_succeeded_hook_empty"] = {
            "book_id": book.id,
            "chapter_id": ch_e.id,
            "run_id": run_e.id,
            "journey_run_id": journey_e_id,
            "note": "Fake smoke → hook uncertain/empty presentation",
        }

    if run_fake_journey:
        _run_fake_journey(Session, journey_e_id)
        with Session() as session:
            from app.db.models import ReaderJourneyRun

            refreshed = session.get(ReaderJourneyRun, journey_e_id)
            manifest["fixtures"]["E_succeeded_hook_empty"]["final_status"] = (
                refreshed.status if refreshed else None
            )

    fe = f"http://127.0.0.1:{FE_PORT}"
    fx = manifest["fixtures"]
    manifest["urls"] = {
        "REVISION_22_TO_6": (
            f"{fe}/books/{book.id}?chapter={fx['A_revision_22_to_6']['chapter_id']}"
            f"&analysisRun={fx['A_revision_22_to_6']['run_id']}&view=result"
        ),
        "INTERRUPTED": (
            f"{fe}/books/{book.id}?chapter={fx['B_interrupted_1_of_6']['chapter_id']}"
            f"&analysisRun={fx['B_interrupted_1_of_6']['run_id']}"
            f"&journeyRun={fx['B_interrupted_1_of_6']['journey_run_id']}"
        ),
        "AWAITING_CONFIRMATION": (
            f"{fe}/books/{book.id}?chapter={fx['C_awaiting_confirmation_17_to_6']['chapter_id']}"
            f"&analysisRun={fx['C_awaiting_confirmation_17_to_6']['run_id']}"
            f"&view=scene-boundary-review"
        ),
        "RUNNING": (
            f"{fe}/books/{book.id}?chapter={fx['running_2_of_6']['chapter_id']}"
            f"&analysisRun={fx['running_2_of_6']['run_id']}"
            f"&journeyRun={fx['running_2_of_6']['journey_run_id']}"
        ),
        "SUCCEEDED": (
            f"{fe}/books/{book.id}?chapter={fx['E_succeeded_hook_empty']['chapter_id']}"
            f"&analysisRun={fx['E_succeeded_hook_empty']['run_id']}"
            f"&journeyRun={fx['E_succeeded_hook_empty']['journey_run_id']}&view=result"
        ),
        "HOOK_EMPTY": (
            f"{fe}/books/{book.id}?chapter={fx['E_succeeded_hook_empty']['chapter_id']}"
            f"&journeyRun={fx['E_succeeded_hook_empty']['journey_run_id']}&lens=hook_payoff"
        ),
        "HOOK_RICH": "vitest://chg005FixtureBReliableHooks (frontend-only; see FIXTURES.md)",
        "TASK_CENTER": f"{fe}/tasks",
    }

    out = EVIDENCE / "FIXTURE_MANIFEST.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--skip-fake-journey",
        action="store_true",
        help="Skip execute_reader_journey for succeeded fixture (faster seed)",
    )
    args = parser.parse_args()
    manifest = seed_all(
        data_dir=args.data_dir,
        db_path=args.db_path,
        run_fake_journey=not args.skip_fake_journey,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
