#!/usr/bin/env python3
"""Append Live Hook Rich fixture (Chapter 6) to CHG-011 MG DB.

Persists structured facts equivalent to chg005FixtureBReliableHooks via normal
Reader Journey profile / summary / phase rows. No Provider calls. Does not
wipe Fixture A–E.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
DEFAULT_DB = (
    Path(os.environ.get("TEMP", "/tmp"))
    / "storylens-mg-chg011-workflow-consistency"
    / "database"
    / "storylens-mg-chg011.db"
)
FORMAL_DB = Path.home() / "AppData" / "Local" / "StoryLens" / "database" / "storylens.db"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _assert_isolated(db_path: Path) -> None:
    resolved = db_path.resolve()
    if resolved == FORMAL_DB.resolve():
        raise SystemExit(f"Refusing formal AppData DB: {resolved}")
    local = Path.home() / "AppData" / "Local" / "StoryLens"
    try:
        resolved.relative_to(local.resolve())
        raise SystemExit(f"Refusing write under formal StoryLens tree: {resolved}")
    except ValueError:
        pass


def _base_profile(
    *,
    scene_id: int,
    ordinal: int,
    summary: str,
    evidence: list[str],
    hook_score: int = 40,
    payoff_score: int = 30,
    **extra,
) -> dict:
    payload = {
        "scene_id": scene_id,
        "scene_ordinal": ordinal,
        "scene_value_summary": summary,
        "reader_question_in": [],
        "reader_question_created": [],
        "reader_question_answered": [],
        "reader_question_out": [],
        "dominant_emotion": "tension",
        "emotional_valence_start": -10,
        "emotional_valence_end": 10,
        "arousal_start": 40,
        "arousal_end": 55,
        "curiosity_score": 55,
        "tension_score": 50,
        "payoff_score": payoff_score,
        "hook_score": hook_score,
        "information_gain_score": 45,
        "emotional_resonance_score": 40,
        "cognitive_load_score": 35,
        "dropoff_risk_score": 30,
        "payoffs": [],
        "hooks": [],
        "techniques": [],
        "risk_points": [],
        "emotion_beats": [],
        "information_changes": [],
        "character_effects": [],
        "writing_takeaways": [],
        "confidence": 0.85,
        "evidence_paragraph_ids": evidence[:2],
    }
    payload.update(extra)
    return payload


def main() -> int:
    db_path = Path(os.environ.get("MG_DB_PATH", str(DEFAULT_DB)))
    _assert_isolated(db_path)
    if not db_path.exists():
        raise SystemExit(f"MG DB missing; seed A–E first: {db_path}")

    db_url = f"sqlite:///{db_path.as_posix()}"
    os.environ["STORYLENS_DATABASE_URL"] = db_url
    os.environ.setdefault("STORYLENS_APP_ENV", "development")
    os.environ["STORYLENS_REAL_PROVIDER_ENABLED"] = "0"
    sys.path.insert(0, str(REPO / "apps" / "api"))

    from sqlalchemy import create_engine, select, func
    from sqlalchemy.orm import sessionmaker

    from app.db.models import (
        AnalysisRun,
        Book,
        BoundaryRevision,
        BoundaryReviewSession,
        Chapter,
        ChapterReaderJourneySummary,
        Paragraph,
        ReaderJourneyPhase,
        ReaderJourneyRun,
        Scene,
        SceneReaderJourneyProfile,
    )
    from app.schemas.reader_journey import SceneReaderJourneyProfileItem
    from app.services.reader_journey_visualization import build_reader_journey_visualization
    from app.services.scene_boundary_manual_review import (
        confirm_scene_revision_v1,
        create_or_get_scene_boundary_draft_v1,
        ensure_ai_model_revision_after_scenes_v1,
        save_scene_boundary_draft_v1,
    )
    from app.services.chapter_analysis_completion import (
        mark_scenes_complete_awaiting_boundary_confirmation,
    )
    from tests.test_chg041_scene_boundary_manual_review import _attach_scene_analysis

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session() as session:
        book = session.get(Book, 1)
        if book is None:
            raise SystemExit("Book 1 missing — run seed_mg_chg011_fixtures.py first")

        existing = session.scalar(
            select(Chapter).where(Chapter.book_id == book.id, Chapter.chapter_index == 6)
        )
        if existing is not None:
            # Prefer reuse when already seeded with succeeded hook-rich journey.
            prior_journey = session.scalar(
                select(ReaderJourneyRun)
                .where(
                    ReaderJourneyRun.chapter_id == existing.id,
                    ReaderJourneyRun.status == "succeeded",
                )
                .order_by(ReaderJourneyRun.id.desc())
            )
            if prior_journey is not None:
                prior_summary = session.scalar(
                    select(ChapterReaderJourneySummary).where(
                        ChapterReaderJourneySummary.reader_journey_run_id == prior_journey.id
                    )
                )
                payload = {}
                if prior_summary is not None:
                    try:
                        payload = json.loads(prior_summary.payload_json or "{}")
                    except json.JSONDecodeError:
                        payload = {}
                if payload.get("fixture_source") == "chg005FixtureBReliableHooks":
                    viz = build_reader_journey_visualization(session, prior_journey)
                    loops = (viz or {}).get("narrative_loops") or []
                    fixture = {
                        "book_id": book.id,
                        "chapter_id": existing.id,
                        "run_id": prior_journey.analysis_run_id,
                        "journey_run_id": prior_journey.id,
                        "confirmed_revision_id": prior_journey.scene_revision_id,
                        "scene_count": prior_journey.total_scene_count,
                        "narrative_loop_count": len(loops),
                        "questions": [str(l.get("question") or "") for l in loops],
                        "fixture_source": "chg005FixtureBReliableHooks",
                        "url": (
                            f"http://127.0.0.1:1426/books/{book.id}"
                            f"?chapter={existing.id}&analysisRun={prior_journey.analysis_run_id}"
                            f"&journeyRun={prior_journey.id}&view=result&tab=reader-journey&lens=hook_payoff"
                        ),
                    }
                    manifest_path = EVIDENCE / "FIXTURE_MANIFEST.json"
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["fixtures"]["D_hook_rich"] = fixture
                    manifest["urls"]["HOOK_RICH"] = fixture["url"]
                    manifest_path.write_text(
                        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    print(json.dumps(fixture, ensure_ascii=False, indent=2))
                    print("REAL_PROVIDER_CALLS=0")
                    print("IDEMPOTENT_REUSE=1")
                    return 0

            # Incomplete prior chapter-6: wipe dependent rows then chapter.
            from app.db.models import AnalysisArtifact, AnalysisEvidence, BoundaryReviewSession

            for run in list(
                session.scalars(
                    select(AnalysisRun).where(
                        AnalysisRun.subject_type == "chapter",
                        AnalysisRun.subject_id == str(existing.id),
                    )
                )
            ):
                for jr in list(
                    session.scalars(
                        select(ReaderJourneyRun).where(ReaderJourneyRun.analysis_run_id == run.id)
                    )
                ):
                    session.query(SceneReaderJourneyProfile).filter_by(
                        reader_journey_run_id=jr.id
                    ).delete()
                    session.query(ReaderJourneyPhase).filter_by(
                        reader_journey_run_id=jr.id
                    ).delete()
                    session.query(ChapterReaderJourneySummary).filter_by(
                        reader_journey_run_id=jr.id
                    ).delete()
                    session.delete(jr)
                session.query(BoundaryReviewSession).filter_by(analysis_run_id=run.id).delete()
                session.query(BoundaryRevision).filter_by(analysis_run_id=run.id).delete()
                session.query(AnalysisEvidence).filter(
                    AnalysisEvidence.artifact_id.in_(
                        select(AnalysisArtifact.id).where(AnalysisArtifact.run_id == run.id)
                    )
                ).delete(synchronize_session=False)
                session.query(AnalysisArtifact).filter_by(run_id=run.id).delete()
                session.query(Scene).filter_by(created_by_run_id=run.id).delete()
                session.delete(run)
            session.query(Scene).filter_by(chapter_id=existing.id).delete()
            session.query(Paragraph).filter_by(chapter_id=existing.id).delete()
            session.delete(existing)
            session.commit()

        chapter = Chapter(
            book_id=book.id,
            chapter_index=6,
            title="第六章 钩子丰富旅程",
            display_title="第六章 钩子丰富旅程",
            section_type="chapter",
        )
        session.add(chapter)
        session.flush()

        paragraphs: list[Paragraph] = []
        prefix = f"B{book.id:04d}-C{chapter.id:04d}"
        for index in range(1, 31):
            body = f"第{index}段：钩子丰富 MG 探针 — 主角在暗处观察门外动静。"
            p = Paragraph(
                id=f"{prefix}-P{index:04d}",
                book_id=book.id,
                chapter_id=chapter.id,
                paragraph_index=index,
                raw_text=body,
                normalized_text=body,
                char_start=index * 10,
                char_end=index * 10 + len(body),
            )
            session.add(p)
            paragraphs.append(p)
        session.flush()

        run = AnalysisRun(
            task_type="scene_pipeline",
            subject_type="chapter",
            subject_id=str(chapter.id),
            provider="aliyun_qwen_plus",
            model="qwen-plus",
            prompt_version="v3.5",
            schema_version="v1",
            input_hash=hashlib.sha256(f"hook-rich-{chapter.id}".encode()).hexdigest(),
            status="succeeded",
            execution_mode="cloud",
            cloud_consent=True,
            sends_content_to_cloud=True,
            completed_at=_utc_now(),
        )
        session.add(run)
        session.flush()

        # Temporary scenes for AI revision path then rematerialize via confirm.
        scenes_tmp: list[Scene] = []
        chunk = max(1, len(paragraphs) // 6)
        for ordinal in range(1, 7):
            start_idx = (ordinal - 1) * chunk
            end_idx = start_idx + chunk - 1 if ordinal < 6 else len(paragraphs) - 1
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
            scenes_tmp.append(scene)
        session.flush()
        _attach_scene_analysis(session, run, scenes_tmp)
        ensure_ai_model_revision_after_scenes_v1(session, run)
        mark_scenes_complete_awaiting_boundary_confirmation(session, run)
        session.commit()

        draft = create_or_get_scene_boundary_draft_v1(session, chapter.id)
        session.commit()
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
        confirmed, _already = confirm_scene_revision_v1(
            session, saved.id, expected_etag=saved.revision_etag
        )
        session.commit()

        scenes = list(
            session.scalars(
                select(Scene)
                .where(Scene.boundary_revision_id == confirmed.id)
                .order_by(Scene.ordinal)
            )
        )
        assert len(scenes) == 6, f"expected 6 confirmed scenes, got {len(scenes)}"

        now = _utc_now()
        journey = ReaderJourneyRun(
            analysis_run_id=run.id,
            book_id=book.id,
            chapter_id=chapter.id,
            status="succeeded",
            current_stage="complete",
            provider_name="aliyun_qwen_plus",
            model_name="qwen-plus",
            scene_prompt_version="v2.0",
            chapter_prompt_version="v2.0",
            scene_contract_version="2.0",
            chapter_contract_version="2.0",
            formula_version="1.0",
            genre="suspense",
            planner_version="1.1",
            total_scene_count=6,
            completed_scene_count=6,
            remaining_scene_count=0,
            completed_scene_ids_json=json.dumps([s.id for s in scenes]),
            remaining_scene_ids_json="[]",
            included_scene_ids_json=json.dumps([s.id for s in scenes]),
            started_at=now,
            completed_at=now,
            cloud_consent=True,
            client_request_id=f"mg-chg011-hook-rich-{chapter.id}",
            scene_revision_id=confirmed.id,
            scene_revision_no=confirmed.revision_number,
            scene_boundary_hash=confirmed.boundary_hash,
            chapter_text_hash=confirmed.chapter_text_hash,
            result_status="current",
            retryable=False,
        )
        session.add(journey)
        session.flush()

        # Map paragraph evidence for hooks (reuse fixture B questions).
        p_by_ord = {i + 1: paragraphs[i].id for i in range(len(paragraphs))}
        q_identity = "主角为什么会出现在这里？"
        q_danger = "门外的人是谁？"

        profiles_spec = [
            # S01 raise identity
            _base_profile(
                scene_id=scenes[0].id,
                ordinal=1,
                summary="开场身份疑云，读者开始追问主角来历。",
                evidence=[p_by_ord[1], p_by_ord[2]],
                hook_score=82,
                payoff_score=20,
                hooks=[
                    {
                        "type": "identity",
                        "summary": "身份疑问",
                        "strength": 82,
                        "evidence_paragraph_ids": [p_by_ord[1]],
                        "gap": "主角来历不明",
                        "continue_drive": "想弄清他是谁",
                        "next_handoff": "继续观察举动",
                    }
                ],
                reader_question_created=[
                    {
                        "question": q_identity,
                        "trigger_summary": "陌生出现",
                        "strength": 82,
                        "evidence_paragraph_ids": [p_by_ord[1]],
                    }
                ],
                reader_question_out=[
                    {
                        "question": q_identity,
                        "origin": "created_here",
                        "strength": 82,
                        "evidence_paragraph_ids": [p_by_ord[1]],
                        "hook_type": "identity",
                    }
                ],
            ),
            # S02 deepen identity
            _base_profile(
                scene_id=scenes[1].id,
                ordinal=2,
                summary="身份疑云加深，仍未给出明确答案。",
                evidence=[p_by_ord[6], p_by_ord[7]],
                hook_score=70,
                payoff_score=25,
                hooks=[
                    {
                        "type": "identity",
                        "summary": "身份疑云加深",
                        "strength": 70,
                        "evidence_paragraph_ids": [p_by_ord[6]],
                        "gap": "仍不知真实身份",
                        "continue_drive": "继续追问",
                        "next_handoff": "等待线索",
                    }
                ],
                reader_question_in=[
                    {
                        "question": q_identity,
                        "source": "carried_from_previous",
                        "confidence": 0.7,
                    }
                ],
                reader_question_out=[
                    {
                        "question": q_identity,
                        "origin": "carried",
                        "strength": 70,
                        "evidence_paragraph_ids": [p_by_ord[6]],
                        "hook_type": "identity",
                    }
                ],
            ),
            # S03 partial respond identity
            _base_profile(
                scene_id=scenes[2].id,
                ordinal=3,
                summary="给出部分身份回应，核心疑问仍在。",
                evidence=[p_by_ord[11], p_by_ord[12]],
                hook_score=45,
                payoff_score=72,
                payoffs=[
                    {
                        "type": "identity",
                        "summary": "部分回应身份",
                        "strength": 72,
                        "evidence_paragraph_ids": [p_by_ord[11]],
                    }
                ],
                reader_question_answered=[
                    {
                        "question": q_identity,
                        "answer_summary": "部分回应身份",
                        "answer_degree": "partial",
                        "evidence_paragraph_ids": [p_by_ord[11]],
                    }
                ],
                reader_question_out=[
                    {
                        "question": q_identity,
                        "origin": "carried",
                        "strength": 55,
                        "evidence_paragraph_ids": [p_by_ord[11]],
                        "hook_type": "identity",
                    }
                ],
            ),
            # S04 raise danger
            _base_profile(
                scene_id=scenes[3].id,
                ordinal=4,
                summary="门外出现危险来客，新问题被提出。",
                evidence=[p_by_ord[16], p_by_ord[17]],
                hook_score=78,
                payoff_score=20,
                hooks=[
                    {
                        "type": "danger",
                        "summary": "危险来客",
                        "strength": 78,
                        "evidence_paragraph_ids": [p_by_ord[16]],
                        "gap": "不知门外是谁",
                        "continue_drive": "想确认威胁",
                        "next_handoff": "靠近门边",
                    }
                ],
                reader_question_created=[
                    {
                        "question": q_danger,
                        "trigger_summary": "门外异响",
                        "strength": 78,
                        "evidence_paragraph_ids": [p_by_ord[16]],
                    }
                ],
                reader_question_out=[
                    {
                        "question": q_danger,
                        "origin": "created_here",
                        "strength": 78,
                        "evidence_paragraph_ids": [p_by_ord[16]],
                        "hook_type": "danger",
                    }
                ],
            ),
            # S05 deepen danger
            _base_profile(
                scene_id=scenes[4].id,
                ordinal=5,
                summary="危险感加重，门外身份仍未知。",
                evidence=[p_by_ord[21], p_by_ord[22]],
                hook_score=74,
                payoff_score=18,
                hooks=[
                    {
                        "type": "danger",
                        "summary": "威胁逼近",
                        "strength": 74,
                        "evidence_paragraph_ids": [p_by_ord[21]],
                        "gap": "来客仍未现身",
                        "continue_drive": "必须知道是谁",
                        "next_handoff": "章末悬置",
                    }
                ],
                reader_question_in=[
                    {
                        "question": q_danger,
                        "source": "carried_from_previous",
                        "confidence": 0.74,
                    }
                ],
                reader_question_out=[
                    {
                        "question": q_danger,
                        "origin": "carried",
                        "strength": 74,
                        "evidence_paragraph_ids": [p_by_ord[21]],
                        "hook_type": "danger",
                    }
                ],
            ),
            # S06 carry both
            _base_profile(
                scene_id=scenes[5].id,
                ordinal=6,
                summary="章末未兑现危险来客身份，期待留到下一章。",
                evidence=[p_by_ord[26], p_by_ord[27]],
                hook_score=60,
                payoff_score=15,
                reader_question_in=[
                    {
                        "question": q_danger,
                        "source": "carried_from_previous",
                        "confidence": 0.7,
                    }
                ],
                reader_question_out=[
                    {
                        "question": q_danger,
                        "origin": "carried",
                        "strength": 70,
                        "evidence_paragraph_ids": [p_by_ord[26]],
                        "hook_type": "danger",
                    }
                ],
            ),
        ]

        for spec in profiles_spec:
            item = SceneReaderJourneyProfileItem.model_validate(spec)
            dumped = item.model_dump()
            session.add(
                SceneReaderJourneyProfile(
                    reader_journey_run_id=journey.id,
                    scene_id=item.scene_id,
                    scene_ordinal=item.scene_ordinal,
                    scene_value_summary=item.scene_value_summary,
                    dominant_emotion=item.dominant_emotion,
                    curiosity_score=item.curiosity_score,
                    tension_score=item.tension_score,
                    payoff_score=item.payoff_score,
                    hook_score=item.hook_score,
                    information_gain_score=item.information_gain_score,
                    emotional_resonance_score=item.emotional_resonance_score,
                    cognitive_load_score=item.cognitive_load_score,
                    dropoff_risk_score=item.dropoff_risk_score,
                    engagement_score=55,
                    confidence=item.confidence,
                    validation_status="valid",
                    payload_json=json.dumps(dumped, ensure_ascii=False),
                )
            )

        session.add(
            ReaderJourneyPhase(
                reader_journey_run_id=journey.id,
                ordinal=1,
                title="开端",
                start_scene_ordinal=1,
                end_scene_ordinal=2,
                primary_reader_question=q_identity,
                dominant_emotion="curiosity",
                reading_payoff="建立身份疑云",
                continuation_motivation="想弄清主角来历",
                summary="开场提出身份问题并加深。",
                confidence=0.85,
            )
        )
        session.add(
            ReaderJourneyPhase(
                reader_journey_run_id=journey.id,
                ordinal=2,
                title="发展",
                start_scene_ordinal=3,
                end_scene_ordinal=5,
                primary_reader_question=q_danger,
                dominant_emotion="tension",
                reading_payoff="部分回应身份并引入危险",
                continuation_motivation="确认门外威胁",
                summary="部分回应后转入新的危险问题。",
                confidence=0.85,
            )
        )
        session.add(
            ReaderJourneyPhase(
                reader_journey_run_id=journey.id,
                ordinal=3,
                title="收束",
                start_scene_ordinal=6,
                end_scene_ordinal=6,
                primary_reader_question=q_danger,
                dominant_emotion="suspense",
                reading_payoff="危险身份留待后续",
                continuation_motivation="带着疑问进入下一章",
                summary="章末保留核心危险悬念。",
                confidence=0.8,
            )
        )

        lifecycle = [
            {
                "question_id": "ID-identity",
                "question_text": q_identity,
                "setup_scene": 1,
                "development_scenes": [2],
                "payoff_scene": 3,
                "status": "partial",
                "strength": 82,
            },
            {
                "question_id": "ID-danger",
                "question_text": q_danger,
                "setup_scene": 4,
                "development_scenes": [5],
                "payoff_scene": None,
                "status": "open",
                "strength": 78,
            },
        ]
        session.add(
            ChapterReaderJourneySummary(
                reader_journey_run_id=journey.id,
                chapter_value_summary="本章提出身份与危险两类核心问题，部分回应后仍牵引后续。",
                one_sentence_diagnosis=(
                    "本章连续提出问题，中段给出一次部分回应，核心悬念仍被保留并带到下一章。"
                ),
                overall_engagement_score=62,
                deterministic_statistics_json=json.dumps(
                    {"question_lifecycle": lifecycle}, ensure_ascii=False
                ),
                payload_json=json.dumps(
                    {
                        "fixture_source": "chg005FixtureBReliableHooks",
                        "chg": "CHG-20260729-011",
                    },
                    ensure_ascii=False,
                ),
                validation_status="valid",
            )
        )

        session.commit()

        viz = build_reader_journey_visualization(session, journey)
        if not viz:
            raise SystemExit("Failed to build visualization for Hook Rich journey")
        loops = viz.get("narrative_loops") or []
        questions = [str(l.get("question") or "") for l in loops]
        if q_identity not in questions or q_danger not in questions:
            raise SystemExit(f"Hook Rich loops missing fixture questions: {questions}")

        fixture = {
            "book_id": book.id,
            "chapter_id": chapter.id,
            "run_id": run.id,
            "journey_run_id": journey.id,
            "confirmed_revision_id": confirmed.id,
            "scene_count": 6,
            "narrative_loop_count": len(loops),
            "questions": questions,
            "fixture_source": "chg005FixtureBReliableHooks",
            "url": (
                f"http://127.0.0.1:1426/books/{book.id}"
                f"?chapter={chapter.id}&analysisRun={run.id}"
                f"&journeyRun={journey.id}&view=result&tab=reader-journey&lens=hook_payoff"
            ),
        }

        manifest_path = EVIDENCE / "FIXTURE_MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["fixtures"]["D_hook_rich"] = fixture
        manifest["urls"]["HOOK_RICH"] = fixture["url"]
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(fixture, ensure_ascii=False, indent=2))
        print("REAL_PROVIDER_CALLS=0")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
