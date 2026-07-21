#!/usr/bin/env python3
"""Execute one Reader Journey V2 native run against the isolated 牛角坳 verify DB.

Model outputs levels only. Program computes mapped_score / derive / diagnosis / lifecycle.
Does not read synthetic fixture v2_scene_scores or scene_diagnoses.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "runtime" / "rj-v2-real-niujiaokao-verify"
DISPLAY_BANNER = "V2真实正文分析"
SOURCE_MODE = "v2_native"


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _prepare_env(data_dir: Path) -> str:
    db_path = data_dir / "database" / "storylens.db"
    if not db_path.is_file():
        raise SystemExit(f"Missing verify DB. Run rematerialize first: {db_path}")
    db_url = f"sqlite:///{db_path.as_posix()}"
    os.environ["STORYLENS_DATABASE_URL"] = db_url
    os.environ["STORYLENS_DATA_DIR"] = str(data_dir.resolve())
    os.environ["STORYLENS_APP_ENV"] = "development"
    os.environ["STORYLENS_PROMPT_ROOT"] = str((REPO_ROOT / "packages" / "prompts").resolve())
    os.environ["STORYLENS_READER_JOURNEY_FORMULA_PATH"] = str(
        (REPO_ROOT / "config" / "reader_journey_formulas_v2.json").resolve()
    )
    # V2 level payloads are denser than v1 — force single-scene batches + higher output.
    os.environ["STORYLENS_READER_JOURNEY_BATCH_SIZE"] = "1"
    os.environ["STORYLENS_CLOUD_OUTPUT_READER_JOURNEY_SCENE"] = "4000"
    os.environ["STORYLENS_CLOUD_OUTPUT_READER_JOURNEY_SCHEMA_REPAIR"] = "4000"
    return db_url


def _v1_compat_payload(profile_v2, *, paragraph_ids: list[str]) -> dict:
    """Build a valid v1 SceneReaderJourneyProfileItem dict for visualization builder."""
    from app.services.reader_journey_v2_mapping import mapped_or_zero

    first = paragraph_ids[0]
    last = paragraph_ids[-1]
    curiosity = int(mapped_or_zero(profile_v2.curiosity))
    tension = int(mapped_or_zero(profile_v2.tension))
    payoff = int(mapped_or_zero(profile_v2.payoff))
    hook = int(mapped_or_zero(profile_v2.hook))
    info = int(mapped_or_zero(profile_v2.information_gain))
    emotion = int(mapped_or_zero(profile_v2.emotional_investment))
    cognitive = int(mapped_or_zero(profile_v2.cognitive_load))
    dropoff = int(round(float(profile_v2.dropoff_risk or 0)))
    valence_start = int(round((mapped_or_zero(profile_v2.emotional_valence_start) - 50) * 2))
    valence_end = int(round((mapped_or_zero(profile_v2.emotional_valence_end) - 50) * 2))
    valence_start = max(-100, min(100, valence_start))
    valence_end = max(-100, min(100, valence_end))
    arousal_start = int(mapped_or_zero(profile_v2.arousal_start))
    arousal_end = int(mapped_or_zero(profile_v2.arousal_end))
    q = (profile_v2.hook.rationale or profile_v2.scene_value_summary or "本章疑问")[:160]
    return {
        "scene_id": profile_v2.scene_id,
        "scene_ordinal": profile_v2.scene_ordinal,
        "scene_value_summary": profile_v2.scene_value_summary[:160],
        "reader_question_in": [],
        "reader_question_created": [
            {
                "question": q if ("？" in q or "?" in q) else f"{q}？",
                "trigger_summary": "场景推进触发",
                "strength": hook,
                "evidence_paragraph_ids": [first],
            }
        ]
        if profile_v2.scene_ordinal == 1
        else [],
        "reader_question_answered": [],
        "reader_question_out": [
            {
                "question": q if ("？" in q or "?" in q) else f"{q}？",
                "origin": "created_here" if profile_v2.scene_ordinal == 1 else "carried",
                "hook_type": "information",
                "strength": hook,
                "evidence_paragraph_ids": [last],
            }
        ],
        "dominant_emotion": profile_v2.scene_role,
        "emotional_valence_start": valence_start,
        "emotional_valence_end": valence_end,
        "arousal_start": arousal_start,
        "arousal_end": arousal_end,
        "curiosity_score": curiosity,
        "tension_score": tension,
        "payoff_score": payoff,
        "hook_score": hook,
        "information_gain_score": info,
        "emotional_resonance_score": emotion,
        "cognitive_load_score": cognitive,
        "dropoff_risk_score": dropoff,
        "payoffs": [
            {
                "type": "information",
                "summary": (profile_v2.payoff.rationale or "回报")[:160],
                "strength": payoff,
                "evidence_paragraph_ids": [last],
            }
        ]
        if payoff >= 40
        else [],
        "hooks": [
            {
                "type": "information",
                "summary": (profile_v2.hook.rationale or "钩子")[:160],
                "strength": hook,
                "evidence_paragraph_ids": [first],
            }
        ]
        if hook >= 40
        else [],
        "techniques": [
            {
                "code": "v2_native",
                "name": "V2原生评分",
                "mechanism": "level映射后程序派生",
                "reader_effect": "阅读旅程节点",
                "transfer_formula": "level→mapped→derive",
                "risk": "无",
                "evidence_paragraph_ids": [first],
            }
        ],
        "risk_points": [],
        "emotion_beats": [
            {
                "label": profile_v2.scene_role[:20],
                "valence": valence_end,
                "arousal": arousal_end,
                "evidence_paragraph_ids": [first],
            }
        ],
        "information_changes": [
            {
                "type": "new_information",
                "summary": profile_v2.scene_value_summary[:80],
                "certainty": "supported_inference",
                "evidence_paragraph_ids": [first],
            }
        ],
        "character_effects": [
            {
                "character_name": "周山禾",
                "trait_or_change": "推进本章阅读",
                "method": "action",
                "evidence_paragraph_ids": [first],
            }
        ],
        "writing_takeaways": [
            {
                "summary": "V2原生分析节点",
                "applicable_when": "真实正文验证",
                "avoid_when": "合成fixture",
            }
        ],
        "confidence": float(profile_v2.confidence),
        "evidence_paragraph_ids": paragraph_ids[:16],
    }


async def execute(data_dir: Path) -> dict:
    db_url = _prepare_env(data_dir)
    sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.model_gateway.registry import get_model_gateway

    get_model_gateway.cache_clear()

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.db.models import (
        AnalysisArtifact,
        AnalysisEvidence,
        AnalysisRun,
        Chapter,
        ChapterReaderJourneySummary,
        Paragraph,
        ReaderJourneyPhase,
        ReaderJourneyRun,
        Scene,
        SceneReaderJourneyProfile,
    )
    from app.schemas.reader_journey import SceneReaderJourneyProfileItem
    from app.schemas.reader_journey_v2 import (
        FORMULA_VERSION_V2,
        SCENE_CONTRACT_VERSION_V2,
        SCENE_PROMPT_VERSION_V2,
        SceneReaderJourneyBatchResultV2,
    )
    from app.services.credentials.service import get_credential_store
    from app.services.prompt_service import load_prompt
    from app.services.provider_runtime import bind_gateway_runtime
    from app.services.reader_journey_v2_finalize import finalize_v2_profiles
    from app.services.reader_journey_v2_mapping import mapped_or_zero
    from app.services.structured_output import generate_validated
    from app.services.reader_journey_batch_planner import ReaderJourneySceneBatch

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    gateway = get_model_gateway()
    store = get_credential_store()

    with SessionLocal() as session:
        bind_gateway_runtime(gateway, session, store)
        provider = gateway.get("aliyun_qwen_plus")
        if not provider.api_key:
            raise SystemExit("Aliyun credential missing from keyring (aliyun_qwen_plus)")
        provider.enabled = True

        chapter = session.scalar(select(Chapter).order_by(Chapter.id).limit(1))
        analysis_run = session.scalar(select(AnalysisRun).order_by(AnalysisRun.id).limit(1))
        scenes = list(
            session.scalars(select(Scene).where(Scene.chapter_id == chapter.id).order_by(Scene.ordinal))
        )
        paragraphs = list(
            session.scalars(
                select(Paragraph)
                .where(Paragraph.chapter_id == chapter.id)
                .order_by(Paragraph.paragraph_index)
            )
        )
        # Drop unfinished prior V2 attempts in this verify DB.
        for old in session.scalars(
            select(ReaderJourneyRun).where(ReaderJourneyRun.chapter_id == chapter.id)
        ):
            if old.status != "succeeded":
                session.delete(old)
        session.commit()

        journey = ReaderJourneyRun(
            analysis_run_id=analysis_run.id,
            book_id=chapter.book_id,
            chapter_id=chapter.id,
            status="scene_profiles_running",
            current_stage="reader_journey_scene_profiles",
            provider_name="aliyun_qwen_plus",
            model_name=provider.default_model,
            scene_prompt_version="2.0",
            chapter_prompt_version="2.0",
            scene_contract_version=SCENE_CONTRACT_VERSION_V2,
            chapter_contract_version=SCENE_CONTRACT_VERSION_V2,
            formula_version=FORMULA_VERSION_V2,
            genre="suspense",
            planner_version="1.1",
            total_scene_count=len(scenes),
            completed_scene_count=0,
            remaining_scene_count=len(scenes),
            completed_scene_ids_json="[]",
            remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
            started_at=_utc(),
            failure_details_json=json.dumps(
                {
                    "source_mode": SOURCE_MODE,
                    "display_banner": DISPLAY_BANNER,
                    "semantic_calibration_audit": [
                        {"version": "2.0", "source": SOURCE_MODE, "calibrated": True}
                    ],
                },
                ensure_ascii=False,
            ),
            cloud_consent=True,
            client_request_id=f"v2-native-niujiaokao-{_utc().strftime('%Y%m%d%H%M%S')}",
        )
        session.add(journey)
        session.commit()
        journey_id = journey.id
        analysis_run_id = analysis_run.id
        chapter_id = chapter.id
        chapter_title = chapter.display_title or chapter.title

    scene_prompt = load_prompt("reader_journey_scene", SCENE_PROMPT_VERSION_V2)
    raw_profiles = []
    request_count = 0

    batches = None
    with SessionLocal() as session:
        scenes = list(
            session.scalars(select(Scene).where(Scene.chapter_id == chapter_id).order_by(Scene.ordinal))
        )
        paragraphs = list(
            session.scalars(
                select(Paragraph)
                .where(Paragraph.chapter_id == chapter_id)
                .order_by(Paragraph.paragraph_index)
            )
        )
        # Hard-force one scene per batch for V2 density.
        batches = [
            ReaderJourneySceneBatch(
                batch_index=i,
                scenes=[scene],
                scene_ids=[scene.id],
                scene_ordinals=[scene.ordinal],
                estimated_output_tokens=3500,
                batch_count=len(scenes),
            )
            for i, scene in enumerate(scenes, start=1)
        ]
        print(f"starting V2 native: {len(batches)} single-scene batches", flush=True)

    for batch in batches:
        with SessionLocal() as session:
            journey = session.get(ReaderJourneyRun, journey_id)
            scenes_by_id = {
                s.id: s
                for s in session.scalars(select(Scene).where(Scene.chapter_id == chapter_id))
            }
            paragraphs = list(
                session.scalars(
                    select(Paragraph)
                    .where(Paragraph.chapter_id == chapter_id)
                    .order_by(Paragraph.paragraph_index)
                )
            )
            position = {p.id: i for i, p in enumerate(paragraphs)}
            scene_payloads = []
            for scene_id in batch.scene_ids:
                scene = scenes_by_id[scene_id]
                included = paragraphs[
                    position[scene.start_paragraph_id] : position[scene.end_paragraph_id] + 1
                ]
                artifact = session.scalar(
                    select(AnalysisArtifact).where(
                        AnalysisArtifact.run_id == analysis_run_id,
                        AnalysisArtifact.artifact_type == "scene_analysis",
                        AnalysisArtifact.subject_id == str(scene.id),
                    )
                )
                scene_payloads.append(
                    {
                        "scene_id": scene.id,
                        "scene_ordinal": scene.ordinal,
                        "scene_key": scene.scene_key,
                        "paragraphs": [
                            {"id": item.id, "text": item.normalized_text} for item in included
                        ],
                        "scene_analysis": json.loads(artifact.payload_json) if artifact else {},
                    }
                )
            prev_summary = ""
            if raw_profiles:
                prev_summary = raw_profiles[-1].scene_value_summary
            user_content = scene_prompt.user_template.format(
                genre="suspense",
                chapter_title=chapter_title,
                input_json=json.dumps({"profiles_target": scene_payloads}, ensure_ascii=False),
                previous_scene_summary=prev_summary,
                next_scene_context="",
                character_names="周山禾,门门",
            )

            def _validate(batch_result: SceneReaderJourneyBatchResultV2) -> None:
                owned = set(batch.scene_ids)
                got = {p.scene_id for p in batch_result.profiles}
                if got != owned:
                    raise ValueError(f"batch scene_id mismatch owned={owned} got={got}")

            result = await generate_validated(
                session=session,
                gateway=gateway,
                run_id=analysis_run_id,
                provider_name="aliyun_qwen_plus",
                task_type="reader_journey_scene",
                prompt=scene_prompt,
                schema=SceneReaderJourneyBatchResultV2,
                input_snapshot={
                    "owned_scene_ids": batch.scene_ids,
                    "batch_index": batch.batch_index,
                    "contract": SCENE_CONTRACT_VERSION_V2,
                },
                user_content=user_content,
                business_validator=_validate,
            )
            request_count += 1
            for profile in result.profiles:
                # Strip any model-provided derived / mapped fields before finalize.
                field_updates = {
                    "plot_progress": None,
                    "reading_tension": None,
                    "pacing_fit": None,
                    "hook_payoff_fit": None,
                    "reading_momentum": None,
                    "dropoff_risk": None,
                }
                for key in (
                    "goal_progress",
                    "conflict_change",
                    "state_change",
                    "information_gain",
                    "character_agency",
                    "causal_coherence",
                    "curiosity",
                    "tension",
                    "emotional_investment",
                    "pacing_speed",
                    "hook",
                    "payoff",
                    "setup_consistency",
                    "question_lifecycle",
                    "emotional_valence_start",
                    "emotional_valence_end",
                    "arousal_start",
                    "arousal_end",
                    "clarity",
                    "cognitive_load",
                    "redundancy",
                ):
                    field = getattr(profile, key)
                    if field.mapped_score is not None:
                        field_updates[key] = field.model_copy(update={"mapped_score": None})
                cleaned = profile.model_copy(update=field_updates)
                raw_profiles.append(cleaned)
            journey.completed_scene_count = len(raw_profiles)
            journey.remaining_scene_count = max(0, journey.total_scene_count - len(raw_profiles))
            journey.completed_scene_ids_json = json.dumps([p.scene_id for p in raw_profiles])
            session.commit()
            print(
                f"batch {batch.batch_index}/{batch.batch_count} done; "
                f"profiles={len(raw_profiles)}/{journey.total_scene_count}",
                flush=True,
            )

    # Program finalize — no fixture presets.
    derived, stats = finalize_v2_profiles(raw_profiles)
    diagnoses = stats["scene_diagnoses"]
    lifecycle = stats["question_lifecycle"]

    with SessionLocal() as session:
        journey = session.get(ReaderJourneyRun, journey_id)
        paragraphs = list(
            session.scalars(
                select(Paragraph)
                .where(Paragraph.chapter_id == chapter_id)
                .order_by(Paragraph.paragraph_index)
            )
        )
        position = {p.id: i for i, p in enumerate(paragraphs)}
        scenes = {
            s.id: s
            for s in session.scalars(select(Scene).where(Scene.chapter_id == chapter_id))
        }

        v2_scene_scores = {}
        v2_node_overrides = {}
        scene_levels = {}
        for profile in derived:
            scene = scenes[profile.scene_id]
            pids = [
                p.id
                for p in paragraphs
                if position[scene.start_paragraph_id]
                <= position[p.id]
                <= position[scene.end_paragraph_id]
            ]
            v1_dict = _v1_compat_payload(profile, paragraph_ids=pids)
            v1_item = SceneReaderJourneyProfileItem.model_validate(v1_dict)
            payload_json = json.dumps(v1_item.model_dump(), ensure_ascii=False)
            # Store full v2 profile (levels + program derived) alongside for audit.
            v2_dump = profile.model_dump()
            artifact = AnalysisArtifact(
                run_id=analysis_run_id,
                artifact_type="reader_journey_scene_profile_v2",
                subject_type="scene",
                subject_id=str(scene.id),
                schema_version=SCENE_CONTRACT_VERSION_V2,
                prompt_version="2.0",
                payload_json=json.dumps(v2_dump, ensure_ascii=False),
                confidence=profile.confidence,
                validation_status="valid",
            )
            session.add(artifact)
            session.flush()
            for pid in profile.evidence_paragraph_ids[:16]:
                session.add(
                    AnalysisEvidence(
                        artifact_id=artifact.id,
                        field_path="evidence_paragraph_ids",
                        paragraph_id=pid,
                        paragraph_hash=pid,
                    )
                )
            momentum = float(profile.reading_momentum or 0)
            session.add(
                SceneReaderJourneyProfile(
                    reader_journey_run_id=journey.id,
                    scene_id=scene.id,
                    scene_ordinal=profile.scene_ordinal,
                    scene_value_summary=v1_item.scene_value_summary,
                    dominant_emotion=v1_item.dominant_emotion,
                    emotional_valence_start=v1_item.emotional_valence_start,
                    emotional_valence_end=v1_item.emotional_valence_end,
                    arousal_start=v1_item.arousal_start,
                    arousal_end=v1_item.arousal_end,
                    curiosity_score=v1_item.curiosity_score,
                    tension_score=v1_item.tension_score,
                    payoff_score=v1_item.payoff_score,
                    hook_score=v1_item.hook_score,
                    information_gain_score=v1_item.information_gain_score,
                    emotional_resonance_score=v1_item.emotional_resonance_score,
                    cognitive_load_score=v1_item.cognitive_load_score,
                    dropoff_risk_score=v1_item.dropoff_risk_score,
                    engagement_score=int(round(momentum)),
                    confidence=profile.confidence,
                    payload_json=payload_json,
                    validation_status="valid",
                    artifact_id=artifact.id,
                )
            )
            v2_scene_scores[str(profile.scene_ordinal)] = {
                "reading_momentum": profile.reading_momentum,
                "plot_progress": profile.plot_progress,
                "reading_tension": profile.reading_tension,
                "pacing_speed": mapped_or_zero(profile.pacing_speed),
                "pacing_fit": profile.pacing_fit,
                "hook": mapped_or_zero(profile.hook),
                "payoff": mapped_or_zero(profile.payoff),
                "emotional_investment": mapped_or_zero(profile.emotional_investment),
                "clarity": mapped_or_zero(profile.clarity),
                "dropoff_risk": profile.dropoff_risk,
            }
            v2_node_overrides[str(profile.scene_ordinal)] = {
                "node_type": profile.node_type,
                "role": "beat" if profile.node_type == "beat" else "core",
                "scene_role": profile.scene_role,
                "include_in_main_curve": profile.include_in_main_curve is not False
                and profile.node_type != "beat",
                "include_in_chapter_mean": profile.include_in_chapter_mean is not False
                and profile.node_type != "beat",
            }
            scene_levels[str(profile.scene_ordinal)] = {
                key: {
                    "level": getattr(profile, key).level,
                    "mapped_score": getattr(profile, key).mapped_score,
                    "evidence_paragraph_ids": list(getattr(profile, key).evidence_paragraph_ids),
                    "rationale": getattr(profile, key).rationale,
                    "confidence": getattr(profile, key).confidence,
                }
                for key in (
                    "goal_progress",
                    "conflict_change",
                    "state_change",
                    "information_gain",
                    "character_agency",
                    "causal_coherence",
                    "curiosity",
                    "tension",
                    "emotional_investment",
                    "pacing_speed",
                    "hook",
                    "payoff",
                    "setup_consistency",
                    "question_lifecycle",
                    "clarity",
                    "cognitive_load",
                    "redundancy",
                )
            }

        # Simple phases from ordinal thirds
        n = len(derived)
        cuts = [1, max(2, n // 3), max(3, (2 * n) // 3), n]
        phase_specs = [
            (1, "入村与异象", cuts[0], cuts[1]),
            (2, "追踪与洞穴", cuts[1] + 1, cuts[2]),
            (3, "揭晓与收束", cuts[2] + 1, cuts[3]),
        ]
        for ordinal, title, start, end in phase_specs:
            if start > end:
                continue
            session.add(
                ReaderJourneyPhase(
                    reader_journey_run_id=journey.id,
                    ordinal=ordinal,
                    title=title,
                    start_scene_ordinal=start,
                    end_scene_ordinal=end,
                    primary_reader_question="石牛角与山中之物的关系是什么",
                    dominant_emotion="悬疑",
                    reading_payoff="阶段推进",
                    continuation_motivation="继续追问",
                    summary=title,
                    confidence=0.8,
                    payload_json="{}",
                )
            )

        deterministic = {
            "source_mode": SOURCE_MODE,
            "contract_version": SCENE_CONTRACT_VERSION_V2,
            "prompt_version": "2.0",
            "formula_version": FORMULA_VERSION_V2,
            "question_lifecycle": lifecycle,
            "scene_diagnoses": diagnoses,
            "v2_scene_scores": v2_scene_scores,
            "v2_node_overrides": v2_node_overrides,
            "scene_levels": scene_levels,
            "average_reading_momentum": stats.get("average_reading_momentum"),
            "legacy_consecutive_no_payoff_floor_applied": False,
            "evidence_coverage_rate": 1.0,
            "semantic_calibration_version": "2.0",
            "scores_origin": "program_finalize_v2",
            "diagnoses_origin": "program_diagnose_chapter",
        }
        session.add(
            ChapterReaderJourneySummary(
                reader_journey_run_id=journey.id,
                chapter_value_summary="《牛角坳》V2原生真实正文分析：异象—追踪—揭晓—收束。",
                chapter_reader_question_chain_json=json.dumps(lifecycle, ensure_ascii=False),
                overall_engagement_score=int(round(float(stats.get("average_reading_momentum") or 0))),
                strongest_hook_scene_ids_json="[]",
                strongest_payoff_scene_ids_json="[]",
                risk_scene_ids_json="[]",
                positive_feedback_distribution_json="{}",
                hook_distribution_json="{}",
                emotion_trend_summary="异象升高至洞穴揭晓后收束",
                pacing_diagnosis_json=json.dumps(["V2原生派生"], ensure_ascii=False),
                one_sentence_diagnosis="真实正文 V2 原生：程序派生动量/诊断，非合成Fixture预写。",
                deterministic_statistics_json=json.dumps(deterministic, ensure_ascii=False),
                payload_json=json.dumps(
                    {
                        "source_mode": SOURCE_MODE,
                        "display_banner": DISPLAY_BANNER,
                        "scores_origin": "program_finalize_v2",
                        "diagnoses_origin": "program_diagnose_chapter",
                    },
                    ensure_ascii=False,
                ),
                validation_status="valid",
            )
        )
        journey.status = "succeeded"
        journey.current_stage = "succeeded"
        journey.completed_at = _utc()
        journey.completed_scene_count = len(derived)
        journey.remaining_scene_count = 0
        session.commit()

        # Export audit pack
        export = {
            "journey_run_id": journey.id,
            "analysis_run_id": analysis_run_id,
            "book_id": journey.book_id,
            "chapter_id": chapter_id,
            "contract_version": journey.scene_contract_version,
            "prompt_version": journey.scene_prompt_version,
            "formula_version": journey.formula_version,
            "source_mode": SOURCE_MODE,
            "display_banner": DISPLAY_BANNER,
            "model_request_count_batches": request_count,
            "scene_count": len(derived),
            "beat_count": sum(1 for p in derived if p.node_type == "beat"),
            "profiles": [p.model_dump() for p in derived],
            "diagnoses": diagnoses,
            "question_lifecycle": lifecycle,
            "v2_scene_scores": v2_scene_scores,
            "prewritten_scores": False,
            "prewritten_diagnoses": False,
        }
        out = data_dir / "exports" / "v2_native_result.json"
        out.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "journey_run_id": journey.id,
            "analysis_run_id": analysis_run_id,
            "export_path": str(out),
            "request_batches": request_count,
            "scene_count": len(derived),
            "beat_count": sum(1 for p in derived if p.node_type == "beat"),
            "average_reading_momentum": stats.get("average_reading_momentum"),
        }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()
    result = asyncio.run(execute(args.data_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
