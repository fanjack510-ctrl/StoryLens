#!/usr/bin/env python3
"""Seed an isolated SQLite DB with Reader Journey V2 native local-fixture data.

Does not touch %LOCALAPPDATA%\\StoryLens\\database\\storylens.db.
Does not call cloud models. Does not bump VERSION.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = (
    REPO_ROOT / "data" / "fixtures" / "reader_journey_v2_native" / "chapter_preview_v2.json"
)
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "runtime" / "rj-v2-native-verify"
FORBIDDEN_PROD_DB = Path.home() / "AppData" / "Local" / "StoryLens" / "database" / "storylens.db"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assert_not_prod_db(db_path: Path) -> None:
    resolved = db_path.resolve()
    forbidden = FORBIDDEN_PROD_DB.resolve()
    if resolved == forbidden:
        raise SystemExit(
            f"Refusing to write formal desktop DB: {forbidden}\n"
            "Use data/runtime/rj-v2-native-verify or another non-prod path."
        )
    # Also block LOCALAPPDATA StoryLens tree when env is set.
    local = Path.home() / "AppData" / "Local" / "StoryLens"
    try:
        resolved.relative_to(local.resolve())
        raise SystemExit(
            f"Refusing to write under formal StoryLens user data: {resolved}\n"
            "Use repo data/runtime/... instead."
        )
    except ValueError:
        pass


def _build_profile_payload(
    *,
    scene_id: int,
    scene_ordinal: int,
    paragraph_ids: list[str],
    scene_spec: dict,
) -> dict:
    first, last = paragraph_ids[0], paragraph_ids[-1]
    profile = dict(scene_spec["profile"])
    question = scene_spec.get("question_out") or "本章主疑问尚未闭合"
    hooks = []
    for item in scene_spec.get("hooks") or []:
        hooks.append(
            {
                "type": item["type"],
                "summary": item["summary"],
                "strength": int(item["strength"]),
                "evidence_paragraph_ids": [first],
            }
        )
    payoffs = []
    for item in scene_spec.get("payoffs") or []:
        payoffs.append(
            {
                "type": item["type"],
                "summary": item["summary"],
                "strength": int(item["strength"]),
                "evidence_paragraph_ids": [last],
            }
        )
    created = []
    if scene_ordinal == 1:
        created = [
            {
                "question": question,
                "trigger_summary": "井口铁锁出现新刮痕",
                "strength": 82,
                "evidence_paragraph_ids": [first],
            }
        ]
    q_in = []
    if scene_ordinal > 1:
        q_in = [
            {
                "question": "井口铁锁为什么被人动过",
                "source": "carried_from_previous",
                "confidence": 0.85,
            }
        ]
    answered = []
    if scene_ordinal == 9:
        answered = [
            {
                "question": "井口铁锁为什么被人动过",
                "answer_summary": "鞋印指向村里文书",
                "answer_degree": "partial",
                "evidence_paragraph_ids": [last],
            }
        ]
    payload = {
        "scene_id": scene_id,
        "scene_ordinal": scene_ordinal,
        "scene_value_summary": profile["scene_value_summary"],
        "reader_question_in": q_in,
        "reader_question_created": created,
        "reader_question_answered": answered,
        "reader_question_out": [
            {
                "question": question,
                "origin": "created_here" if scene_ordinal == 1 else "carried",
                "hook_type": "information",
                "strength": int(profile.get("hook_score", 40)),
                "evidence_paragraph_ids": [last],
            }
        ],
        "dominant_emotion": profile["dominant_emotion"],
        "emotional_valence_start": int(profile["emotional_valence_start"]),
        "emotional_valence_end": int(profile["emotional_valence_end"]),
        "arousal_start": int(profile["arousal_start"]),
        "arousal_end": int(profile["arousal_end"]),
        "curiosity_score": int(profile["curiosity_score"]),
        "tension_score": int(profile["tension_score"]),
        "payoff_score": int(profile["payoff_score"]),
        "hook_score": int(profile["hook_score"]),
        "information_gain_score": int(profile["information_gain_score"]),
        "emotional_resonance_score": int(profile["emotional_resonance_score"]),
        "cognitive_load_score": int(profile["cognitive_load_score"]),
        "dropoff_risk_score": int(profile["dropoff_risk_score"]),
        "payoffs": payoffs,
        "hooks": hooks,
        "techniques": [
            {
                "code": "evidence_anchor",
                "name": "证据锚定",
                "mechanism": "用可验证物证承载疑问",
                "reader_effect": "读者对照正文证据",
                "transfer_formula": "异常细节+可复验物证",
                "risk": "证据弱则像空钩",
                "evidence_paragraph_ids": [first],
            }
        ],
        "risk_points": [
            {
                "type": "slow_progress" if scene_ordinal == 2 else "weak_hook",
                "summary": f"V2案例节点 S{scene_ordinal}",
                "severity": 40,
                "evidence_paragraph_ids": [last],
            }
        ],
        "emotion_beats": [
            {
                "label": profile["dominant_emotion"][:20],
                "valence": int(profile["emotional_valence_end"]),
                "arousal": int(profile["arousal_end"]),
                "evidence_paragraph_ids": [first],
            }
        ],
        "information_changes": [
            {
                "type": "new_information",
                "summary": profile["scene_value_summary"][:80],
                "certainty": "fact",
                "evidence_paragraph_ids": [first],
            }
        ],
        "character_effects": [
            {
                "character_name": "陈岁",
                "trait_or_change": "对铁锁异常的反应推动阅读",
                "method": "action",
                "evidence_paragraph_ids": [first],
            }
        ],
        "writing_takeaways": [
            {
                "summary": "合成诊断测试节点需保留正文证据引用",
                "applicable_when": "本地fixture验证",
                "avoid_when": "正式云端分析",
            }
        ],
        "confidence": float(profile["confidence"]),
        "evidence_paragraph_ids": paragraph_ids[:16],
    }
    return payload


def seed(*, fixture_path: Path, data_dir: Path, reset: bool) -> dict:
    sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

    data_dir = data_dir.resolve()
    db_path = data_dir / "database" / "storylens.db"
    _assert_not_prod_db(db_path)

    if reset and db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    (data_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (data_dir / "exports").mkdir(parents=True, exist_ok=True)

    db_url = f"sqlite:///{db_path.as_posix()}"
    # Must set before importing app.db.session / Settings.
    import os

    os.environ["STORYLENS_DATABASE_URL"] = db_url
    os.environ["STORYLENS_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("STORYLENS_APP_ENV", "development")

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.db.models import (
        AnalysisArtifact,
        AnalysisEvidence,
        AnalysisRun,
        Base,
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
    from app.db.session import (
        migrate_phase_1b,
        migrate_phase_1c_a,
        migrate_phase_1c_a3,
        migrate_phase_1c_a4,
        migrate_phase_1c_a7,
        migrate_phase_1c_c1,
        migrate_phase_1d_c1_uat05,
        migrate_phase_2a1,
        migrate_phase_2b1,
        migrate_phase_2b2,
    )
    from app.schemas.reader_journey import SceneReaderJourneyProfileItem

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    for key in ("contract_version", "prompt_version", "formula_version", "source_mode"):
        if key not in fixture:
            raise SystemExit(f"Fixture missing required field: {key}")
    if fixture["contract_version"] != "2.0":
        raise SystemExit("Fixture contract_version must be 2.0")
    if fixture["source_mode"] not in {"local_fixture", "v2_native"}:
        raise SystemExit("Fixture source_mode must be local_fixture or v2_native")

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    for migrate in (
        migrate_phase_1b,
        migrate_phase_2a1,
        migrate_phase_2b1,
        migrate_phase_2b2,
        migrate_phase_1c_a,
        migrate_phase_1c_a3,
        migrate_phase_1c_a4,
        migrate_phase_1c_a7,
        migrate_phase_1c_c1,
        migrate_phase_1d_c1_uat05,
    ):
        migrate(engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    scenes_spec = fixture["scenes"]
    if len(scenes_spec) < 10:
        raise SystemExit("Fixture must include at least 9 main scenes + 1 beat (10 nodes)")
    beat_count = sum(1 for s in scenes_spec if s.get("node_type") == "beat")
    main_count = len(scenes_spec) - beat_count
    if main_count < 9 or beat_count < 1:
        raise SystemExit("Fixture must include >=9 main scenes and >=1 beat")

    with SessionLocal() as session:
        existing = session.scalar(
            select(Book).where(Book.fixture_name == fixture["fixture_id"])
        )
        if existing is not None and not reset:
            raise SystemExit(
                f"Fixture book already present (id={existing.id}). Re-run with --reset."
            )
        if existing is not None and reset:
            session.delete(existing)
            session.commit()

        book = Book(
            title=fixture["book_title"],
            source_file_name="chapter_preview_v2.json",
            source_file_hash=_sha(
                f"{fixture['fixture_id']}:{fixture['fixture_version']}:{fixture['book_title']}"
            ),
            fixture_name=fixture["fixture_id"],
            fixture_version=fixture["fixture_version"],
        )
        session.add(book)
        session.flush()

        chapter = Chapter(
            book_id=book.id,
            chapter_index=1,
            title=fixture["chapter_title"],
            display_title=fixture.get("chapter_display_title") or fixture["chapter_title"],
            section_type="chapter",
            word_count=0,
        )
        session.add(chapter)
        session.flush()

        paragraphs: list[Paragraph] = []
        paragraph_index = 0
        scene_paragraph_ids: dict[int, list[str]] = {}
        for scene_spec in scenes_spec:
            ordinal = int(scene_spec["ordinal"])
            ids: list[str] = []
            for text in scene_spec["paragraphs"]:
                paragraph_index += 1
                pid = f"B{book.id:04d}-C0001-P{paragraph_index:04d}"
                row = Paragraph(
                    id=pid,
                    book_id=book.id,
                    chapter_id=chapter.id,
                    paragraph_index=paragraph_index,
                    raw_text=text,
                    normalized_text=text,
                    char_start=0,
                    char_end=len(text),
                )
                session.add(row)
                paragraphs.append(row)
                ids.append(pid)
                chapter.word_count = (chapter.word_count or 0) + len(text)
            scene_paragraph_ids[ordinal] = ids
            if chapter.start_paragraph_id is None:
                chapter.start_paragraph_id = ids[0]
            chapter.end_paragraph_id = ids[-1]
        session.flush()

        run = AnalysisRun(
            task_type="scene_pipeline",
            provider="local_fixture",
            model="v2-native-preview",
            prompt_version=str(fixture["prompt_version"]),
            schema_version=str(fixture["contract_version"]),
            input_hash=_sha(fixture_path.read_text(encoding="utf-8")),
            status="succeeded",
            subject_type="chapter",
            subject_id=str(chapter.id),
            prompt_hash=_sha("reader-journey-v2-native-preview"),
            progress_current=len(scenes_spec),
            progress_total=len(scenes_spec),
            analysis_mode="assisted_boundary_review",
            execution_mode="local",
            cloud_consent=False,
            sends_content_to_cloud=False,
            completed_at=_utc_now(),
        )
        session.add(run)
        session.flush()

        review = BoundaryReviewSession(
            book_id=book.id,
            chapter_id=chapter.id,
            analysis_run_id=run.id,
            prompt_version=str(fixture["prompt_version"]),
            provider="local_fixture",
            model="v2-native-preview",
            status="confirmed",
            confirmed_by="v2-fixture-seed",
            completed_at=_utc_now(),
        )
        session.add(review)
        session.flush()

        revision = BoundaryRevision(
            review_session_id=review.id,
            chapter_id=chapter.id,
            analysis_run_id=run.id,
            revision_number=1,
            final_boundaries_json="[]",
            confirmed_by="v2-fixture-seed",
            confirmed_at=_utc_now(),
            coverage_rate=1.0,
        )
        session.add(revision)
        session.flush()

        scenes: list[Scene] = []
        for scene_spec in scenes_spec:
            ordinal = int(scene_spec["ordinal"])
            pids = scene_paragraph_ids[ordinal]
            scene = Scene(
                scene_key=f"B{book.id:04d}-C0001-R0001-S{ordinal:04d}",
                book_id=book.id,
                chapter_id=chapter.id,
                ordinal=ordinal,
                start_paragraph_id=pids[0],
                end_paragraph_id=pids[-1],
                content_hash=_sha("|".join(pids)),
                created_by_run_id=run.id,
                boundary_confidence=0.95,
                boundary_detected=True,
                boundary_revision_id=revision.id,
                boundary_source="user_added",
            )
            session.add(scene)
            scenes.append(scene)
        session.flush()

        for scene in scenes:
            payload = {
                "scene_id": scene.scene_key,
                "entry_state": {
                    "summary": f"进入-S{scene.ordinal}",
                    "evidence_paragraph_ids": [scene.start_paragraph_id],
                },
                "goal": {
                    "summary": f"目标-S{scene.ordinal}",
                    "evidence_paragraph_ids": [scene.start_paragraph_id],
                },
                "obstacle": {"summary": "", "evidence_paragraph_ids": []},
                "key_actions": [
                    {
                        "summary": f"行动-S{scene.ordinal}",
                        "evidence_paragraph_ids": [scene.start_paragraph_id],
                    }
                ],
                "turning_point": {"summary": "", "evidence_paragraph_ids": []},
                "outcome": {
                    "summary": f"结果-S{scene.ordinal}",
                    "evidence_paragraph_ids": [scene.end_paragraph_id],
                },
                "unresolved_question": {"summary": "", "evidence_paragraph_ids": []},
                "function_tags": ["事件推进"],
                "confidence": 0.9,
            }
            artifact = AnalysisArtifact(
                run_id=run.id,
                artifact_type="scene_analysis",
                subject_type="scene",
                subject_id=str(scene.id),
                schema_version="v1",
                prompt_version=str(fixture["prompt_version"]),
                payload_json=json.dumps(payload, ensure_ascii=False),
                confidence=0.9,
                validation_status="valid",
            )
            session.add(artifact)
            session.flush()
            session.add(
                AnalysisEvidence(
                    artifact_id=artifact.id,
                    field_path="goal.evidence",
                    paragraph_id=scene.start_paragraph_id,
                    paragraph_hash=_sha(scene.start_paragraph_id),
                )
            )

        display_banner = str(
            fixture.get("display_banner")
            or "合成测试数据：仅用于验证V2图表、数据透传和诊断规则，不代表真实小说分析结果。"
        )
        failure_details = {
            "source_mode": fixture["source_mode"],
            "fixture_id": fixture["fixture_id"],
            "fixture_version": fixture["fixture_version"],
            "display_banner": display_banner,
            "semantic_calibration_audit": [
                {
                    "version": "2.0",
                    "source": "local_fixture",
                    "calibrated": True,
                }
            ],
        }
        journey = ReaderJourneyRun(
            analysis_run_id=run.id,
            book_id=book.id,
            chapter_id=chapter.id,
            status="succeeded",
            current_stage="succeeded",
            provider_name="local_fixture",
            model_name="v2-native-preview",
            scene_prompt_version=str(fixture["prompt_version"]),
            chapter_prompt_version=str(fixture["prompt_version"]),
            scene_contract_version=str(fixture["contract_version"]),
            chapter_contract_version=str(fixture["contract_version"]),
            formula_version=str(fixture["formula_version"]),
            genre=str(fixture.get("genre") or "suspense"),
            planner_version="2.0",
            total_scene_count=len(scenes),
            completed_scene_count=len(scenes),
            remaining_scene_count=0,
            completed_scene_ids_json=json.dumps([s.id for s in scenes]),
            remaining_scene_ids_json="[]",
            started_at=_utc_now(),
            completed_at=_utc_now(),
            failure_details_json=json.dumps(failure_details, ensure_ascii=False),
            cloud_consent=False,
            client_request_id=f"v2-native-preview-{fixture['fixture_version']}",
        )
        session.add(journey)
        session.flush()

        scene_diagnoses = []
        v2_scene_scores = {}
        v2_node_overrides = {}
        for scene, scene_spec in zip(scenes, scenes_spec, strict=True):
            pids = scene_paragraph_ids[int(scene_spec["ordinal"])]
            profile_dict = _build_profile_payload(
                scene_id=scene.id,
                scene_ordinal=scene.ordinal,
                paragraph_ids=pids,
                scene_spec=scene_spec,
            )
            profile_item = SceneReaderJourneyProfileItem.model_validate(profile_dict)
            payload_json = json.dumps(profile_item.model_dump(), ensure_ascii=False)
            artifact = AnalysisArtifact(
                run_id=run.id,
                artifact_type="reader_journey_scene_profile",
                subject_type="scene",
                subject_id=str(scene.id),
                schema_version=str(fixture["contract_version"]),
                prompt_version=str(fixture["prompt_version"]),
                payload_json=payload_json,
                confidence=profile_item.confidence,
                validation_status="valid",
            )
            session.add(artifact)
            session.flush()
            for pid in profile_item.evidence_paragraph_ids:
                session.add(
                    AnalysisEvidence(
                        artifact_id=artifact.id,
                        field_path="evidence_paragraph_ids",
                        paragraph_id=pid,
                        paragraph_hash=_sha(pid),
                    )
                )
            scores = scene_spec["v2_scores"]
            session.add(
                SceneReaderJourneyProfile(
                    reader_journey_run_id=journey.id,
                    scene_id=scene.id,
                    scene_ordinal=scene.ordinal,
                    scene_value_summary=profile_item.scene_value_summary,
                    dominant_emotion=profile_item.dominant_emotion,
                    emotional_valence_start=profile_item.emotional_valence_start,
                    emotional_valence_end=profile_item.emotional_valence_end,
                    arousal_start=profile_item.arousal_start,
                    arousal_end=profile_item.arousal_end,
                    curiosity_score=profile_item.curiosity_score,
                    tension_score=profile_item.tension_score,
                    payoff_score=profile_item.payoff_score,
                    hook_score=profile_item.hook_score,
                    information_gain_score=profile_item.information_gain_score,
                    emotional_resonance_score=profile_item.emotional_resonance_score,
                    cognitive_load_score=profile_item.cognitive_load_score,
                    dropoff_risk_score=profile_item.dropoff_risk_score,
                    engagement_score=int(round(float(scores["reading_momentum"]))),
                    confidence=profile_item.confidence,
                    payload_json=payload_json,
                    validation_status="valid",
                    artifact_id=artifact.id,
                )
            )
            diag = dict(scene_spec["diagnosis"])
            diag["scene_ordinal"] = scene.ordinal
            scene_diagnoses.append(diag)
            v2_scene_scores[str(scene.ordinal)] = dict(scores)
            v2_node_overrides[str(scene.ordinal)] = {
                "node_type": scene_spec.get("node_type", "scene"),
                "role": "beat" if scene_spec.get("node_type") == "beat" else "core",
                "scene_role": scene_spec.get("scene_role"),
                "include_in_main_curve": scene_spec.get("node_type") != "beat",
                "include_in_chapter_mean": scene_spec.get("node_type") != "beat",
                "case_labels": scene_spec.get("case_labels") or [],
            }

        for phase in fixture.get("phases") or []:
            session.add(
                ReaderJourneyPhase(
                    reader_journey_run_id=journey.id,
                    ordinal=int(phase["ordinal"]),
                    title=phase["title"],
                    start_scene_ordinal=int(phase["start_scene_ordinal"]),
                    end_scene_ordinal=int(phase["end_scene_ordinal"]),
                    primary_reader_question=phase["primary_reader_question"],
                    dominant_emotion=phase["dominant_emotion"],
                    reading_payoff=phase["reading_payoff"],
                    continuation_motivation=phase["continuation_motivation"],
                    summary=phase["summary"],
                    confidence=float(phase.get("confidence", 0.9)),
                    payload_json="{}",
                )
            )

        deterministic = {
            "source_mode": fixture["source_mode"],
            "fixture_id": fixture["fixture_id"],
            "contract_version": fixture["contract_version"],
            "prompt_version": fixture["prompt_version"],
            "formula_version": fixture["formula_version"],
            "question_lifecycle": fixture.get("question_lifecycle") or [],
            "scene_diagnoses": scene_diagnoses,
            "v2_scene_scores": v2_scene_scores,
            "v2_node_overrides": v2_node_overrides,
            "evidence_coverage_rate": 1.0,
            "semantic_calibration_version": "2.0",
        }
        session.add(
            ChapterReaderJourneySummary(
                reader_journey_run_id=journey.id,
                chapter_value_summary="合成诊断测试章：覆盖停滞/空转/节奏/好奇紧张/钩子兑现/情绪与Beat（非真实小说）。",
                chapter_reader_question_chain_json=json.dumps(
                    [
                        {
                            "question_chain_id": "qc-iron-lock",
                            "question_summary": "井口铁锁为什么被人动过",
                            "created_scene_ordinal": 1,
                            "carried_scene_ordinals": [2, 4, 5, 6, 7, 8],
                            "answered_scene_ordinal": 9,
                            "status": "answered",
                            "strength": 86,
                        }
                    ],
                    ensure_ascii=False,
                ),
                overall_engagement_score=62,
                strongest_hook_scene_ids_json=json.dumps([scenes[0].id]),
                strongest_payoff_scene_ids_json=json.dumps([scenes[8].id]),
                risk_scene_ids_json=json.dumps([scenes[1].id, scenes[3].id]),
                positive_feedback_distribution_json="{}",
                hook_distribution_json="{}",
                emotion_trend_summary="由平淡停滞升至情绪高点",
                pacing_diagnosis_json=json.dumps(
                    ["含空转快节奏与节奏偏慢对照节点"], ensure_ascii=False
                ),
                one_sentence_diagnosis=fixture["one_sentence_diagnosis"],
                deterministic_statistics_json=json.dumps(deterministic, ensure_ascii=False),
                payload_json=json.dumps(
                    {
                        "chapter_strengths": ["有效兑现", "情绪高点"],
                        "chapter_risks": ["剧情停滞", "空转快节奏", "好奇不足"],
                        "source_mode": fixture["source_mode"],
                        "display_banner": display_banner,
                    },
                    ensure_ascii=False,
                ),
                validation_status="valid",
            )
        )
        session.commit()

        return {
            "data_dir": str(data_dir),
            "database_path": str(db_path),
            "database_url": db_url,
            "fixture_path": str(fixture_path.resolve()),
            "book_id": book.id,
            "book_title": book.title,
            "chapter_id": chapter.id,
            "chapter_title": chapter.title,
            "analysis_run_id": run.id,
            "journey_run_id": journey.id,
            "scene_count": len(scenes),
            "contract_version": journey.scene_contract_version,
            "prompt_version": journey.scene_prompt_version,
            "formula_version": journey.formula_version,
            "source_mode": fixture["source_mode"],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Path to V2 native fixture JSON",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Isolated StoryLens data dir (DB under database/storylens.db)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing verify DB before seeding",
    )
    args = parser.parse_args()
    if not args.fixture.is_file():
        raise SystemExit(f"Fixture not found: {args.fixture}")
    result = seed(fixture_path=args.fixture, data_dir=args.data_dir, reset=args.reset)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print()
    print("Seed OK. Start with the same DATABASE_URL / DATA_DIR, then open:")
    print("  http://127.0.0.1:1420")
    print(f"  Book: {result['book_title']}")
    print(f"  Chapter: {result['chapter_title']}")
    print(f"  Analysis run id: {result['analysis_run_id']}")


if __name__ == "__main__":
    main()
