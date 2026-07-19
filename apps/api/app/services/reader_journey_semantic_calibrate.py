"""Deterministic Reader Journey semantic calibration (zero HTTP).

Fixes carry-in questions, hook structure, consecutive no-payoff risks,
journey node roles, and chapter diagnosis phrasing without model calls.
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ChapterReaderJourneySummary,
    ReaderJourneyPhase,
    ReaderJourneyRun,
    Scene,
    SceneReaderJourneyProfile,
)
from app.schemas.reader_journey import (
    CHAPTER_CONTRACT_VERSION,
    ReaderQuestionIn,
    RiskPoint,
    SCENE_CONTRACT_VERSION,
    SCENE_PROMPT_VERSION,
    SceneReaderJourneyProfileItem,
)
from app.services.reader_journey_engagement import compute_engagement
from app.services.reader_journey_progress import load_revision_scenes, sync_journey_run_counts
from app.services.reader_journey_question_lifecycle import build_question_chains
from app.services.reader_journey_statistics import compute_deterministic_statistics

ACTIVE_OUT_STRENGTH = 40
CONSECUTIVE_NO_PAYOFF_THRESHOLD = 2
BEAT_PARAGRAPH_THRESHOLD = 3
SECONDARY_PARAGRAPH_THRESHOLD = 5

CHAPTER_BANNED_PHRASES = (
    "层层剥开",
    "推向高潮",
    "成功确立",
    "悬念迭起",
    "引人入胜",
    "扣人心弦",
    "步步紧逼",
    "高潮迭起",
    "层层递进",
    "逐步揭示",
)


def paragraph_count_for_scene(scene: Scene) -> int:
    start = int(scene.start_paragraph_id.rsplit("-P", 1)[-1])
    end = int(scene.end_paragraph_id.rsplit("-P", 1)[-1])
    return max(1, end - start + 1)


def journey_node_role(paragraph_count: int) -> str:
    if paragraph_count <= BEAT_PARAGRAPH_THRESHOLD:
        return "beat"
    if paragraph_count <= SECONDARY_PARAGRAPH_THRESHOLD:
        return "secondary"
    return "primary"


def active_outbound_questions(profile: SceneReaderJourneyProfileItem) -> list[str]:
    """Questions that should carry into the next scene."""
    fully_answered = {
        item.question.strip()
        for item in profile.reader_question_answered
        if item.answer_degree == "full"
    }
    ordered: list[tuple[int, str]] = []
    for out in profile.reader_question_out:
        question = out.question.strip()
        if not question or question in fully_answered:
            continue
        if out.strength < ACTIVE_OUT_STRENGTH:
            continue
        ordered.append((out.strength, question))
    ordered.sort(key=lambda item: (-item[0], item[1]))
    questions = [question for _strength, question in ordered[:2]]
    if questions:
        return questions
    for created in profile.reader_question_created:
        question = created.question.strip()
        if question and question not in fully_answered:
            questions.append(question)
        if len(questions) >= 2:
            break
    return questions


def build_carried_question_in(
    prior: SceneReaderJourneyProfileItem,
) -> list[ReaderQuestionIn]:
    result: list[ReaderQuestionIn] = []
    for question in active_outbound_questions(prior):
        strength = next(
            (
                item.strength
                for item in prior.reader_question_out
                if item.question.strip() == question
            ),
            55,
        )
        result.append(
            ReaderQuestionIn(
                question=question[:160],
                source="carried_from_previous",
                confidence=round(min(1.0, max(0.35, strength / 100.0)), 2),
            )
        )
    return result


def apply_deterministic_qin(
    profiles: list[SceneReaderJourneyProfileItem],
) -> list[SceneReaderJourneyProfileItem]:
    """Overwrite Scene 2+ q_in from prior active outs (deterministic)."""
    ordered = sorted(profiles, key=lambda item: item.scene_ordinal)
    calibrated: list[SceneReaderJourneyProfileItem] = []
    for index, profile in enumerate(ordered):
        data = profile.model_dump()
        if profile.scene_ordinal > 1 and index > 0:
            data["reader_question_in"] = [
                item.model_dump() for item in build_carried_question_in(ordered[index - 1])
            ]
        calibrated.append(SceneReaderJourneyProfileItem.model_validate(data))
    return calibrated


def _clip(text: str, limit: int = 80) -> str:
    text = re.sub(r"\s+", "", text.strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def enrich_hook_structure(
    profile: SceneReaderJourneyProfileItem,
    *,
    next_profile: SceneReaderJourneyProfileItem | None,
) -> SceneReaderJourneyProfileItem:
    known_seed = profile.scene_value_summary.strip() or "本场已给出的可读信息"
    gap_seed = (
        profile.reader_question_out[0].question.strip()
        if profile.reader_question_out
        else (
            profile.reader_question_created[0].question.strip()
            if profile.reader_question_created
            else "未闭合的读者疑问"
        )
    )
    continue_seed = f"读者需要弄清：{gap_seed}" if gap_seed else "读者仍缺关键信息，需继续跟踪"
    handoff_seed = (
        next_profile.scene_value_summary.strip()
        if next_profile is not None
        else "下一场需承接本场未决问题"
    )
    hooks: list[dict[str, Any]] = []
    for hook in profile.hooks:
        data = hook.model_dump()
        if not data.get("known"):
            data["known"] = _clip(known_seed)
        if not data.get("gap"):
            data["gap"] = _clip(gap_seed)
        if not data.get("continue_drive"):
            data["continue_drive"] = _clip(continue_seed)
        if not data.get("next_handoff"):
            data["next_handoff"] = _clip(handoff_seed or "进入下一场核验")
        if len(data["summary"].strip()) < 8:
            data["summary"] = _clip(f"{data['known']}→缺口：{data['gap']}", 160)
        hooks.append(data)
    payload = profile.model_dump()
    payload["hooks"] = hooks
    return SceneReaderJourneyProfileItem.model_validate(payload)


def inject_consecutive_no_payoff_risks(
    profiles: list[SceneReaderJourneyProfileItem],
) -> list[SceneReaderJourneyProfileItem]:
    ordered = sorted(profiles, key=lambda item: item.scene_ordinal)
    no_payoff_flags = [
        (not profile.payoffs) or profile.payoff_score < 30 for profile in ordered
    ]
    calibrated: list[SceneReaderJourneyProfileItem] = []
    for index, profile in enumerate(ordered):
        data = profile.model_dump()
        run_len = 1
        if no_payoff_flags[index]:
            left = index - 1
            while left >= 0 and no_payoff_flags[left]:
                run_len += 1
                left -= 1
            right = index + 1
            while right < len(ordered) and no_payoff_flags[right]:
                run_len += 1
                right += 1
        if run_len >= CONSECUTIVE_NO_PAYOFF_THRESHOLD and no_payoff_flags[index]:
            risks = list(data.get("risk_points") or [])
            already = any(
                item.get("type") in {"low_payoff", "consecutive_no_payoff"} for item in risks
            )
            if not already:
                evidence = list(profile.evidence_paragraph_ids[:2])
                if not evidence and profile.hooks:
                    evidence = list(profile.hooks[0].evidence_paragraph_ids[:2])
                risks.append(
                    RiskPoint(
                        type="consecutive_no_payoff",
                        summary=_clip(
                            f"连续{run_len}个Scene缺少有效payoff，阅读兑现中断，需诊断牵引空窗",
                            160,
                        ),
                        severity=min(95, 40 + run_len * 15),
                        evidence_paragraph_ids=evidence,
                    ).model_dump()
                )
                data["risk_points"] = risks[:2]
                data["dropoff_risk_score"] = max(int(data.get("dropoff_risk_score") or 0), 55)
        calibrated.append(SceneReaderJourneyProfileItem.model_validate(data))
    return calibrated


def build_journey_nodes(
    scenes: list[Scene],
    profiles: list[SceneReaderJourneyProfileItem],
) -> list[dict[str, Any]]:
    by_ordinal = {item.scene_ordinal: item for item in profiles}
    nodes: list[dict[str, Any]] = []
    for scene in sorted(scenes, key=lambda item: item.ordinal):
        count = paragraph_count_for_scene(scene)
        role = journey_node_role(count)
        profile = by_ordinal.get(scene.ordinal)
        nodes.append(
            {
                "scene_id": scene.id,
                "scene_ordinal": scene.ordinal,
                "paragraph_count": count,
                "role": role,
                "label": f"Scene {scene.ordinal}",
                "primary_question": (
                    profile.reader_question_out[0].question
                    if profile and profile.reader_question_out
                    else (
                        profile.reader_question_in[0].question
                        if profile and profile.reader_question_in
                        else ""
                    )
                ),
                "engagement_hint": profile.hook_score if profile else None,
            }
        )
    return nodes


def contains_banned_chapter_phrase(text: str) -> bool:
    return any(phrase in text for phrase in CHAPTER_BANNED_PHRASES)


def build_deterministic_chapter_diagnosis(
    profiles: list[SceneReaderJourneyProfileItem],
    *,
    journey_nodes: list[dict[str, Any]],
    question_chains: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered = sorted(profiles, key=lambda item: item.scene_ordinal)
    chains = question_chains or build_question_chains(ordered)
    top_chain = chains[0]["question_summary"] if chains else "核心读者问题未形成稳定链"
    weak_beats = [
        node["scene_ordinal"]
        for node in journey_nodes
        if node["role"] in {"beat", "secondary"}
    ]
    low_payoff_ordinals = [
        profile.scene_ordinal
        for profile in ordered
        if (not profile.payoffs) or profile.payoff_score < 30
    ]
    consecutive = 0
    best_span = 0
    span_start = None
    best_start = None
    max_ordinal = ordered[-1].scene_ordinal if ordered else 0
    for ordinal in range(1, max_ordinal + 1):
        if ordinal in low_payoff_ordinals:
            if consecutive == 0:
                span_start = ordinal
            consecutive += 1
            if consecutive > best_span:
                best_span = consecutive
                best_start = span_start
        else:
            consecutive = 0
    weak_interval = (
        f"Scene {best_start}—{best_start + best_span - 1}"
        if best_start is not None and best_span >= 2
        else ("无连续空窗" if not low_payoff_ordinals else f"Scene {low_payoff_ordinals[0]}")
    )
    traction = top_chain[:80]
    beat_note = (
        f"短Scene {','.join(str(item) for item in weak_beats[:6])} 作为Beat/次级节点，不单独承担主阶段转折"
        if weak_beats
        else "各Scene长度较均衡"
    )
    diagnosis = (
        f"主牵引是「{traction}」的跨Scene承接；薄弱区间在{weak_interval}（连续低payoff）；"
        f"{beat_note}。"
    )[:240]
    pacing = [
        f"开场至中前：主问题「{traction}」建立，短场以Beat推进信息密度。",
        f"薄弱区间{weak_interval}：缺少目标/信息/身份/规则/情绪/恐怖兑现或阶段完成类payoff，应优先补诊断风险。",
        "后段需用明确问题链闭合或部分兑现，避免空泛高潮措辞。",
    ]
    strengths = [
        f"问题链条目数 {len(chains)}，可追踪跨Scene承接",
        f"强钩子Scene：{[p.scene_ordinal for p in ordered if p.hook_score >= 70][:5]}",
    ]
    risks = [
        f"连续低payoff区间：{weak_interval}",
        "禁止用泛化高潮措辞替代机制说明",
    ]
    chain_texts = [item["question_summary"] for item in chains[:8]] or [traction]
    return {
        "one_sentence_diagnosis": diagnosis,
        "pacing_diagnosis": pacing,
        "chapter_strengths": strengths,
        "chapter_risks": risks,
        "chapter_reader_question_chain": chain_texts,
    }


def calibrate_profile_list(
    profiles: list[SceneReaderJourneyProfileItem],
    scenes: list[Scene],
) -> tuple[list[SceneReaderJourneyProfileItem], dict[str, Any]]:
    with_qin = apply_deterministic_qin(profiles)
    ordered = sorted(with_qin, key=lambda item: item.scene_ordinal)
    structured: list[SceneReaderJourneyProfileItem] = []
    for index, profile in enumerate(ordered):
        nxt = ordered[index + 1] if index + 1 < len(ordered) else None
        structured.append(enrich_hook_structure(profile, next_profile=nxt))
    with_risks = inject_consecutive_no_payoff_risks(structured)
    nodes = build_journey_nodes(scenes, with_risks)
    chains = build_question_chains(with_risks)
    chapter = build_deterministic_chapter_diagnosis(
        with_risks,
        journey_nodes=nodes,
        question_chains=chains,
    )
    meta = {
        "journey_nodes": nodes,
        "question_chains": chains,
        "chapter_diagnosis": chapter,
        "empty_qin_count": sum(1 for item in with_risks if not item.reader_question_in),
        "non_opening_empty_qin": sum(
            1 for item in with_risks if item.scene_ordinal > 1 and not item.reader_question_in
        ),
        "scene_contract_version": SCENE_CONTRACT_VERSION,
    }
    return with_risks, meta


def semantic_recalibrate_journey_run(
    session: Session,
    journey_run_id: int,
) -> dict[str, Any]:
    journey_run = session.get(ReaderJourneyRun, journey_run_id)
    if journey_run is None:
        raise ValueError("READER_JOURNEY_RUN_NOT_FOUND")
    _revision, scenes = load_revision_scenes(session, journey_run.analysis_run_id)
    if not scenes:
        raise ValueError("NO_SCENES")
    rows = list(
        session.scalars(
            select(SceneReaderJourneyProfile)
            .where(SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id)
            .order_by(SceneReaderJourneyProfile.scene_ordinal)
        )
    )
    if len(rows) != len(scenes):
        raise ValueError("SCENE_PROFILES_INCOMPLETE")

    profiles = [
        SceneReaderJourneyProfileItem.model_validate_json(row.payload_json) for row in rows
    ]
    empty_qin_before = sum(1 for item in profiles if not item.reader_question_in)
    calibrated, meta = calibrate_profile_list(profiles, scenes)
    meta["empty_qin_before"] = empty_qin_before
    by_ordinal = {item.scene_ordinal: item for item in calibrated}
    genre = journey_run.genre or "suspense"

    for row in rows:
        item = by_ordinal[row.scene_ordinal]
        engagement = compute_engagement(item, genre=genre)
        row.payload_json = item.model_dump_json()
        row.scene_value_summary = item.scene_value_summary
        row.curiosity_score = item.curiosity_score
        row.tension_score = item.tension_score
        row.payoff_score = item.payoff_score
        row.hook_score = item.hook_score
        row.information_gain_score = item.information_gain_score
        row.emotional_resonance_score = item.emotional_resonance_score
        row.cognitive_load_score = item.cognitive_load_score
        row.dropoff_risk_score = item.dropoff_risk_score
        row.emotional_valence_start = item.emotional_valence_start
        row.emotional_valence_end = item.emotional_valence_end
        row.arousal_start = item.arousal_start
        row.arousal_end = item.arousal_end
        row.engagement_score = engagement.engagement_score
        row.engagement_breakdown_json = engagement.model_dump_json()
        row.validation_status = "valid"

    phase_n = int(
        session.scalar(
            select(func.count())
            .select_from(ReaderJourneyPhase)
            .where(ReaderJourneyPhase.reader_journey_run_id == journey_run.id)
        )
        or 0
    )
    stats = compute_deterministic_statistics(scenes, rows, phase_count=phase_n)
    stats["journey_nodes"] = meta["journey_nodes"]
    stats["semantic_calibration_version"] = SCENE_CONTRACT_VERSION
    stats["question_chains"] = meta["question_chains"]

    chapter = meta["chapter_diagnosis"]
    summary = session.scalar(
        select(ChapterReaderJourneySummary).where(
            ChapterReaderJourneySummary.reader_journey_run_id == journey_run.id
        )
    )
    if summary is not None:
        try:
            payload = json.loads(summary.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        must_rewrite = (
            empty_qin_before >= max(2, len(calibrated) - 1)
            or contains_banned_chapter_phrase(summary.one_sentence_diagnosis or "")
            or contains_banned_chapter_phrase(
                json.dumps(payload.get("pacing_diagnosis") or [], ensure_ascii=False)
            )
        )
        if must_rewrite:
            summary.one_sentence_diagnosis = chapter["one_sentence_diagnosis"]
            summary.pacing_diagnosis_json = json.dumps(
                chapter["pacing_diagnosis"], ensure_ascii=False
            )
            summary.chapter_value_summary = chapter["one_sentence_diagnosis"]
            summary.chapter_reader_question_chain_json = json.dumps(
                chapter["chapter_reader_question_chain"], ensure_ascii=False
            )
            payload.update(
                {
                    "one_sentence_diagnosis": chapter["one_sentence_diagnosis"],
                    "pacing_diagnosis": chapter["pacing_diagnosis"],
                    "chapter_strengths": chapter["chapter_strengths"],
                    "chapter_risks": chapter["chapter_risks"],
                    "chapter_reader_question_chain": chapter["chapter_reader_question_chain"],
                    "contract_version": CHAPTER_CONTRACT_VERSION,
                }
            )
            summary.payload_json = json.dumps(payload, ensure_ascii=False)
        else:
            summary.chapter_reader_question_chain_json = json.dumps(
                chapter["chapter_reader_question_chain"], ensure_ascii=False
            )
        summary.deterministic_statistics_json = json.dumps(stats, ensure_ascii=False)
        summary.risk_scene_ids_json = json.dumps(
            stats.get("risk_scene_ids", []), ensure_ascii=False
        )
        summary.strongest_hook_scene_ids_json = json.dumps(
            stats.get("strong_hook_scene_ids", []), ensure_ascii=False
        )

    journey_run.scene_contract_version = SCENE_CONTRACT_VERSION
    journey_run.scene_prompt_version = SCENE_PROMPT_VERSION
    details: dict[str, Any] = {}
    try:
        details = json.loads(journey_run.failure_details_json or "{}")
    except json.JSONDecodeError:
        details = {}
    audits = details.get("semantic_calibration_audit")
    audit_list = audits if isinstance(audits, list) else ([audits] if audits else [])
    audit_list.append(
        {
            "to_contract_version": SCENE_CONTRACT_VERSION,
            "empty_qin_before": empty_qin_before,
            "non_opening_empty_qin_after": meta["non_opening_empty_qin"],
            "journey_node_count": len(meta["journey_nodes"]),
            "http_requests": 0,
            "tokens": 0,
            "cost": 0.0,
        }
    )
    details["semantic_calibration_audit"] = audit_list
    journey_run.failure_details_json = json.dumps(details, ensure_ascii=False)
    sync_journey_run_counts(session, journey_run)
    session.commit()

    return {
        "journey_run_id": journey_run_id,
        "calibrated_profile_count": len(calibrated),
        "empty_qin_remaining": meta["non_opening_empty_qin"],
        "journey_nodes": meta["journey_nodes"],
        "question_chain_count": len(meta["question_chains"]),
        "one_sentence_diagnosis": chapter["one_sentence_diagnosis"],
        "scene_contract_version": SCENE_CONTRACT_VERSION,
        "http_requests": 0,
        "tokens": 0,
        "cost": 0.0,
    }
