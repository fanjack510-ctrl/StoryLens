#!/usr/bin/env python3
"""Seed isolated Manual Gate DB for CHG-20260730-015 (Fake Provider, zero real calls).

Fixtures:
  A — Scene analysis structural failure (0/3, journey not started)
  B — Journey synthesis failure (3/3 scenes done)
  C — Recoverable journey interrupt (claimed + lease expired, can_resume)
  D — Success wait-gate: AI 2 scenes → draft 3 awaiting confirm

Does NOT touch formal AppData storylens.db.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
DEFAULT_DATA = Path(os.environ.get("TEMP", "/tmp")) / "storylens-mg-chg015-rc4-failure"
DEFAULT_DB = DEFAULT_DATA / "database" / "storylens-mg-chg015.db"
FORMAL_DB = Path.home() / "AppData" / "Local" / "StoryLens" / "database" / "storylens.db"
API_PORT = 18049
FE_PORT = 1428


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


def _seed_book(session, title: str = "CHG-015 RC.4 Failure Consistency MG"):
    from app.db.models import Book

    book = Book(
        title=title,
        source_file_name="chg015-mg-fixture.txt",
        source_file_hash=hashlib.sha256(title.encode()).hexdigest(),
    )
    session.add(book)
    session.flush()
    return book


def _seed_chapter_base(session, *, book, chapter_index: int, title: str, paragraph_count: int):
    from app.db.models import Chapter, Paragraph

    chapter = Chapter(
        book_id=book.id,
        chapter_index=chapter_index,
        title=title,
        section_type="chapter",
    )
    session.add(chapter)
    session.flush()
    paragraphs = []
    prefix = f"B{book.id:04d}-C{chapter.id:04d}"
    for index in range(1, paragraph_count + 1):
        body = f"第{index}段：{title} — CHG-015 MG 探针文本，巷口灯影摇晃，案情线索逐渐浮现。"
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


def _new_run(session, chapter, *, status: str, suffix: str) -> "AnalysisRun":
    from app.db.models import AnalysisRun

    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="aliyun_qwen_plus",
        model="qwen-plus",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash=hashlib.sha256(f"{suffix}-{chapter.id}".encode()).hexdigest(),
        status=status,
        execution_mode="cloud",
        cloud_consent=True,
        sends_content_to_cloud=True,
        completed_at=_utc_now() if status == "succeeded" else None,
    )
    session.add(run)
    session.flush()
    return run


def _make_scenes(session, book, chapter, paragraphs, run, scene_count: int):
    from app.db.models import Scene

    scenes = []
    per = max(1, len(paragraphs) // scene_count)
    start_idx = 0
    prefix = f"B{book.id:04d}-C{chapter.id:04d}"
    for ordinal in range(1, scene_count + 1):
        end_idx = start_idx + per - 1 if ordinal < scene_count else len(paragraphs) - 1
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
    return scenes


def _attach_scene_analysis(session, run, scenes) -> None:
    from tests.test_chg041_scene_boundary_manual_review import _attach_scene_analysis as _attach

    _attach(session, run, scenes)


def _confirm_partition(session, chapter, paragraphs, scene_count: int, run):
    from app.services.scene_boundary_manual_review import (
        confirm_scene_revision_v1,
        create_or_get_scene_boundary_draft_v1,
        ensure_ai_model_revision_after_scenes_v1,
        save_scene_boundary_draft_v1,
    )

    ensure_ai_model_revision_after_scenes_v1(session, run)
    draft = create_or_get_scene_boundary_draft_v1(session, chapter.id)
    session.commit()
    session.refresh(draft)
    per = max(1, len(paragraphs) // scene_count)
    partition = []
    pidx = 0
    for order in range(1, scene_count + 1):
        start_p = paragraphs[pidx]
        end_idx = pidx + per - 1 if order < scene_count else len(paragraphs) - 1
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
    draft = save_scene_boundary_draft_v1(
        session, draft.id, partition, expected_etag=draft.revision_etag
    )
    session.commit()
    session.refresh(draft)
    revision, _already = confirm_scene_revision_v1(
        session, draft.id, expected_etag=draft.revision_etag
    )
    session.commit()
    return revision


def _seed_fixture_a(session, book):
    """Scene structural failure: 0/3, journey not started."""
    from app.db.models import AnalysisRunStage
    from app.services.scene_boundary_manual_review import revision_scenes

    chapter, paragraphs = _seed_chapter_base(
        session,
        book=book,
        chapter_index=1,
        title="第一章 场景分析失败",
        paragraph_count=18,
    )
    run = _new_run(session, chapter, status="succeeded", suffix="a-pre")
    scenes = _make_scenes(session, book, chapter, paragraphs, run, 3)
    # No scene analysis artifacts — first scene structural fail before any commit.
    revision = _confirm_partition(session, chapter, paragraphs, 3, run)
    rematerialized = revision_scenes(session, revision.id)

    run.status = "failed_structural"
    run.failed_stage = "scene_analysis"
    run.progress_current = 0
    run.progress_total = 3
    run.root_error_code = "STRUCTURAL_VALIDATION_FAILED"
    run.root_error_message = (
        "第一个场景分析时发生结构化校验失败（确定性 Fake Fixture）。阅读旅程尚未开始生成。"
    )
    run.retryable = False
    run.error_message = "场景分析失败"
    run.raw_output = json.dumps(
        {
            "kind": "scene_analysis_failure",
            "failed_scene_ordinal": 1,
            "error_code": "STRUCTURAL_VALIDATION_FAILED",
            "completed_scene_count": 0,
            "total_scene_count": 3,
        },
        ensure_ascii=False,
    )
    run.completed_at = _utc_now()
    session.add(
        AnalysisRunStage(
            run_id=run.id,
            stage_key="scene_analysis",
            stage_order=3,
            status="failed",
            error_code="STRUCTURAL_VALIDATION_FAILED",
            error_message=run.root_error_message,
            checkpoint_json=json.dumps(
                {
                    "completed_scene_count": 0,
                    "total_scene_count": 3,
                    "failed_scene_ordinal": 1,
                },
                ensure_ascii=False,
            ),
            completed_at=_utc_now(),
        )
    )
    session.commit()
    return {
        "book_id": book.id,
        "chapter_id": chapter.id,
        "run_id": run.id,
        "journey_run_id": None,
        "confirmed_revision_id": revision.id,
        "scene_count": len(rematerialized),
        "completed_scene_count": 0,
        "total_scene_count": 3,
        "root_error_code": run.root_error_code,
        "failed_stage": run.failed_stage,
    }


def _seed_fixture_b(session, book):
    """3/3 scenes complete; Journey synthesis deterministic failure."""
    from app.db.models import AnalysisRunStage, ReaderJourneyRun
    from app.services.chapter_analysis_completion import mark_scenes_complete_awaiting_journey
    from app.services.scene_boundary_manual_review import (
        bind_journey_to_revision,
        revision_scenes,
    )

    chapter, paragraphs = _seed_chapter_base(
        session,
        book=book,
        chapter_index=2,
        title="第二章 旅程整合失败",
        paragraph_count=18,
    )
    run = _new_run(session, chapter, status="succeeded", suffix="b-pre")
    scenes = _make_scenes(session, book, chapter, paragraphs, run, 3)
    _attach_scene_analysis(session, run, scenes)
    revision = _confirm_partition(session, chapter, paragraphs, 3, run)
    rematerialized = revision_scenes(session, revision.id)
    # Rematerialized scenes may be new IDs — attach artifacts for confirmed revision scenes.
    _attach_scene_analysis(session, run, rematerialized)
    mark_scenes_complete_awaiting_journey(session, run)
    session.add(
        AnalysisRunStage(
            run_id=run.id,
            stage_key="scene_analysis",
            stage_order=3,
            status="completed",
            checkpoint_json=json.dumps(
                {"completed_scene_count": 3, "total_scene_count": 3},
                ensure_ascii=False,
            ),
            completed_at=_utc_now(),
        )
    )
    session.commit()

    now = _utc_now()
    journey = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="failed",
        current_stage="reader_journey_chapter_synthesis",
        failed_stage="reader_journey_chapter_synthesis",
        provider_name="aliyun_qwen_plus",
        model_name="qwen-plus",
        scene_prompt_version="v2.0",
        chapter_prompt_version="v2.0",
        scene_contract_version="2.0",
        chapter_contract_version="2.0",
        formula_version="1.0",
        genre="suspense",
        planner_version="1.1",
        total_scene_count=3,
        completed_scene_count=3,
        remaining_scene_count=0,
        completed_scene_ids_json=json.dumps([s.id for s in rematerialized]),
        remaining_scene_ids_json="[]",
        cloud_consent=True,
        retryable=True,
        root_error_code="JOURNEY_SYNTHESIS_FAILED",
        root_error_message="阅读旅程整合失败（确定性 Fake Fixture）：一句话诊断不能为空。",
        client_request_id=f"chg015-synth-fail-{chapter.id}",
        failure_details_json=json.dumps(
            {
                "failed_stage": "reader_journey_chapter_synthesis",
                "error_code": "JOURNEY_SYNTHESIS_FAILED",
                "worker_claim": {
                    "claimed_at": (now - timedelta(minutes=10)).isoformat(),
                    "worker_id": "mg-chg015-synth",
                },
            },
            ensure_ascii=False,
        ),
        scene_revision_id=revision.id,
        scene_revision_no=revision.revision_number,
        included_scene_ids_json=json.dumps([s.id for s in rematerialized]),
        started_at=now - timedelta(minutes=12),
        updated_at=now,
        completed_at=now,
    )
    session.add(journey)
    session.flush()
    bind_journey_to_revision(session, journey, revision, rematerialized)
    journey.status = "failed"
    journey.completed_scene_count = 3
    journey.remaining_scene_count = 0
    journey.completed_scene_ids_json = json.dumps([s.id for s in rematerialized])
    journey.remaining_scene_ids_json = "[]"
    journey.root_error_code = "JOURNEY_SYNTHESIS_FAILED"
    journey.failed_stage = "reader_journey_chapter_synthesis"
    journey.current_stage = "reader_journey_chapter_synthesis"
    journey.retryable = True
    journey.completed_at = now
    for scene in rematerialized:
        from app.db.models import SceneReaderJourneyProfile

        session.add(
            SceneReaderJourneyProfile(
                reader_journey_run_id=journey.id,
                scene_id=scene.id,
                scene_ordinal=scene.ordinal,
                scene_value_summary=f"MG synthesis-fail profile S{scene.ordinal}",
                dominant_emotion="tension",
                engagement_score=55,
                confidence=0.8,
                validation_status="valid",
                payload_json="{}",
            )
        )
    session.commit()
    return {
        "book_id": book.id,
        "chapter_id": chapter.id,
        "run_id": run.id,
        "journey_run_id": journey.id,
        "confirmed_revision_id": revision.id,
        "completed_scene_count": 3,
        "total_scene_count": 3,
        "root_error_code": journey.root_error_code,
        "failed_stage": journey.failed_stage,
    }


def _seed_fixture_c(session, book):
    """Recoverable interrupt: claimed worker, lease expired, can_resume=true."""
    from app.db.models import AnalysisRunStage, ReaderJourneyRun
    from app.services.chapter_analysis_completion import mark_scenes_complete_awaiting_journey
    from app.services.reader_journey_recovery import JOURNEY_INTERRUPTED
    from app.services.scene_boundary_manual_review import (
        bind_journey_to_revision,
        revision_scenes,
    )

    chapter, paragraphs = _seed_chapter_base(
        session,
        book=book,
        chapter_index=3,
        title="第三章 可恢复中断",
        paragraph_count=18,
    )
    run = _new_run(session, chapter, status="succeeded", suffix="c-pre")
    scenes = _make_scenes(session, book, chapter, paragraphs, run, 3)
    _attach_scene_analysis(session, run, scenes)
    revision = _confirm_partition(session, chapter, paragraphs, 3, run)
    rematerialized = revision_scenes(session, revision.id)
    _attach_scene_analysis(session, run, rematerialized)
    mark_scenes_complete_awaiting_journey(session, run)
    session.add(
        AnalysisRunStage(
            run_id=run.id,
            stage_key="scene_analysis",
            stage_order=3,
            status="completed",
            checkpoint_json=json.dumps(
                {"completed_scene_count": 3, "total_scene_count": 3},
                ensure_ascii=False,
            ),
            completed_at=_utc_now(),
        )
    )
    session.commit()

    now = _utc_now()
    lease_expired = now - timedelta(minutes=30)
    completed = rematerialized[:1]
    remaining = rematerialized[1:]
    journey = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=book.id,
        chapter_id=chapter.id,
        status="scene_profiles_partial",
        current_stage="reader_journey_scene_profiles",
        failed_stage="reader_journey_scene_profiles",
        provider_name="aliyun_qwen_plus",
        model_name="qwen-plus",
        scene_prompt_version="v2.0",
        chapter_prompt_version="v2.0",
        scene_contract_version="2.0",
        chapter_contract_version="2.0",
        formula_version="1.0",
        genre="suspense",
        planner_version="1.1",
        total_scene_count=3,
        completed_scene_count=1,
        remaining_scene_count=2,
        completed_scene_ids_json=json.dumps([s.id for s in completed]),
        remaining_scene_ids_json=json.dumps([s.id for s in remaining]),
        cloud_consent=True,
        retryable=True,
        root_error_code=JOURNEY_INTERRUPTED,
        root_error_message="应用重启或后台任务中断，阅读旅程未完成；可从已完成检查点恢复",
        client_request_id=f"chg015-recoverable-{chapter.id}",
        failure_details_json=json.dumps(
            {
                "interrupt": {
                    "code": JOURNEY_INTERRUPTED,
                    "previous_status": "scene_profiles_running",
                    "recovered_at": now.isoformat(),
                    "auto_enqueued": False,
                    "had_worker_claim": True,
                },
                "worker_claim": {
                    "claimed_at": (lease_expired - timedelta(minutes=5)).isoformat(),
                    "worker_id": "mg-chg015-worker",
                    "lease_expires_at": lease_expired.isoformat(),
                },
                "startup_intent": {"claimed": True},
            },
            ensure_ascii=False,
        ),
        scene_revision_id=revision.id,
        scene_revision_no=revision.revision_number,
        included_scene_ids_json=json.dumps([s.id for s in rematerialized]),
        started_at=lease_expired - timedelta(minutes=10),
        updated_at=lease_expired,
        completed_at=now,
    )
    session.add(journey)
    session.flush()
    bind_journey_to_revision(session, journey, revision, rematerialized)
    # Restore progress wiped by rebind when binding a fresh journey row.
    journey.status = "scene_profiles_partial"
    journey.completed_scene_count = 1
    journey.remaining_scene_count = 2
    journey.completed_scene_ids_json = json.dumps([s.id for s in completed])
    journey.remaining_scene_ids_json = json.dumps([s.id for s in remaining])
    journey.root_error_code = JOURNEY_INTERRUPTED
    journey.retryable = True
    journey.completed_at = now
    journey.updated_at = lease_expired
    from app.db.models import SceneReaderJourneyProfile

    session.add(
        SceneReaderJourneyProfile(
            reader_journey_run_id=journey.id,
            scene_id=completed[0].id,
            scene_ordinal=completed[0].ordinal,
            scene_value_summary="MG recoverable checkpoint S1",
            dominant_emotion="tension",
            engagement_score=60,
            confidence=0.85,
            validation_status="valid",
            payload_json="{}",
        )
    )
    session.commit()
    return {
        "book_id": book.id,
        "chapter_id": chapter.id,
        "run_id": run.id,
        "journey_run_id": journey.id,
        "confirmed_revision_id": revision.id,
        "completed_scene_count": 1,
        "total_scene_count": 3,
        "root_error_code": journey.root_error_code,
        "can_resume": True,
    }


def _seed_awaiting_2_to_3(session, book, *, chapter_index: int, title: str, suffix: str):
    """AI 2 scenes → draft saved as 3, awaiting confirm (wait-gate path)."""
    from app.services.chapter_analysis_completion import (
        mark_scenes_complete_awaiting_boundary_confirmation,
    )
    from app.services.scene_boundary_manual_review import (
        create_or_get_scene_boundary_draft_v1,
        ensure_ai_model_revision_after_scenes_v1,
        save_scene_boundary_draft_v1,
    )

    chapter, paragraphs = _seed_chapter_base(
        session,
        book=book,
        chapter_index=chapter_index,
        title=title,
        paragraph_count=18,
    )
    run = _new_run(session, chapter, status="succeeded", suffix=suffix)
    scenes = _make_scenes(session, book, chapter, paragraphs, run, 2)
    _attach_scene_analysis(session, run, scenes)
    model_rev = ensure_ai_model_revision_after_scenes_v1(session, run)
    mark_scenes_complete_awaiting_boundary_confirmation(session, run)
    session.commit()

    draft = create_or_get_scene_boundary_draft_v1(session, chapter.id)
    session.commit()
    session.refresh(draft)
    # User adjusts 2 → 3 scenes (new middle scene will have no inheritable artifact).
    spans = [
        (0, 5),
        (6, 11),
        (12, len(paragraphs) - 1),
    ]
    partition = []
    for order, (start_i, end_i) in enumerate(spans, start=1):
        partition.append(
            {
                "scene_order": order,
                "start_paragraph_id": paragraphs[start_i].id,
                "end_paragraph_id": paragraphs[end_i].id,
                "included_in_journey": True,
            }
        )
    draft = save_scene_boundary_draft_v1(
        session, draft.id, partition, expected_etag=draft.revision_etag
    )
    session.commit()
    return {
        "book_id": book.id,
        "chapter_id": chapter.id,
        "run_id": run.id,
        "journey_run_id": None,
        "model_revision_id": model_rev.id,
        "draft_revision_id": draft.id,
        "draft_etag": draft.revision_etag,
        "ai_scene_count": 2,
        "draft_scene_count": 3,
        "status": "awaiting_confirm_2_to_3",
    }


def _seed_fixture_d(session, book):
    """Manual SUCCESS fixture — leave awaiting confirm for user click."""
    return _seed_awaiting_2_to_3(
        session,
        book,
        chapter_index=4,
        title="第四章 等待门禁成功主链路",
        suffix="d-manual",
    )


def _seed_fixture_d_auto(session, book):
    """Auto wait-gate probe twin — same shape as D, consumed by HTTP probe only."""
    return _seed_awaiting_2_to_3(
        session,
        book,
        chapter_index=5,
        title="第五章 等待门禁自动探针",
        suffix="d-auto",
    )


def seed_all(*, data_dir: Path, db_path: Path) -> dict:
    _assert_isolated_db(db_path)
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        side = Path(str(db_path) + suffix)
        if side.exists():
            side.unlink()
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

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.session import create_db

    create_db()
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    fe = f"http://127.0.0.1:{FE_PORT}"
    manifest: dict = {
        "change_id": "CHG-20260730-015",
        "database": str(db_path),
        "api": f"http://127.0.0.1:{API_PORT}",
        "frontend": fe,
        "fake_provider": "ON",
        "real_provider": "OFF",
        "real_provider_calls": 0,
        "formal_db_writes": 0,
        "fixtures": {},
        "urls": {},
    }

    with Session() as session:
        _enable_cloud(session)
        book = _seed_book(session)

        fx_a = _seed_fixture_a(session, book)
        fx_b = _seed_fixture_b(session, book)
        fx_c = _seed_fixture_c(session, book)
        fx_d = _seed_fixture_d(session, book)
        fx_d_auto = _seed_fixture_d_auto(session, book)

        manifest["fixtures"]["A_scene_failure"] = fx_a
        manifest["fixtures"]["B_synthesis_failure"] = fx_b
        manifest["fixtures"]["C_recoverable"] = fx_c
        manifest["fixtures"]["D_success_wait_gate"] = fx_d
        manifest["fixtures"]["D_auto_wait_gate"] = fx_d_auto

        manifest["urls"] = {
            "SCENE_FAILURE": (
                f"{fe}/books/{book.id}?chapter={fx_a['chapter_id']}"
                f"&analysisRun={fx_a['run_id']}&view=progress"
            ),
            "SYNTHESIS_FAILURE": (
                f"{fe}/books/{book.id}?chapter={fx_b['chapter_id']}"
                f"&analysisRun={fx_b['run_id']}&journeyRun={fx_b['journey_run_id']}"
                f"&view=progress"
            ),
            "RECOVERABLE_INTERRUPTED": (
                f"{fe}/books/{book.id}?chapter={fx_c['chapter_id']}"
                f"&analysisRun={fx_c['run_id']}&journeyRun={fx_c['journey_run_id']}"
                f"&view=progress"
            ),
            "SUCCESS": (
                f"{fe}/books/{book.id}?chapter={fx_d['chapter_id']}"
                f"&analysisRun={fx_d['run_id']}&view=scene-boundary-review"
            ),
        }

    out = EVIDENCE / "FIXTURE_MANIFEST.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    seed_all(data_dir=args.data_dir, db_path=args.db_path)


if __name__ == "__main__":
    main()
