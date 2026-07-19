"""Output-capacity-aware batch planning for Reader Journey scene profiles."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.core.config import get_settings
from app.db.models import Paragraph, Scene
from app.services.transition_batch_planner import conservative_token_estimate

PLANNER_VERSION = "1.1"
DEFAULT_MAX_SCENES_PER_BATCH = 2
LONG_SCENE_CHAR_THRESHOLD = 1800
SHORT_SCENE_CHAR_THRESHOLD = 400
LONG_SCENE_PARAGRAPH_THRESHOLD = 12
OUTPUT_BUDGET_RATIO = 0.72


@dataclass(frozen=True)
class SceneOutputEstimate:
    scene_id: int
    scene_ordinal: int
    body_chars: int
    analysis_chars: int
    paragraph_count: int
    estimated_profile_tokens: int


@dataclass(frozen=True)
class ReaderJourneySceneBatch:
    batch_index: int
    scenes: list[Scene]
    scene_ids: list[int]
    scene_ordinals: list[int]
    estimated_output_tokens: int
    planner_version: str = PLANNER_VERSION
    batch_count: int = 0
    split_from_truncation: bool = False
    audit_type: str | None = None

    def with_index(self, batch_index: int, batch_count: int) -> ReaderJourneySceneBatch:
        return ReaderJourneySceneBatch(
            batch_index=batch_index,
            scenes=self.scenes,
            scene_ids=self.scene_ids,
            scene_ordinals=self.scene_ordinals,
            estimated_output_tokens=self.estimated_output_tokens,
            planner_version=self.planner_version,
            batch_count=batch_count,
            split_from_truncation=self.split_from_truncation,
            audit_type=self.audit_type,
        )


def output_token_budget(*, output_limit: int | None = None) -> int:
    settings = get_settings()
    limit = output_limit if output_limit is not None else settings.cloud_output_reader_journey_scene
    return max(1, math.floor(limit * OUTPUT_BUDGET_RATIO))


def _worst_case_profile_payload(
    *,
    scene_id: int,
    scene_ordinal: int,
    evidence_ids: list[str],
) -> dict[str, object]:
    """Conservative upper-bound JSON for one Scene profile (respects schema caps)."""
    evidence = evidence_ids[:3] or [f"P{scene_ordinal:04d}"]
    question = "读者进入本场景时最关心的核心未解问题"
    return {
        "scene_id": scene_id,
        "scene_ordinal": scene_ordinal,
        "scene_value_summary": "本场景通过可验证细节建立阅读牵引并推动问题链前进" * 2,
        "reader_question_in": [
            {"question": question, "source": "created_in_scene", "confidence": 1.0},
            {"question": question + "续", "source": "carried_from_previous", "confidence": 1.0},
        ],
        "reader_question_answered": [
            {
                "question": question,
                "answer_summary": "给出部分可验证线索但未完全闭合",
                "answer_degree": "partial",
                "evidence_paragraph_ids": evidence[:2],
            },
            {
                "question": question + "续",
                "answer_summary": "确认先前猜测中的关键事实",
                "answer_degree": "full",
                "evidence_paragraph_ids": evidence[:2],
            },
        ],
        "reader_question_out": [
            {"question": "身份与动机是否一致", "hook_type": "identity", "strength": 100},
            {"question": "危险是否会立即兑现", "hook_type": "danger", "strength": 100},
        ],
        "dominant_emotion": "好奇与紧张交织",
        "emotional_valence_start": -100,
        "emotional_valence_end": 100,
        "arousal_start": 100,
        "arousal_end": 100,
        "curiosity_score": 100,
        "tension_score": 100,
        "payoff_score": 100,
        "hook_score": 100,
        "information_gain_score": 100,
        "emotional_resonance_score": 100,
        "cognitive_load_score": 100,
        "dropoff_risk_score": 100,
        "payoffs": [
            {
                "type": "information",
                "summary": "提供可验证的新信息并改变读者判断",
                "strength": 100,
                "evidence_paragraph_ids": evidence[:2],
            },
            {
                "type": "emotion",
                "summary": "情绪兑现形成阶段性正反馈",
                "strength": 100,
                "evidence_paragraph_ids": evidence[:2],
            },
        ],
        "hooks": [
            {
                "type": "identity",
                "summary": "留下未闭合的身份疑问驱动续读",
                "strength": 100,
                "evidence_paragraph_ids": evidence[:2],
            },
            {
                "type": "information",
                "summary": "信息缺口迫使读者追问下一场景",
                "strength": 100,
                "evidence_paragraph_ids": evidence[:2],
            },
        ],
        "techniques": [
            {
                "code": "contrast_reveal",
                "name": "反差揭示",
                "mechanism": "先给出日常表象再露出异常细节迫使读者比对",
                "reader_effect": "让读者主动比对前后信息并提高警惕",
                "transfer_formula": "日常动作加一处不合常理的细节形成对照",
                "risk": "细节过弱则像笔误而不是机制",
                "evidence_paragraph_ids": evidence[:2],
            },
            {
                "code": "delayed_payoff",
                "name": "延宕兑现",
                "mechanism": "先承诺后延宕，维持悬念张力直至关键节点",
                "reader_effect": "提高续读动机",
                "transfer_formula": "先抛问题再延迟给出答案",
                "risk": "延宕过长会削弱信任",
                "evidence_paragraph_ids": evidence[:2],
            },
            {
                "code": "misdirection",
                "name": "误导分流",
                "mechanism": "用看似合理的假线索分流注意力",
                "reader_effect": "制造认知落差",
                "transfer_formula": "真假线索并行出现",
                "risk": "误导过强会引发被欺骗感",
                "evidence_paragraph_ids": evidence[:2],
            },
        ],
        "risk_points": [
            {
                "type": "weak_hook",
                "summary": "若后续不承接疑问牵引会衰减",
                "severity": 100,
                "evidence_paragraph_ids": evidence[:2],
            },
            {
                "type": "high_cognitive_load",
                "summary": "信息密度过高可能造成阅读疲劳",
                "severity": 100,
                "evidence_paragraph_ids": evidence[:2],
            },
        ],
        "emotion_beats": [
            {
                "label": "疑惑",
                "valence": -50,
                "arousal": 60,
                "evidence_paragraph_ids": evidence[:1],
            }
        ],
        "information_changes": [
            {
                "type": "new_information",
                "summary": "引入新的可观察事实改变局面判断",
                "certainty": "fact",
                "evidence_paragraph_ids": evidence[:2],
            },
            {
                "type": "foreshadowing",
                "summary": "埋下后续可回收的伏笔线索",
                "certainty": "supported_inference",
                "evidence_paragraph_ids": evidence[:2],
            },
            {
                "type": "misdirection",
                "summary": "制造看似合理的错误方向",
                "certainty": "speculation",
                "evidence_paragraph_ids": evidence[:2],
            },
        ],
        "character_effects": [
            {
                "character_name": "主角",
                "trait_or_change": "行动选择与此前印象形成对照",
                "method": "action",
                "evidence_paragraph_ids": evidence[:2],
            },
            {
                "character_name": "对手",
                "trait_or_change": "态度变化暴露隐藏动机",
                "method": "dialogue",
                "evidence_paragraph_ids": evidence[:2],
            },
        ],
        "writing_takeaways": [
            {
                "summary": "用可验证细节承载悬念而不是空泛气氛",
                "applicable_when": "悬疑开场需要建立牵引",
                "avoid_when": "需要快速交代世界观时",
            },
            {
                "summary": "问题链进出要有明确证据支撑",
                "applicable_when": "章内连续场景推进",
                "avoid_when": "纯动作场面",
            },
        ],
        "confidence": 1.0,
        "evidence_paragraph_ids": evidence,
    }


def estimate_scene_profile_tokens(
    scene: Scene,
    *,
    paragraphs: list[Paragraph] | None = None,
    position: dict[str, int] | None = None,
    analysis_payload: dict[str, object] | None = None,
) -> SceneOutputEstimate:
    body_chars = 0
    paragraph_count = 0
    evidence_ids: list[str] = []
    if paragraphs is not None and position is not None:
        start = position[scene.start_paragraph_id]
        end = position[scene.end_paragraph_id]
        included = paragraphs[start : end + 1]
        paragraph_count = len(included)
        body_chars = sum(len(item.normalized_text or item.raw_text or "") for item in included)
        evidence_ids = [item.id for item in included[:4]]
    analysis_chars = 0
    if analysis_payload:
        analysis_chars = len(str(analysis_payload))
    # Output estimate is dominated by the profile JSON, not the input body.
    # Body/analysis length still influences whether the scene is "long" for packing.
    profile_tokens = conservative_token_estimate(
        _worst_case_profile_payload(
            scene_id=int(scene.id),
            scene_ordinal=int(scene.ordinal),
            evidence_ids=evidence_ids,
        )
    )
    # conservative_token_estimate treats CJK as 1 token/char; real model tokenization
    # for capped literary JSON is typically closer to ~0.5 of that upper bound.
    # Keep two normal profiles under ~72% of the 2000-token output limit.
    profile_tokens = max(1, math.ceil(profile_tokens * 0.5))
    # Longer scenes tend to produce denser evidence lists and slightly longer prose.
    density_bonus = min(60, paragraph_count * 2 + body_chars // 150 + analysis_chars // 400)
    return SceneOutputEstimate(
        scene_id=int(scene.id),
        scene_ordinal=int(scene.ordinal),
        body_chars=body_chars,
        analysis_chars=analysis_chars,
        paragraph_count=paragraph_count,
        estimated_profile_tokens=profile_tokens + density_bonus,
    )


def estimate_batch_output_tokens(estimates: list[SceneOutputEstimate]) -> int:
    wrapper_overhead = 24
    return wrapper_overhead + sum(item.estimated_profile_tokens for item in estimates)


def _is_long_scene(estimate: SceneOutputEstimate) -> bool:
    return (
        estimate.body_chars >= LONG_SCENE_CHAR_THRESHOLD
        or estimate.paragraph_count >= LONG_SCENE_PARAGRAPH_THRESHOLD
        or estimate.estimated_profile_tokens >= output_token_budget() * 0.62
    )


def _is_short_scene(estimate: SceneOutputEstimate) -> bool:
    return (
        estimate.body_chars <= SHORT_SCENE_CHAR_THRESHOLD
        and estimate.paragraph_count <= 3
        and not _is_long_scene(estimate)
    )


def split_batch_after_truncation(
    batch: ReaderJourneySceneBatch,
) -> tuple[ReaderJourneySceneBatch, ReaderJourneySceneBatch]:
    """Deterministically split a multi-scene batch into left/right halves."""
    if len(batch.scenes) < 2:
        raise ValueError("cannot split a single-scene batch")
    mid = len(batch.scenes) // 2
    left_scenes = batch.scenes[:mid]
    right_scenes = batch.scenes[mid:]
    left = ReaderJourneySceneBatch(
        batch_index=batch.batch_index,
        scenes=left_scenes,
        scene_ids=[item.id for item in left_scenes],
        scene_ordinals=[item.ordinal for item in left_scenes],
        estimated_output_tokens=max(1, batch.estimated_output_tokens // 2),
        planner_version=batch.planner_version,
        batch_count=batch.batch_count,
        split_from_truncation=True,
        audit_type="batch_split_after_truncation",
    )
    right = ReaderJourneySceneBatch(
        batch_index=batch.batch_index,
        scenes=right_scenes,
        scene_ids=[item.id for item in right_scenes],
        scene_ordinals=[item.ordinal for item in right_scenes],
        estimated_output_tokens=max(1, batch.estimated_output_tokens - left.estimated_output_tokens),
        planner_version=batch.planner_version,
        batch_count=batch.batch_count,
        split_from_truncation=True,
        audit_type="batch_split_after_truncation",
    )
    return left, right


def worst_case_requests_for_batches(batches: list[ReaderJourneySceneBatch]) -> int:
    """Normal batches + binary split to singles + one repair per final unit."""
    total = 0
    for batch in batches:
        size = max(1, len(batch.scenes))
        # Binary split tree: size-1 failed internals + size leaf attempts + size repairs.
        total += (2 * size - 1) + size
    return total


def plan_scene_batches(
    scenes: list[Scene],
    *,
    batch_size: int | None = None,
    completed_scene_ids: set[int] | None = None,
    paragraphs: list[Paragraph] | None = None,
    analysis_by_scene_id: dict[int, dict[str, object]] | None = None,
    output_limit: int | None = None,
) -> list[ReaderJourneySceneBatch]:
    """Plan batches with output-capacity awareness.

    Defaults: at most 2 scenes per batch; long scenes alone; never 4 full profiles.
    """
    settings = get_settings()
    max_per_batch = batch_size if batch_size is not None else settings.reader_journey_batch_size
    max_per_batch = max(1, min(DEFAULT_MAX_SCENES_PER_BATCH, max_per_batch))
    budget = output_token_budget(output_limit=output_limit)
    done = completed_scene_ids or set()
    pending = [scene for scene in scenes if scene.id not in done]
    if not pending:
        return []

    position: dict[str, int] | None = None
    if paragraphs is not None:
        position = {item.id: index for index, item in enumerate(paragraphs)}

    estimates = [
        estimate_scene_profile_tokens(
            scene,
            paragraphs=paragraphs,
            position=position,
            analysis_payload=(analysis_by_scene_id or {}).get(int(scene.id)),
        )
        for scene in pending
    ]

    raw_batches: list[tuple[list[Scene], list[SceneOutputEstimate]]] = []
    index = 0
    while index < len(pending):
        scene = pending[index]
        estimate = estimates[index]
        if _is_long_scene(estimate) or estimate.estimated_profile_tokens > budget:
            raw_batches.append(([scene], [estimate]))
            index += 1
            continue

        chunk_scenes = [scene]
        chunk_estimates = [estimate]
        index += 1
        while index < len(pending) and len(chunk_scenes) < max_per_batch:
            nxt = pending[index]
            nxt_est = estimates[index]
            if _is_long_scene(nxt_est):
                break
            candidate_estimates = chunk_estimates + [nxt_est]
            if estimate_batch_output_tokens(candidate_estimates) > budget:
                break
            chunk_scenes.append(nxt)
            chunk_estimates.append(nxt_est)
            index += 1
        raw_batches.append((chunk_scenes, chunk_estimates))

    batch_count = len(raw_batches)
    batches: list[ReaderJourneySceneBatch] = []
    for batch_index, (chunk_scenes, chunk_estimates) in enumerate(raw_batches, start=1):
        batches.append(
            ReaderJourneySceneBatch(
                batch_index=batch_index,
                scenes=chunk_scenes,
                scene_ids=[item.id for item in chunk_scenes],
                scene_ordinals=[item.ordinal for item in chunk_scenes],
                estimated_output_tokens=estimate_batch_output_tokens(chunk_estimates),
                planner_version=PLANNER_VERSION,
                batch_count=batch_count,
            )
        )
    return batches


def format_batch_plan_report(batches: list[ReaderJourneySceneBatch]) -> list[str]:
    lines: list[str] = []
    for batch in batches:
        ordinals = batch.scene_ordinals
        if len(ordinals) == 1:
            lines.append(f"Scene {ordinals[0]}单独")
        else:
            lines.append(f"Scene {ordinals[0]}–{ordinals[-1]}")
    return lines
