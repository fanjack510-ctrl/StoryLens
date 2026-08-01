"""TEST-ONLY seed for CHG-029/030 integration manual smoke (v2).

Creates a fresh isolated SQLite with separate books for scene/journey/whole-book
acceptance entries. Not packaged; not a product Fake Provider registration.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent
REPO_ROOT = API_ROOT.parents[1]
sys.path.insert(0, str(API_ROOT))

SMOKE_DIR = Path(
    os.environ.get(
        "STORYLENS_CHG029_SMOKE_ROOT",
        Path(os.environ["TEMP"]) / "storylens-chg029-smoke-v2",
    )
)
SMOKE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = SMOKE_DIR / "chg029_smoke_v2.db"
if DB_PATH.exists():
    DB_PATH.unlink()
for suffix in ("-wal", "-shm"):
    side = Path(str(DB_PATH) + suffix)
    if side.exists():
        side.unlink()

os.environ["STORYLENS_DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED"] = "true"
os.environ["STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED"] = "true"
os.environ["STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED"] = "false"
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
    ChapterReaderJourneySummary,
    Paragraph,
    ReaderJourneyPhase,
    ReaderJourneyRun,
    Scene,
    SceneReaderJourneyProfile,
)
from app.db.session import create_db, get_session_factory  # noqa: E402
from app.narrative_core.services.whole_book_fixture_pipeline_v1_service import (  # noqa: E402
    execute_fixture_minimal_pipeline_v1,
)
from app.schemas.settings import CloudBudgetUpdate  # noqa: E402
from app.services.chapter_analysis_completion import (  # noqa: E402
    mark_scenes_complete_awaiting_boundary_confirmation,
)
from app.services.reader_journey_recovery import JOURNEY_INTERRUPTED  # noqa: E402
from app.services.scene_boundary_manual_review import (  # noqa: E402
    confirm_scene_revision_and_start_journey_v1,
    create_or_get_scene_boundary_draft_v1,
    save_scene_boundary_draft_v1,
)
from app.narrative_core.services.fixture_window_analysis_sample_s import (  # noqa: E402
    SAMPLE_S_PARAGRAPH_TEXTS,
)
from app.narrative_core.services.whole_book_snapshot_v1_service import (  # noqa: E402
    create_or_reuse_book_snapshot_v1,
)
from app.services.whole_book_source_fingerprint import sha256_utf8  # noqa: E402
from tests.whole_book_minimal_test_helpers import prepare_sample_s_run  # noqa: E402

PROVIDER = "aliyun_qwen_plus"
MODEL = "qwen-plus"
API_URL = os.environ.get("STORYLENS_CHG029_API_URL", "http://127.0.0.1:8003")
FE_URL = os.environ.get("STORYLENS_CHG029_FE_URL", "http://127.0.0.1:1423")


def _enable_cloud(session) -> None:
    session.merge(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True)))
    payload = CloudBudgetUpdate().model_dump()
    payload.update(
        {
            "daily_request_limit": 500,
            "daily_token_limit": 2_000_000,
            "daily_cost_limit": 50.0,
            "cloud_daily_request_limit": 500,
            "cloud_daily_token_limit": 2_000_000,
            "cloud_daily_estimated_cost_limit": 50.0,
        }
    )
    session.merge(ApplicationSetting(key="cloud_budget_settings", value_json=json.dumps(payload)))
    session.commit()


def _seed_book(
    session,
    *,
    title: str,
    source_hash: str,
    book_code: str,
    input_hash: str,
    paragraph_count: int,
    scene_count: int,
    run_status: str = "succeeded",
):
    book = Book(
        title=title,
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
    paragraphs: list[Paragraph] = []
    for index in range(1, paragraph_count + 1):
        body = f"第{index}段：雨打青瓦，巷口灯影摇晃，案情线索逐渐浮现。"
        row = Paragraph(
            id=f"{book_code}-C0001-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=body,
            normalized_text=body,
            char_start=index * 10,
            char_end=index * 10 + len(body),
        )
        session.add(row)
        paragraphs.append(row)
    session.flush()
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider=PROVIDER,
        model=MODEL,
        prompt_version="v3.5",
        schema_version="v1",
        input_hash=input_hash,
        status=run_status,
        execution_mode="local",
        cloud_consent=True,
        cloud_consent_at=datetime.now(timezone.utc),
        sends_content_to_cloud=False,
        status_version=1,
        book_id=book.id,
        start_chapter_id=chapter.id,
        end_chapter_id=chapter.id,
        progress_current=0 if run_status == "running" else scene_count,
        progress_total=scene_count,
        started_at=datetime.now(timezone.utc) if run_status == "running" else None,
        analysis_mode="assisted_boundary_review",
    )
    session.add(run)
    session.flush()
    per_scene = max(1, paragraph_count // scene_count)
    scenes: list[Scene] = []
    start_idx = 0
    for ordinal in range(1, scene_count + 1):
        end_idx = start_idx + per_scene - 1 if ordinal < scene_count else paragraph_count - 1
        start_p = paragraphs[start_idx]
        end_p = paragraphs[end_idx]
        content = "\n".join(p.normalized_text for p in paragraphs[start_idx : end_idx + 1])
        scene = Scene(
            scene_key=f"{book_code}-C0001-S{ordinal:04d}",
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
    return book, chapter, paragraphs, run, scenes


def _attach_scene_analysis(session, run: AnalysisRun, scenes: list[Scene]) -> None:
    for scene in scenes:
        artifact = AnalysisArtifact(
            run_id=run.id,
            artifact_type="scene_analysis",
            subject_type="scene",
            subject_id=str(scene.id),
            schema_version="v1",
            prompt_version="v1",
            payload_json='{"scene_id": "x", "goal": {"summary": "seed", "evidence_paragraph_ids": []}}',
            confidence=0.9,
            validation_status="valid",
        )
        session.add(artifact)
        session.flush()
        session.add(
            AnalysisEvidence(
                artifact_id=artifact.id,
                field_path="summary",
                paragraph_id=scene.start_paragraph_id,
                paragraph_hash="c" * 64,
            )
        )
    session.flush()


def _shrink_draft(session, draft, paragraphs, scene_count: int):
    span = max(1, len(paragraphs) // scene_count)
    partition = []
    for i in range(scene_count):
        start = paragraphs[i * span]
        end = paragraphs[min((i + 1) * span - 1, len(paragraphs) - 1)]
        partition.append(
            {
                "scene_order": i + 1,
                "start_paragraph_id": start.id,
                "end_paragraph_id": end.id,
                "included_in_journey": True,
            }
        )
    return save_scene_boundary_draft_v1(
        session, draft.id, partition, expected_etag=draft.revision_etag
    )


def _url(book_id: int, chapter_id: int, run_id: int | None = None, **extra) -> str:
    q = [f"chapter={chapter_id}"]
    if run_id is not None:
        q.append(f"analysisRun={run_id}")
    for k, v in extra.items():
        if v is None:
            continue
        q.append(f"{k}={v}")
    return f"{FE_URL}/books/{book_id}?{'&'.join(q)}"


def _entry(kind: str, book, chapter, run=None, journey=None, revision=None, **extra) -> dict:
    return {
        "kind": kind,
        "book_title": book.title,
        "book_id": book.id,
        "chapter_id": chapter.id,
        "analysis_run_id": run.id if run else None,
        "journey_run_id": journey.id if journey else None,
        "revision_id": revision.id if revision else None,
        "url": _url(
            book.id,
            chapter.id,
            run.id if run else None,
            journeyRun=journey.id if journey else None,
            **{k: v for k, v in extra.items() if k.startswith("view") or k.startswith("tab")},
        ),
        **{k: v for k, v in extra.items() if not (k.startswith("view") or k.startswith("tab"))},
    }


async def _seed_split_and_boundary(session) -> tuple[dict, dict]:
    """A custom split + B boundary review share draft/confirm patterns on separate books."""
    # A: awaiting confirm with editable draft (custom split entry)
    book_a, chapter_a, paragraphs_a, run_a, scenes_a = _seed_book(
        session,
        title="CHG029 A Custom Scene Split",
        source_hash="a1" * 32,
        book_code="B029A",
        input_hash="a1" * 32,
        paragraph_count=12,
        scene_count=3,
    )
    _attach_scene_analysis(session, run_a, scenes_a)
    mark_scenes_complete_awaiting_boundary_confirmation(session, run_a)
    draft_a = create_or_get_scene_boundary_draft_v1(session, chapter_a.id)
    session.commit()
    session.refresh(draft_a)
    draft_a = _shrink_draft(session, draft_a, paragraphs_a, scene_count=3)
    session.commit()
    session.refresh(draft_a)
    entry_a = _entry(
        "custom_scene_split",
        book_a,
        chapter_a,
        run_a,
        revision=draft_a,
        expected_initial="awaiting_scene_boundary_confirmation; draft editable; split/save creates revision",
        draft_revision_id=draft_a.id,
        run_status=run_a.status,
    )

    # B: boundary review session + draft ready for confirm (idempotent confirm)
    book_b, chapter_b, paragraphs_b, run_b, scenes_b = _seed_book(
        session,
        title="CHG029 B Scene Boundary Review",
        source_hash="b1" * 32,
        book_code="B029B",
        input_hash="b1" * 32,
        paragraph_count=12,
        scene_count=3,
    )
    _attach_scene_analysis(session, run_b, scenes_b)
    mark_scenes_complete_awaiting_boundary_confirmation(session, run_b)
    review = BoundaryReviewSession(
        book_id=book_b.id,
        chapter_id=chapter_b.id,
        analysis_run_id=run_b.id,
        prompt_version="v3.5",
        provider=PROVIDER,
        model=MODEL,
        status="awaiting_confirmation",
        candidate_count=2,
        accepted_count=0,
        rejected_count=0,
        manually_added_count=0,
    )
    session.add(review)
    session.flush()
    draft_b = create_or_get_scene_boundary_draft_v1(session, chapter_b.id)
    session.commit()
    session.refresh(draft_b)
    draft_b = _shrink_draft(session, draft_b, paragraphs_b, scene_count=3)
    session.commit()
    session.refresh(draft_b)
    entry_b = _entry(
        "scene_boundary",
        book_b,
        chapter_b,
        run_b,
        revision=draft_b,
        expected_initial="boundary review session present; draft confirm uses current revision; repeat confirm no new revision",
        boundary_review_session_id=review.id,
        draft_revision_id=draft_b.id,
        run_status=run_b.status,
    )
    return entry_a, entry_b


def _seed_scene_cancel(session) -> dict:
    book, chapter, paragraphs, run, scenes = _seed_book(
        session,
        title="CHG029 C Scene Task Cancel",
        source_hash="c1" * 32,
        book_code="B029C",
        input_hash="c1" * 32,
        paragraph_count=8,
        scene_count=2,
        run_status="running",
    )
    _attach_scene_analysis(session, run, scenes[:1])
    session.commit()
    return _entry(
        "scene_cancel",
        book,
        chapter,
        run,
        expected_initial="analysis_run.status=running; cancel/stop visible; cancel → cancelled; no auto-resume; no new analysis run",
        run_status=run.status,
        view="progress",
    )


def _seed_interrupted(
    session,
    *,
    title: str,
    source_hash: str,
    book_code: str,
    input_hash: str,
    client_request_id: str,
):
    book, chapter, paragraphs, run, scenes = _seed_book(
        session,
        title=title,
        source_hash=source_hash,
        book_code=book_code,
        input_hash=input_hash,
        paragraph_count=8,
        scene_count=4,
    )
    _attach_scene_analysis(session, run, scenes)
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
        manually_added_count=3,
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
                {"after_paragraph_id": paragraphs[i * 2 - 1].id, "source": "user_added"}
                for i in range(1, 4)
            ],
            ensure_ascii=False,
        ),
        confirmed_by="tester",
        confirmed_at=datetime.now(timezone.utc),
        coverage_rate=1.0,
    )
    session.add(revision)
    session.flush()
    for scene in scenes:
        scene.boundary_revision_id = revision.id
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
        scene_revision_id=revision.id,
        scene_revision_no=revision.revision_number,
        retryable=True,
        root_error_code=JOURNEY_INTERRUPTED,
        root_error_message="fixture recoverable interrupt",
        completed_scene_count=0,
        total_scene_count=len(scenes),
        remaining_scene_count=len(scenes),
        completed_scene_ids_json="[]",
        remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
        failure_details_json=json.dumps(
            {"scene_contract_version": "2.0", "source_mode": "v2_native"},
            ensure_ascii=False,
        ),
        started_at=datetime.now(timezone.utc),
    )
    session.add(journey)
    session.flush()
    return book, chapter, run, revision, journey


async def _seed_succeeded_with_result(
    session,
    *,
    title: str,
    source_hash: str,
    book_code: str,
    input_hash: str,
    kind: str,
    expected_initial: str,
    attach_interrupt_noise: bool = False,
) -> dict:
    book, chapter, paragraphs, run, scenes = _seed_book(
        session,
        title=title,
        source_hash=source_hash,
        book_code=book_code,
        input_hash=input_hash,
        paragraph_count=12,
        scene_count=3,
    )
    _attach_scene_analysis(session, run, scenes)
    draft = create_or_get_scene_boundary_draft_v1(session, chapter.id)
    session.commit()
    session.refresh(draft)
    draft = _shrink_draft(session, draft, paragraphs, scene_count=3)
    session.commit()
    session.refresh(draft)
    revision, journey, _, _ = await confirm_scene_revision_and_start_journey_v1(
        session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    session.commit()
    assert journey is not None
    if journey.root_error_code == "WAITING_SCENE_ANALYSIS":
        journey.root_error_code = None
        journey.root_error_message = None
    from app.services.scene_boundary_manual_review import revision_scenes

    rev_scenes = revision_scenes(session, revision.id)
    included_ids = [int(s.id) for s in rev_scenes]
    journey.status = "succeeded"
    journey.current_stage = "succeeded"
    journey.result_status = "current"
    journey.completed_scene_count = len(rev_scenes)
    journey.total_scene_count = len(rev_scenes)
    journey.remaining_scene_count = 0
    journey.included_scene_ids_json = json.dumps(included_ids)
    journey.completed_scene_ids_json = json.dumps(included_ids)
    journey.completed_at = datetime.now(timezone.utc)
    session.flush()
    for ordinal, scene in enumerate(rev_scenes, start=1):
        session.add(
            SceneReaderJourneyProfile(
                reader_journey_run_id=journey.id,
                scene_id=scene.id,
                scene_ordinal=ordinal,
                scene_value_summary=f"CTA scene {ordinal}",
                dominant_emotion="好奇",
                curiosity_score=70,
                tension_score=55,
                payoff_score=60,
                hook_score=65,
                information_gain_score=50,
                emotional_resonance_score=48,
                cognitive_load_score=40,
                dropoff_risk_score=30,
                engagement_score=68,
                confidence=0.9,
                payload_json="{}",
                validation_status="valid",
            )
        )
    session.add(
        ReaderJourneyPhase(
            reader_journey_run_id=journey.id,
            ordinal=1,
            title="开篇牵引",
            start_scene_ordinal=1,
            end_scene_ordinal=max(1, len(rev_scenes)),
            primary_reader_question="接下来会发生什么",
            dominant_emotion="好奇",
            reading_payoff="建立期待",
            continuation_motivation="继续阅读",
            summary="CTA phase",
            confidence=0.9,
            payload_json="{}",
        )
    )
    session.add(
        ChapterReaderJourneySummary(
            reader_journey_run_id=journey.id,
            chapter_value_summary="阅读旅程已生成",
            chapter_reader_question_chain_json='["接下来会发生什么"]',
            overall_engagement_score=70,
            one_sentence_diagnosis="用于 Journey Result / CTA 验收。",
            pacing_diagnosis_json='["节奏正常"]',
            deterministic_statistics_json="{}",
            payload_json="{}",
            validation_status="valid",
        )
    )
    if attach_interrupt_noise:
        journey.failure_details_json = json.dumps(
            {
                "historical_noise": True,
                "prior_root_error_code": JOURNEY_INTERRUPTED,
                "note": "stale interrupted noise must not override succeeded result",
            },
            ensure_ascii=False,
        )
        journey.root_error_code = None
        journey.root_error_message = None
    session.commit()
    session.refresh(journey)
    return _entry(
        kind,
        book,
        chapter,
        run,
        journey,
        revision,
        expected_initial=expected_initial,
        view="result",
        tab="reader-journey",
        run_status=run.status,
        journey_status=journey.status,
    )


async def _amain() -> dict:
    assert "storylens-chg029-smoke-v2" in get_settings().database_url.replace("\\", "/")
    create_db()
    SessionLocal = get_session_factory()
    fixtures: dict = {
        "change_id": "CHG-20260801-030",
        "parent_change": "CHG-20260731-029",
        "database": str(DB_PATH),
        "smoke_root": str(SMOKE_DIR),
        "api_url": API_URL,
        "frontend_url": FE_URL,
        "note": "test-only fixtures; result_origin=fixture for whole-book; not real model output",
    }
    with SessionLocal() as session:
        _enable_cloud(session)
        entry_a, entry_b = await _seed_split_and_boundary(session)
        entry_c = _seed_scene_cancel(session)
        book_d, chapter_d, run_d, rev_d, journey_d = _seed_interrupted(
            session,
            title="CHG029 D Journey Resume Success",
            source_hash="d1" * 32,
            book_code="B029D",
            input_hash="d1" * 32,
            client_request_id="chg029-resume-success",
        )
        book_e, chapter_e, run_e, rev_e, journey_e = _seed_interrupted(
            session,
            title="CHG029 E Journey Resume Failure",
            source_hash="e1" * 32,
            book_code="B029E",
            input_hash="e1" * 32,
            client_request_id="chg029-resume-failure",
        )
        session.commit()
        entry_d = _entry(
            "journey_resume_success",
            book_d,
            chapter_d,
            run_d,
            journey_d,
            rev_d,
            expected_initial="interrupted; can_resume=true; checkpoint; no result yet",
            journey_status=journey_d.status,
            can_resume=True,
        )
        entry_e = _entry(
            "journey_resume_failure",
            book_e,
            chapter_e,
            run_e,
            journey_e,
            rev_e,
            expected_initial="interrupted; can_resume=true; launcher fails this journey_run_id only",
            journey_status=journey_e.status,
            can_resume=True,
        )
        entry_f = await _seed_succeeded_with_result(
            session,
            title="CHG029 F Stale Interrupted Noise",
            source_hash="f1" * 32,
            book_code="B029F",
            input_hash="f1" * 32,
            kind="stale_success",
            expected_initial="succeeded + result exists; historical JOURNEY_INTERRUPTED noise ignored; show Result directly",
            attach_interrupt_noise=True,
        )
        entry_g = await _seed_succeeded_with_result(
            session,
            title="CHG029 G Journey CTA",
            source_hash="g1" * 32,
            book_code="B029G",
            input_hash="g1" * 32,
            kind="journey_cta",
            expected_initial="succeeded + result; right-rail 查看阅读旅程 + top 阅读旅程 → same analysisRun/journeyRun",
        )

        # Whole-book completed Sample S
        run_id, book_id = prepare_sample_s_run(session)
        execute_fixture_minimal_pipeline_v1(session, run_id)
        session.commit()
        book_wb = session.get(Book, book_id)
        assert book_wb is not None
        book_wb.title = "Sample S"
        session.commit()
        entry_wb = {
            "kind": "whole_book_completed",
            "book_title": "Sample S",
            "book_id": book_id,
            "chapter_id": None,
            "whole_book_run_id": run_id,
            "status": "completed",
            "result_origin": "fixture",
            "url": f"{FE_URL}/books/{book_id}/whole-book",
            "expected_initial": "completed fixture; overview 9 claims; characters/events; evidence deep link; banner=测试数据",
        }

        # Whole-book not started (cost/consent) — unique hash (Sample S hash already used)
        book_ns = Book(
            title="CHG029 Cost Consent Not Started",
            source_file_name="chg029-cost-consent.txt",
            source_file_hash=sha256_utf8("chg029-cost-consent-not-started"),
        )
        session.add(book_ns)
        session.flush()
        chapters_ns: list[Chapter] = []
        for idx in range(3):
            ch = Chapter(book_id=book_ns.id, chapter_index=idx, title=f"第{idx + 1}章")
            session.add(ch)
            session.flush()
            chapters_ns.append(ch)
        global_idx = 0
        for ch_idx, ch in enumerate(chapters_ns):
            for para_idx, text in enumerate(SAMPLE_S_PARAGRAPH_TEXTS[ch_idx * 3 : ch_idx * 3 + 3]):
                session.add(
                    Paragraph(
                        id=f"p-ns-{book_ns.id}-{global_idx}",
                        book_id=book_ns.id,
                        chapter_id=ch.id,
                        paragraph_index=para_idx,
                        raw_text=text,
                        normalized_text=text,
                        char_start=0,
                        char_end=len(text),
                        content_hash=sha256_utf8(text),
                    )
                )
                global_idx += 1
        session.flush()
        create_or_reuse_book_snapshot_v1(session, book_ns.id)
        session.commit()
        entry_cost = {
            "kind": "cost_consent",
            "book_title": book_ns.title,
            "book_id": book_ns.id,
            "chapter_id": None,
            "whole_book_run_id": None,
            "url": f"{FE_URL}/books/{book_ns.id}/whole-book",
            "expected_initial": "prepare 200; estimate+consent UI; real_provider=false disables formal start; fixture preview clickable",
        }

        fixtures.update(
            {
                "custom_scene_split": entry_a,
                "scene_boundary": entry_b,
                "scene_cancel": entry_c,
                "journey_resume_success": entry_d,
                "journey_resume_failure": entry_e,
                "stale_success": entry_f,
                "journey_cta": entry_g,
                "whole_book": entry_wb,
                "cost_consent": entry_cost,
                "fail_journey_run_id": journey_e.id,
            }
        )

    out = SMOKE_DIR / "MANUAL_FIXTURES.json"
    out.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "database": str(DB_PATH), "fixtures": str(out)}, ensure_ascii=False))
    return fixtures


if __name__ == "__main__":
    asyncio.run(_amain())
