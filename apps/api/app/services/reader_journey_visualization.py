"""Deterministic Reader Journey visualization aggregates — zero model/HTTP calls."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisEvidence,
    Chapter,
    ChapterReaderJourneySummary,
    ReaderJourneyPhase,
    ReaderJourneyRun,
    Scene,
    SceneReaderJourneyProfile,
)
from app.schemas.reader_journey import SceneReaderJourneyProfileItem
from app.narrative_core.long_novel.chapter_focus import (
    hook_vocabulary_for_book,
    main_curve_naming_for_book,
)
from app.services.reader_journey_dimension_insights import attach_dimension_insights_to_node
from app.services.reader_journey_comprehensive_presentation import (
    attach_comprehensive_reading_presentation,
)
from app.services.reader_journey_engagement import compute_engagement, load_formula_config
from app.services.reader_journey_progress import load_revision_scenes
from app.services.narrative_loop_view import build_narrative_loop_bundle
from app.services.reader_journey_question_lifecycle import (
    build_question_chains,
    diagnose_dropped_high_strength_questions,
)
from app.services.reader_journey_semantic_calibrate import paragraph_count_for_scene
from app.services.reader_journey_visual_calibration import (
    CLUSTER_FORMULA_VERSION,
    HOOK_SELECT_FORMULA_VERSION,
    IMPORTANCE_FORMULA_VERSION,
    PAYOFF_DERIVE_FORMULA_VERSION,
    VISUALIZATION_VERSION,
    build_density_warnings,
    build_question_clusters,
    classify_scene_levels,
    derive_and_select_payoffs,
    select_visible_hooks,
)

CHAIN_RANK_FORMULA_VERSION = "1.0"
CHAIN_MERGE_FORMULA_VERSION = "1.0"

WEAK_WORDS = "究竟到底真实具体是否什么为何为什么怎么如何的了吗呢啊吧"
WEAK_WORD_RE = re.compile(
    f"[{re.escape(WEAK_WORDS)}\\s，,。！？；;：:\"'（）()\\[\\]【】]+"
)
ENTITY_RE = re.compile(r"[\u4e00-\u9fff]{2,4}")
ENTITY_STOP = frozenset(
    {
        "什么",
        "为何",
        "怎么",
        "如何",
        "到底",
        "究竟",
        "是否",
        "真实",
        "具体",
        "这个",
        "那个",
        "他们",
        "她们",
        "我们",
        "你们",
        "自己",
        "已经",
        "可以",
        "不能",
        "没有",
        "是不是",
        "为什么",
    }
)

QUESTION_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("identity", re.compile(r"身份|是谁|谁|真面目|真实身份|伪装")),
    ("danger", re.compile(r"危险|威胁|杀|死|害|逃|袭击|恐怖|凶手")),
    ("rule", re.compile(r"规则|法则|禁忌|限制|代价|机制|条件")),
    ("goal", re.compile(r"目标|目的|计划|想要|能否|能不能|会不会|要不要")),
    ("relationship", re.compile(r"关系|爱|恨|信任|背叛|联手|对立|感情")),
    ("information", re.compile(r"信息|知道|秘密|真相|发现|线索|证据|原因")),
    ("space", re.compile(r"空间|地方|门|房间|通道|边界|入口|出口|阈值")),
]

ROLE_ORDER = {"beat": 0, "secondary": 1, "core": 2}
ROLE_THRESHOLDS = {"core": 55.0, "secondary": 35.0}

BEAT_PARAGRAPH_MAX = 3
LOW_ENGAGEMENT_THRESHOLD = 40
HIGH_COGNITIVE_LOAD_THRESHOLD = 70
LOW_PAYOFF_THRESHOLD = 30
OVER_FRAGMENTED_BEAT_MIN = 4
MERGE_CONFIDENCE_FLOOR = 0.45
BIGRAM_MERGE_THRESHOLD = 0.55
BIGRAM_ENTITY_MERGE_THRESHOLD = 0.35


def _clamp_score(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _clip_text(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", "", text.strip())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _normalize_question(text: str) -> str:
    lowered = text.strip().lower()
    return WEAK_WORD_RE.sub("", lowered)


def _bigrams(text: str) -> set[str]:
    normalized = _normalize_question(text)
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def classify_question_type(question: str) -> str:
    for question_type, pattern in QUESTION_TYPE_PATTERNS:
        if pattern.search(question):
            return question_type
    return "other"


def extract_entities(question: str) -> set[str]:
    entities: set[str] = set()
    for match in ENTITY_RE.finditer(question):
        token = match.group(0)
        if token in ENTITY_STOP:
            continue
        if all(char in WEAK_WORDS for char in token):
            continue
        entities.add(token)
    return entities


def _canonical_id(question: str, created_scene: int) -> str:
    digest = hashlib.sha256(f"{created_scene}:{_normalize_question(question)}".encode()).hexdigest()[
        :16
    ]
    return f"cqc-{digest}"


def _chain_involved_scenes(chain: dict[str, Any]) -> set[int]:
    scenes = {int(chain.get("created_scene_ordinal") or chain.get("created_scene") or 0)}
    scenes.update(int(item) for item in chain.get("carried_scene_ordinals") or [])
    answered = chain.get("answered_scene_ordinal") or chain.get("answered_scene")
    if answered is not None:
        scenes.add(int(answered))
    return {item for item in scenes if item > 0}


def _chain_lifecycle(chain: dict[str, Any], *, total_scenes: int) -> list[dict[str, Any]]:
    created = int(chain.get("created_scene_ordinal") or chain.get("created_scene") or 0)
    lifecycle: list[dict[str, Any]] = []
    if created > 0:
        lifecycle.append({"scene_ordinal": created, "status": "created"})
    for ordinal in sorted(chain.get("carried_scene_ordinals") or []):
        if int(ordinal) != created:
            lifecycle.append({"scene_ordinal": int(ordinal), "status": "carried"})
    status = str(chain.get("status") or "created")
    answered = chain.get("answered_scene_ordinal") or chain.get("answered_scene")
    if status == "partially_answered" and answered is not None:
        lifecycle.append({"scene_ordinal": int(answered), "status": "partially_answered"})
    elif status == "transformed":
        transformed_scene = int(answered or created)
        lifecycle.append({"scene_ordinal": transformed_scene, "status": "transformed"})
    elif status == "answered" and answered is not None:
        lifecycle.append({"scene_ordinal": int(answered), "status": "answered"})
    elif status == "dropped":
        last_scene = max(_chain_involved_scenes(chain) or {created or total_scenes})
        lifecycle.append({"scene_ordinal": last_scene, "status": "dropped"})
    elif status not in {"answered", "dropped"}:
        last_scene = max(_chain_involved_scenes(chain) or {created or total_scenes})
        if last_scene >= total_scenes:
            lifecycle.append({"scene_ordinal": last_scene, "status": "open"})
        else:
            lifecycle.append({"scene_ordinal": last_scene, "status": "deferred"})
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for item in lifecycle:
        key = (int(item["scene_ordinal"]), str(item["status"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _singleton_canonical(chain: dict[str, Any], *, total_scenes: int) -> dict[str, Any]:
    question = str(chain.get("question_summary") or chain.get("canonical_question") or "")
    created = int(chain.get("created_scene_ordinal") or chain.get("created_scene") or 0)
    answered = chain.get("answered_scene_ordinal") or chain.get("answered_scene")
    status = str(chain.get("status") or "created")
    return {
        "canonical_id": _canonical_id(question, created),
        "canonical_question": question,
        "aliases": [],
        "source_chain_ids": [str(chain.get("question_chain_id") or chain.get("canonical_id") or "")],
        "created_scene": created,
        "carried_scene_ordinals": list(chain.get("carried_scene_ordinals") or []),
        "transformed_scenes": [int(answered)] if status == "transformed" and answered is not None else [],
        "answered_scene": int(answered) if answered is not None else None,
        "status": status,
        "strength": int(chain.get("strength") or 0),
        "open_at_chapter_end": status not in {"answered", "dropped"},
        "confidence": 1.0,
        "merge_reason": "singleton",
        "question_type": classify_question_type(question),
        "auto_merged": False,
        "lifecycle": _chain_lifecycle(chain, total_scenes=total_scenes),
    }


def _merge_pair_confidence(left: dict[str, Any], right: dict[str, Any]) -> tuple[float, str]:
    left_q = str(left.get("question_summary") or "")
    right_q = str(right.get("question_summary") or "")
    bigram_score = _jaccard(_bigrams(left_q), _bigrams(right_q))
    left_entities = extract_entities(left_q)
    right_entities = extract_entities(right_q)
    shared_entities = left_entities & right_entities
    if left_entities and right_entities and not shared_entities:
        return 0.0, "entity_conflict"
    if bigram_score >= BIGRAM_MERGE_THRESHOLD:
        return min(1.0, 0.55 + bigram_score * 0.45), "bigram_similarity"
    if shared_entities and bigram_score >= BIGRAM_ENTITY_MERGE_THRESHOLD:
        return min(1.0, 0.45 + bigram_score * 0.45), "shared_entity_bigram"
    return bigram_score, "below_threshold"


def _can_merge(left: dict[str, Any], right: dict[str, Any]) -> tuple[bool, float, str]:
    left_q = str(left.get("question_summary") or "")
    right_q = str(right.get("question_summary") or "")
    left_type = classify_question_type(left_q)
    right_type = classify_question_type(right_q)
    if left_type != right_type:
        return False, 0.0, "question_type_mismatch"
    confidence, reason = _merge_pair_confidence(left, right)
    return confidence >= MERGE_CONFIDENCE_FLOOR, confidence, reason


def _merge_chains(
    group: list[dict[str, Any]],
    *,
    confidence: float,
    merge_reason: str,
    total_scenes: int,
) -> dict[str, Any]:
    canonical_question = max(
        group,
        key=lambda item: (int(item.get("strength") or 0), len(str(item.get("question_summary") or ""))),
    )["question_summary"]
    aliases = sorted(
        {
            str(item.get("question_summary") or "")
            for item in group
            if str(item.get("question_summary") or "") != canonical_question
        }
    )
    created_scene = min(
        int(item.get("created_scene_ordinal") or item.get("created_scene") or 0) for item in group
    )
    carried: set[int] = set()
    transformed_scenes: set[int] = set()
    answered_candidates: list[int] = []
    source_ids: list[str] = []
    strength = 0
    statuses: list[str] = []
    for item in group:
        source_ids.append(str(item.get("question_chain_id") or ""))
        strength = max(strength, int(item.get("strength") or 0))
        carried.update(int(value) for value in item.get("carried_scene_ordinals") or [])
        status = str(item.get("status") or "created")
        statuses.append(status)
        answered = item.get("answered_scene_ordinal") or item.get("answered_scene")
        if status == "transformed" and answered is not None:
            transformed_scenes.add(int(answered))
        if answered is not None:
            answered_candidates.append(int(answered))
    status_priority = [
        "answered",
        "partially_answered",
        "transformed",
        "carried",
        "created",
        "dropped",
    ]
    merged_status = next((name for name in status_priority if name in statuses), statuses[0])
    answered_scene = max(answered_candidates) if answered_candidates else None
    lifecycle_map: dict[tuple[int, str], dict[str, Any]] = {}
    for item in group:
        for entry in _chain_lifecycle(item, total_scenes=total_scenes):
            lifecycle_map[(int(entry["scene_ordinal"]), str(entry["status"]))] = entry
    return {
        "canonical_id": _canonical_id(canonical_question, created_scene),
        "canonical_question": canonical_question,
        "aliases": aliases,
        "source_chain_ids": [item for item in source_ids if item],
        "created_scene": created_scene,
        "carried_scene_ordinals": sorted(carried),
        "transformed_scenes": sorted(transformed_scenes),
        "answered_scene": answered_scene,
        "status": merged_status,
        "strength": strength,
        "open_at_chapter_end": merged_status not in {"answered", "dropped"},
        "confidence": round(confidence, 2),
        "merge_reason": merge_reason,
        "question_type": classify_question_type(canonical_question),
        "auto_merged": len(group) > 1,
        "lifecycle": list(lifecycle_map.values()),
    }


def canonicalize_question_chains(chains: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge synonymous question chains with deterministic rules."""
    if not chains:
        return []
    total_scenes = 0
    for chain in chains:
        total_scenes = max(total_scenes, max(_chain_involved_scenes(chain) or {0}))
    if total_scenes <= 0:
        total_scenes = len(chains)

    remaining = list(chains)
    canonical: list[dict[str, Any]] = []
    while remaining:
        seed = remaining.pop(0)
        group = [seed]
        rejected: list[dict[str, Any]] = []
        best_confidence = 1.0
        merge_reason = "singleton"
        for candidate in remaining:
            ok, confidence, reason = _can_merge(seed, candidate)
            if ok:
                group.append(candidate)
                best_confidence = min(best_confidence, confidence)
                merge_reason = reason
            else:
                rejected.append(candidate)
        remaining = rejected
        if len(group) == 1:
            canonical.append(_singleton_canonical(seed, total_scenes=total_scenes))
        else:
            canonical.append(
                _merge_chains(
                    group,
                    confidence=best_confidence,
                    merge_reason=merge_reason,
                    total_scenes=total_scenes,
                )
            )
    return sorted(canonical, key=lambda item: (item["created_scene"], item["canonical_id"]))


def _phase_for_scene(scene_ordinal: int, phase_boundaries: list[dict[str, int]]) -> int | None:
    for phase in phase_boundaries:
        if phase["start_scene_ordinal"] <= scene_ordinal <= phase["end_scene_ordinal"]:
            return int(phase["ordinal"])
    return None


def rank_canonical_chains(
    canonical: list[dict[str, Any]],
    total_scenes: int,
    phase_boundaries: list[dict[str, int]],
) -> list[dict[str, Any]]:
    """Rank canonical chains by deterministic importance."""
    ranked: list[dict[str, Any]] = []
    safe_total = max(total_scenes, 1)
    for chain in canonical:
        involved = _chain_involved_scenes(
            {
                "created_scene_ordinal": chain.get("created_scene"),
                "carried_scene_ordinals": chain.get("carried_scene_ordinals"),
                "answered_scene_ordinal": chain.get("answered_scene"),
            }
        )
        if not involved:
            involved = {int(chain.get("created_scene") or 1)}
        lifespan_span = max(involved) - min(involved) + 1
        lifespan_score = _clamp_score(lifespan_span / safe_total * 100)
        coverage = len(involved) / safe_total
        transform_score = 100.0 if chain.get("status") == "transformed" else (
            60.0 if chain.get("transformed_scenes") else 0.0
        )
        if chain.get("status") == "answered":
            answered_or_open = 100.0
        elif chain.get("open_at_chapter_end"):
            answered_or_open = 70.0
        elif chain.get("status") == "dropped":
            answered_or_open = 20.0
        else:
            answered_or_open = 50.0
        phase_ids = {
            _phase_for_scene(scene_ordinal, phase_boundaries)
            for scene_ordinal in involved
        }
        phase_ids.discard(None)
        phase_cross = 100.0 if len(phase_ids) >= 2 else 0.0
        importance = (
            0.25 * float(chain.get("strength") or 0)
            + 0.20 * lifespan_score
            + 0.20 * coverage * 100.0
            + 0.15 * transform_score
            + 0.10 * answered_or_open
            + 0.10 * phase_cross
        )
        payload = dict(chain)
        payload["importance"] = _clamp_score(importance)
        payload["importance_formula_version"] = CHAIN_RANK_FORMULA_VERSION
        ranked.append(payload)
    ranked.sort(key=lambda item: (-int(item["importance"]), item["created_scene"], item["canonical_id"]))
    return ranked


def _score_from_profile(profile: SceneReaderJourneyProfileItem, engagement_score: int) -> float:
    return (
        0.20 * engagement_score
        + 0.15 * profile.hook_score
        + 0.15 * profile.payoff_score
        + 0.15 * profile.information_gain_score
        + 0.10 * profile.tension_score
    )


def compute_scene_importance(
    *,
    profile: SceneReaderJourneyProfileItem,
    engagement_score: int,
    paragraph_count: int,
    question_chain_importance: float,
    is_chapter_end: bool,
    is_phase_boundary: bool,
    beat_hint: bool = False,
) -> dict[str, Any]:
    """Compute deterministic display role for a scene node."""
    phase_boundary_bonus = 100.0 if is_phase_boundary else 0.0
    paragraph_scale = min(100.0, paragraph_count / 8.0 * 100.0)
    raw = (
        _score_from_profile(profile, engagement_score)
        + 0.10 * question_chain_importance
        + 0.10 * phase_boundary_bonus
        + 0.05 * paragraph_scale
    )
    importance_score = _clamp_score(raw)
    reasons: list[str] = []

    if importance_score >= ROLE_THRESHOLDS["core"]:
        role = "core"
    elif importance_score >= ROLE_THRESHOLDS["secondary"]:
        role = "secondary"
    else:
        role = "beat"

    if profile.hook_score >= 70:
        role = "core"
        reasons.append("hook>=70")
    if profile.payoff_score >= 70:
        role = "core"
        reasons.append("payoff>=70")
    if is_chapter_end:
        role = "core"
        reasons.append("chapter_end_floor")
    if is_phase_boundary and ROLE_ORDER[role] < ROLE_ORDER["secondary"]:
        role = "secondary"
        reasons.append("phase_boundary_floor")

    short_connector = (
        paragraph_count <= BEAT_PARAGRAPH_MAX
        and beat_hint
        and profile.hook_score < 70
        and profile.payoff_score < 70
        and not is_chapter_end
        and not is_phase_boundary
        and importance_score < ROLE_THRESHOLDS["secondary"]
    )
    if short_connector:
        role = "beat"
        reasons.append("short_connector")

    return {
        "role": role,
        "importance_score": importance_score,
        "importance_formula_version": IMPORTANCE_FORMULA_VERSION,
        "deterministic_reasons": reasons,
    }


def _collect_intervals(flags: list[tuple[int, bool]], *, risk_type: str, min_span: int = 2) -> list[dict[str, Any]]:
    intervals: list[dict[str, Any]] = []
    start: int | None = None
    for index, (ordinal, active) in enumerate(flags):
        if active:
            if start is None:
                start = ordinal
        if (not active or index == len(flags) - 1) and start is not None:
            end = ordinal if active and index == len(flags) - 1 else flags[index - 1][0]
            if end - start + 1 >= min_span:
                intervals.append(
                    {
                        "risk_type": risk_type,
                        "start_scene_ordinal": start,
                        "end_scene_ordinal": end,
                        "span": end - start + 1,
                    }
                )
            start = None
    return intervals


def build_risk_intervals(
    profiles: list[SceneReaderJourneyProfileItem],
    scene_nodes: list[dict[str, Any]],
    *,
    engagement_by_ordinal: dict[int, int],
    dropped_questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Identify consecutive risk intervals for the journey chart."""
    ordered = sorted(profiles, key=lambda item: item.scene_ordinal)
    intervals: list[dict[str, Any]] = []

    no_payoff_flags = [
        (
            profile.scene_ordinal,
            (not profile.payoffs) or profile.payoff_score < LOW_PAYOFF_THRESHOLD,
        )
        for profile in ordered
    ]
    for item in _collect_intervals(no_payoff_flags, risk_type="consecutive_no_payoff"):
        item["summary"] = (
            f"Scene {item['start_scene_ordinal']}—{item['end_scene_ordinal']} "
            f"连续{item['span']}场缺少有效payoff"
        )
        item["trigger"] = "payoff_score<30 或 payoffs 为空，连续>=2"
        item["needs_review"] = item["span"] >= 3
        intervals.append(item)

    low_engagement_flags = [
        (profile.scene_ordinal, engagement_by_ordinal.get(profile.scene_ordinal, 0) < LOW_ENGAGEMENT_THRESHOLD)
        for profile in ordered
    ]
    for item in _collect_intervals(low_engagement_flags, risk_type="low_engagement"):
        item["summary"] = (
            f"Scene {item['start_scene_ordinal']}—{item['end_scene_ordinal']} "
            f"engagement持续偏低"
        )
        item["trigger"] = f"engagement<{LOW_ENGAGEMENT_THRESHOLD}，连续>=2"
        item["needs_review"] = item["span"] >= 3
        item["field_used"] = "engagement"
        intervals.append(item)

    high_load_flags = [
        (profile.scene_ordinal, profile.cognitive_load_score >= HIGH_COGNITIVE_LOAD_THRESHOLD)
        for profile in ordered
    ]
    for item in _collect_intervals(high_load_flags, risk_type="high_cognitive_load"):
        item["summary"] = (
            f"Scene {item['start_scene_ordinal']}—{item['end_scene_ordinal']} "
            f"认知负担偏高"
        )
        item["trigger"] = f"cognitive_load>={HIGH_COGNITIVE_LOAD_THRESHOLD}，连续>=2"
        item["needs_review"] = True
        intervals.append(item)

    for diagnostic in dropped_questions:
        ordinal = int(diagnostic.get("scene_ordinal") or 0)
        intervals.append(
            {
                "risk_type": "dropped_question",
                "start_scene_ordinal": ordinal,
                "end_scene_ordinal": ordinal,
                "span": 1,
                "summary": _clip_text(
                    f"Scene {ordinal} 高强度问题未承接：{diagnostic.get('question', '')}",
                    120,
                ),
                "trigger": "高强度 question_out 未在下一场 carried/created/answered",
                "needs_review": True,
                "question": diagnostic.get("question"),
                "strength": diagnostic.get("strength"),
            }
        )

    beat_flags = [
        (int(node["scene_ordinal"]), str(node["role"]) == "beat") for node in scene_nodes
    ]
    for item in _collect_intervals(
        beat_flags,
        risk_type="over_fragmented_beats",
        min_span=OVER_FRAGMENTED_BEAT_MIN,
    ):
        item["summary"] = (
            f"Scene {item['start_scene_ordinal']}—{item['end_scene_ordinal']} "
            f"连续{item['span']}个Beat节点，节奏可能过碎"
        )
        item["trigger"] = f"连续>={OVER_FRAGMENTED_BEAT_MIN}个 beat 节点"
        item["needs_review"] = item["span"] >= OVER_FRAGMENTED_BEAT_MIN
        intervals.append(item)

    intervals.sort(key=lambda item: (item["start_scene_ordinal"], item["risk_type"]))
    return intervals


def _is_v2_native_presentation(journey_run: ReaderJourneyRun) -> bool:
    """True when visualization must use V2 reading_momentum dropoff (not engagement)."""
    try:
        details = json.loads(journey_run.failure_details_json or "{}")
    except json.JSONDecodeError:
        details = {}
    source_mode = details.get("source_mode")
    if source_mode in {"v2_native", "local_fixture"}:
        return True
    version = str(journey_run.scene_contract_version or "")
    return version.startswith("2.")


def build_v2_dropoff_risk_intervals(scene_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build V2 risk intervals from reading_momentum (never engagement<40).

    base_dropoff_risk = 100 - reading_momentum, with chapter-level penalties:
    - consecutive two-scene clear decline: +8
    - three consecutive reading_momentum<45: +15
    - hook>75 without payoff in a reasonable span: +10
    """
    ordered = sorted(
        [
            node
            for node in scene_nodes
            if node.get("role") != "beat" and node.get("node_type") != "beat"
        ],
        key=lambda item: int(item["scene_ordinal"]),
    )
    if not ordered:
        return []

    momentums: list[float] = []
    hooks: list[float] = []
    payoffs: list[float] = []
    dropoffs: list[float] = []
    ordinals: list[int] = []
    for node in ordered:
        scores = node.get("scores") or {}
        momentum = scores.get("reading_momentum")
        if momentum is None:
            engagement = (node.get("engagement") or {}).get("engagement_score")
            momentum = engagement if engagement is not None else 0
        momentum_f = float(momentum)
        momentums.append(momentum_f)
        hooks.append(float(scores.get("hook") or 0))
        payoffs.append(float(scores.get("payoff") or 0))
        stored = scores.get("dropoff_risk")
        dropoffs.append(
            float(stored) if stored is not None else max(0.0, min(100.0, 100.0 - momentum_f))
        )
        ordinals.append(int(node["scene_ordinal"]))

    intervals: list[dict[str, Any]] = []

    for index in range(2, len(momentums)):
        d1 = momentums[index - 1] - momentums[index - 2]
        d2 = momentums[index] - momentums[index - 1]
        if d1 < -0.5 and d2 < -0.5:
            start_index = index - 2
            end = index
            penalties = [
                {"code": "consecutive_decline", "amount": 8, "label": "连续两场明显下降"}
            ]
            base = 100.0 - momentums[end]
            final_risk = max(dropoffs[end], min(100.0, base + 8))
            intervals.append(
                {
                    "risk_type": "momentum_decline",
                    "start_scene_ordinal": ordinals[start_index],
                    "end_scene_ordinal": ordinals[end],
                    "span": ordinals[end] - ordinals[start_index] + 1,
                    "summary": (
                        f"Scene {ordinals[start_index]}—{ordinals[end]} "
                        "reading_momentum 连续明显下降"
                    ),
                    "trigger": "连续两场 reading_momentum 明显下降",
                    "needs_review": True,
                    "field_used": "reading_momentum",
                    "penalties": penalties,
                    "final_risk": round(final_risk, 1),
                }
            )

    low_flags = [(ordinals[i], momentums[i] < 45) for i in range(len(momentums))]
    for item in _collect_intervals(low_flags, risk_type="low_reading_momentum"):
        if item["span"] < 3:
            continue
        end_ord = int(item["end_scene_ordinal"])
        end_index = ordinals.index(end_ord)
        base = 100.0 - momentums[end_index]
        penalties = [
            {
                "code": "consecutive_low_momentum",
                "amount": 15,
                "label": "连续三场 reading_momentum<45",
            }
        ]
        final_risk = max(dropoffs[end_index], min(100.0, base + 15))
        item["summary"] = (
            f"Scene {item['start_scene_ordinal']}—{item['end_scene_ordinal']} "
            "reading_momentum 持续偏低"
        )
        item["trigger"] = "reading_momentum<45，连续>=3"
        item["needs_review"] = True
        item["field_used"] = "reading_momentum"
        item["penalties"] = penalties
        item["final_risk"] = round(final_risk, 1)
        intervals.append(item)

    span = 3
    for index, hook in enumerate(hooks):
        if hook <= 75:
            continue
        if payoffs[index] >= 40:
            continue
        future_payoff = any(
            payoffs[ahead] >= 50
            for ahead in range(index + 1, min(len(payoffs), index + 1 + span))
        )
        if future_payoff:
            continue
        end_index = min(len(ordinals) - 1, index + span)
        base = 100.0 - momentums[index]
        penalties = [
            {
                "code": "unpaid_hook",
                "amount": 10,
                "label": "hook>75 且合理跨度内无 payoff",
            }
        ]
        final_risk = max(dropoffs[index], min(100.0, base + 10))
        intervals.append(
            {
                "risk_type": "unpaid_hook",
                "start_scene_ordinal": ordinals[index],
                "end_scene_ordinal": ordinals[end_index],
                "span": ordinals[end_index] - ordinals[index] + 1,
                "summary": (
                    f"Scene {ordinals[index]} hook 偏高且后续 {span} 场内未见有效 payoff"
                ),
                "trigger": "hook>75 且合理跨度内无 payoff",
                "needs_review": True,
                "field_used": "reading_momentum",
                "penalties": penalties,
                "final_risk": round(final_risk, 1),
            }
        )

    for index, risk in enumerate(dropoffs):
        if risk < 60:
            continue
        if any(
            item["start_scene_ordinal"] <= ordinals[index] <= item["end_scene_ordinal"]
            for item in intervals
        ):
            continue
        intervals.append(
            {
                "risk_type": "high_dropoff_risk",
                "start_scene_ordinal": ordinals[index],
                "end_scene_ordinal": ordinals[index],
                "span": 1,
                "summary": (
                    f"Scene {ordinals[index]} 流失风险偏高（base=100-reading_momentum）"
                ),
                "trigger": "base_dropoff_risk = 100 - reading_momentum",
                "needs_review": risk >= 70,
                "field_used": "reading_momentum",
                "penalties": [],
                "final_risk": round(risk, 1),
            }
        )

    intervals.sort(key=lambda item: (item["start_scene_ordinal"], item["risk_type"]))
    return intervals


def _phase_payload(
    phase: ReaderJourneyPhase,
    scene_nodes: list[dict[str, Any]],
    engagement_by_ordinal: dict[int, int],
) -> dict[str, Any]:
    ordinals = list(
        range(int(phase.start_scene_ordinal), int(phase.end_scene_ordinal) + 1)
    )
    nodes = [node for node in scene_nodes if int(node["scene_ordinal"]) in ordinals]
    # Beats are localization aids only — excluded from chapter/phase means.
    mean_nodes = [
        node
        for node in nodes
        if node.get("include_in_chapter_mean", str(node.get("role")) != "beat")
        and str(node.get("role")) != "beat"
    ]
    if mean_nodes:
        engagements = [
            engagement_by_ordinal.get(int(node["scene_ordinal"]), 0) for node in mean_nodes
        ]
    else:
        engagements = [engagement_by_ordinal.get(ordinal, 0) for ordinal in ordinals]
    return {
        "ordinal": phase.ordinal,
        "title": phase.title,
        "start_scene_ordinal": phase.start_scene_ordinal,
        "end_scene_ordinal": phase.end_scene_ordinal,
        "primary_reader_question": phase.primary_reader_question,
        "dominant_emotion": phase.dominant_emotion,
        "reading_payoff": phase.reading_payoff,
        "continuation_motivation": phase.continuation_motivation,
        "summary": phase.summary,
        "confidence": phase.confidence,
        "average_engagement": round(sum(engagements) / max(len(engagements), 1), 1),
        "core_scene_count": sum(1 for node in nodes if node["role"] == "core"),
        "beat_count": sum(1 for node in nodes if node["role"] == "beat"),
        "scene_span": len(ordinals),
    }


def _strongest_marker(
    profiles: list[SceneReaderJourneyProfileItem],
    *,
    field: str,
    label_key: str,
) -> dict[str, Any] | None:
    best_profile: SceneReaderJourneyProfileItem | None = None
    best_item: dict[str, Any] | None = None
    best_strength = -1
    for profile in profiles:
        for item in getattr(profile, field):
            strength = int(getattr(item, "strength", 0) or 0)
            if strength > best_strength:
                best_strength = strength
                best_profile = profile
                best_item = item.model_dump()
    if best_profile is None or best_item is None:
        return None
    return {
        "scene_ordinal": best_profile.scene_ordinal,
        "scene_id": best_profile.scene_id,
        "strength": best_strength,
        label_key: best_item.get("summary") or best_item.get("question") or "",
        "type": best_item.get("type"),
        "evidence_paragraph_ids": list(best_item.get("evidence_paragraph_ids") or []),
    }


def _weak_interval_text(risk_intervals: list[dict[str, Any]]) -> str:
    candidates = [
        item
        for item in risk_intervals
        if item["risk_type"] in {
            "consecutive_no_payoff",
            "low_engagement",
            "low_reading_momentum",
            "momentum_decline",
            "unpaid_hook",
            "high_dropoff_risk",
            "over_fragmented_beats",
        }
    ]
    if not candidates:
        return "无明显薄弱区间"
    best = max(candidates, key=lambda item: (item.get("span", 1), item["start_scene_ordinal"]))
    return (
        f"Scene {best['start_scene_ordinal']}—{best['end_scene_ordinal']} "
        f"({best['risk_type']})"
    )


def _calibration_status(journey_run: ReaderJourneyRun) -> dict[str, Any]:
    details: dict[str, Any] = {}
    try:
        details = json.loads(journey_run.failure_details_json or "{}")
    except json.JSONDecodeError:
        details = {}
    audits = details.get("semantic_calibration_audit") or []
    latest = audits[-1] if isinstance(audits, list) and audits else {}
    source_mode = details.get("source_mode")
    status = {
        "scene_contract_version": journey_run.scene_contract_version,
        "scene_prompt_version": journey_run.scene_prompt_version,
        "planner_version": journey_run.planner_version,
        "formula_version": journey_run.formula_version,
        "semantic_source": "model+deterministic_calibration",
        "calibrated": bool(audits),
        "latest_audit": latest,
        "evidence_coverage": 1.0,
    }
    if source_mode:
        status["source_mode"] = source_mode
        status["semantic_source"] = str(source_mode)
    display_banner = details.get("display_banner")
    if display_banner:
        status["display_banner"] = display_banner
    return status


def _apply_v2_presentation_overrides(
    scene_nodes: list[dict[str, Any]],
    summary: ChapterReaderJourneySummary | None,
) -> None:
    """Merge fixture / v2 deterministic presentation fields onto visualization nodes.

    Does not recompute literary diagnostics; only surfaces already-persisted
    scores, diagnoses, and node-role overrides for contract 2.0 runs.
    """
    if summary is None:
        return
    try:
        deterministic = json.loads(summary.deterministic_statistics_json or "{}")
    except json.JSONDecodeError:
        return
    if not isinstance(deterministic, dict):
        return

    scores_by_ordinal = deterministic.get("v2_scene_scores") or {}
    insights_by_ordinal = deterministic.get("v2_dimension_insights") or {}
    axes_by_ordinal = deterministic.get("v2_genre_axes") or {}
    ledger_by_ordinal = {
        str(row.get("scene_ordinal")): row
        for row in (deterministic.get("v2_open_question_ledger") or [])
        if isinstance(row, dict)
    }
    flags_by_ordinal = deterministic.get("v2_craft_flags") or {}
    diagnoses = deterministic.get("scene_diagnoses") or []
    overrides = deterministic.get("v2_node_overrides") or {}
    diagnosis_by_ordinal: dict[int, dict[str, Any]] = {}
    if isinstance(diagnoses, list):
        for item in diagnoses:
            if not isinstance(item, dict):
                continue
            ordinal = item.get("scene_ordinal")
            if ordinal is None:
                continue
            diagnosis_by_ordinal[int(ordinal)] = item

    for node in scene_nodes:
        ordinal = int(node["scene_ordinal"])
        key = str(ordinal)
        score_patch = scores_by_ordinal.get(key) if isinstance(scores_by_ordinal, dict) else None
        if isinstance(score_patch, dict):
            scores = dict(node.get("scores") or {})
            nullable_fields = {"pacing_fit", "hook_payoff_fit"}
            for field in (
                "reading_momentum",
                "plot_progress",
                "reading_tension",
                "pacing_speed",
                "pacing_fit",
                "hook",
                "payoff",
                "hook_payoff_fit",
                "emotional_investment",
                "clarity",
                "dropoff_risk",
                "pacing_fit_status",
                "pacing_fit_reason_code",
                "hook_payoff_fit_status",
                "hook_payoff_fit_reason_code",
            ):
                if field not in score_patch:
                    continue
                value = score_patch[field]
                if value is not None or field in nullable_fields:
                    scores[field] = value
            node["scores"] = scores
            if "reading_momentum" in score_patch and score_patch["reading_momentum"] is not None:
                engagement = dict(node.get("engagement") or {})
                engagement["engagement_score"] = int(round(float(score_patch["reading_momentum"])))
                node["engagement"] = engagement

        diag = diagnosis_by_ordinal.get(ordinal)
        if diag:
            node["primary_diagnosis"] = diag.get("primary_diagnosis")
            node["secondary_diagnoses"] = list(diag.get("secondary_diagnoses") or [])
            node["positive_mechanism"] = diag.get("positive_mechanism")
            node["data_quality_issue"] = diag.get("data_quality_issue")

        override = overrides.get(key) if isinstance(overrides, dict) else None
        if isinstance(override, dict):
            if override.get("scene_role"):
                node["scene_role"] = override["scene_role"]
            if override.get("node_type"):
                node["node_type"] = override["node_type"]
            if "include_in_main_curve" in override:
                node["include_in_main_curve"] = bool(override["include_in_main_curve"])
            if "include_in_chapter_mean" in override:
                node["include_in_chapter_mean"] = bool(override["include_in_chapter_mean"])
            forced_role = override.get("role")
            if forced_role in {"core", "secondary", "beat"}:
                node["role"] = forced_role
            elif override.get("node_type") == "beat":
                node["role"] = "beat"
            elif override.get("node_type") == "scene" and node.get("role") == "beat":
                # Fixture main scenes must not remain classifier beats.
                node["role"] = "core"

        if isinstance(axes_by_ordinal, dict) and axes_by_ordinal.get(key):
            node["genre_axes"] = list(axes_by_ordinal[key])
        ledger_row = ledger_by_ordinal.get(key)
        if ledger_row is not None:
            # The one number on the page that remembers what came before it.
            node["open_questions"] = {
                "opened": int(ledger_row.get("opened") or 0),
                "closed": int(ledger_row.get("closed") or 0),
                "balance": int(ledger_row.get("balance") or 0),
            }
        if isinstance(flags_by_ordinal, dict) and flags_by_ordinal.get(key):
            node["craft_flags"] = list(flags_by_ordinal[key])

        persisted = (
            insights_by_ordinal.get(key)
            if isinstance(insights_by_ordinal, dict)
            else None
        )
        attach_dimension_insights_to_node(
            node,
            persisted_insights=persisted if isinstance(persisted, dict) else None,
        )


def _narrative_loop_fields(
    *,
    profiles: list[SceneReaderJourneyProfileItem],
    ranked_chains: list[dict[str, Any]],
    question_lifecycle: list[dict[str, Any]],
    risk_intervals: list[dict[str, Any]],
    journey_run: ReaderJourneyRun,
) -> dict[str, Any]:
    """Additive NarrativeLoopView projection — does not mutate stored artifacts."""
    fingerprint = hashlib.sha256(
        f"{journey_run.id}:{journey_run.analysis_run_id}:{journey_run.scene_contract_version}:"
        f"{len(profiles)}".encode()
    ).hexdigest()[:16]
    bundle = build_narrative_loop_bundle(
        profiles,
        question_chains=ranked_chains,
        question_lifecycle=question_lifecycle,
        legacy_risk_intervals=risk_intervals,
        book_id=journey_run.book_id,
        chapter_id=journey_run.chapter_id,
        analysis_run_id=journey_run.analysis_run_id,
        journey_run_id=journey_run.id,
        scene_contract_version=journey_run.scene_contract_version,
        artifact_fingerprint=fingerprint,
    )
    return {
        "narrative_loops": bundle["narrative_loops"],
        "narrative_loop_risks": bundle["narrative_loop_risks"],
        "reading_resistance": bundle.get("reading_resistance") or [],
        "scene_payoff_claims": bundle["scene_payoff_claims"],
        "narrative_loop_consistency": bundle["consistency_report"],
        "narrative_loop_view_version": bundle["narrative_loop_view_version"],
    }


def _question_lifecycle_from_summary(
    summary: ChapterReaderJourneySummary | None,
) -> list[dict[str, Any]]:
    if summary is None:
        return []
    try:
        deterministic = json.loads(summary.deterministic_statistics_json or "{}")
    except json.JSONDecodeError:
        return []
    if not isinstance(deterministic, dict):
        return []
    raw = deterministic.get("question_lifecycle")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _expanded_diagnosis(summary: ChapterReaderJourneySummary | None) -> dict[str, Any]:
    if summary is None:
        return {}
    try:
        payload = json.loads(summary.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    try:
        pacing = json.loads(summary.pacing_diagnosis_json or "[]")
    except json.JSONDecodeError:
        pacing = []
    return {
        "pacing_diagnosis": pacing,
        "chapter_strengths": payload.get("chapter_strengths") or [],
        "chapter_risks": payload.get("chapter_risks") or [],
        "positive_feedback_distribution": json.loads(
            summary.positive_feedback_distribution_json or "{}"
        ),
        "hook_distribution": json.loads(summary.hook_distribution_json or "{}"),
        "one_sentence_diagnosis": summary.one_sentence_diagnosis,
    }


def _max_risk_interval_span(
    risk_intervals: list[dict[str, Any]], risk_type: str
) -> dict[str, Any] | None:
    candidates = [item for item in risk_intervals if item.get("risk_type") == risk_type]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.get("span", 1), item["start_scene_ordinal"]))


def _primary_chain_anchor_scenes(primary_chain: dict[str, Any] | None) -> tuple[int | None, set[int]]:
    if not primary_chain:
        return None, set()
    created = primary_chain.get("created_scene") or primary_chain.get("created_scene_ordinal")
    primary_created = int(created) if created is not None else None
    answer_transform: set[int] = set()
    answered = primary_chain.get("answered_scene") or primary_chain.get("answered_scene_ordinal")
    if answered is not None:
        answer_transform.add(int(answered))
    answer_transform.update(int(value) for value in primary_chain.get("transformed_scenes") or [])
    return primary_created, answer_transform


def _scene_node_payload(
    scene: Scene,
    profile: SceneReaderJourneyProfileItem,
    *,
    engagement: dict[str, Any],
    importance: dict[str, Any],
    phase_ordinal: int | None,
    evidence_count: int,
) -> dict[str, Any]:
    primary_payoff = None
    if profile.payoffs:
        top = max(profile.payoffs, key=lambda item: item.strength)
        primary_payoff = top.model_dump()
    primary_hook = None
    if profile.hooks:
        top = max(profile.hooks, key=lambda item: item.strength)
        primary_hook = top.model_dump()
    primary_risk = None
    if profile.risk_points:
        top = max(profile.risk_points, key=lambda item: item.severity)
        primary_risk = top.model_dump()
    return {
        "scene_id": scene.id,
        "scene_ordinal": scene.ordinal,
        "paragraph_range": {
            "start_paragraph_id": scene.start_paragraph_id,
            "end_paragraph_id": scene.end_paragraph_id,
        },
        "paragraph_count": paragraph_count_for_scene(scene),
        "phase_ordinal": phase_ordinal,
        "role": importance["role"],
        "importance_score": importance["importance_score"],
        "importance_formula_version": importance["importance_formula_version"],
        "deterministic_reasons": importance["deterministic_reasons"],
        "percentile": importance.get("percentile"),
        "forced_floor_reason": importance.get("forced_floor_reason"),
        "classification_reasons": importance.get("classification_reasons"),
        "final_level": importance.get("final_level"),
        "scene_value_summary": profile.scene_value_summary,
        "dominant_emotion": profile.dominant_emotion,
        "engagement": engagement,
        "scores": {
            "curiosity": profile.curiosity_score,
            "tension": profile.tension_score,
            "payoff": profile.payoff_score,
            "hook": profile.hook_score,
            "information_gain": profile.information_gain_score,
            "emotional_resonance": profile.emotional_resonance_score,
            "cognitive_load": profile.cognitive_load_score,
            "dropoff_risk": profile.dropoff_risk_score,
            "valence_start": profile.emotional_valence_start,
            "valence_end": profile.emotional_valence_end,
            "arousal_start": profile.arousal_start,
            "arousal_end": profile.arousal_end,
        },
        "reader_question_in": [item.model_dump() for item in profile.reader_question_in],
        "reader_question_created": [item.model_dump() for item in profile.reader_question_created],
        "reader_question_answered": [item.model_dump() for item in profile.reader_question_answered],
        "reader_question_out": [item.model_dump() for item in profile.reader_question_out],
        "payoffs": [item.model_dump() for item in profile.payoffs],
        "hooks": [item.model_dump() for item in profile.hooks],
        "techniques": [item.model_dump() for item in profile.techniques],
        "risk_points": [item.model_dump() for item in profile.risk_points],
        "information_changes": [item.model_dump() for item in profile.information_changes],
        "character_effects": [item.model_dump() for item in profile.character_effects],
        "writing_takeaways": [item.model_dump() for item in profile.writing_takeaways],
        "evidence_paragraph_ids": list(profile.evidence_paragraph_ids),
        "evidence_count": evidence_count,
        "confidence": profile.confidence,
        "primary_payoff": primary_payoff,
        "primary_hook": primary_hook,
        "primary_risk": primary_risk,
        "node_type": "beat" if importance["role"] == "beat" else "scene",
        "include_in_main_curve": importance["role"] != "beat",
        "include_in_chapter_mean": importance["role"] != "beat",
    }


def build_reader_journey_visualization(
    session: Session,
    journey_run: ReaderJourneyRun,
) -> dict[str, Any] | None:
    """Build full visualization payload for a succeeded journey run."""
    if journey_run.status != "succeeded":
        return None

    # Prefer journey-bound included scenes (same set used by execute/persist).
    try:
        from app.services.scene_boundary_manual_review import load_journey_bound_scenes

        _revision, scenes = load_journey_bound_scenes(session, journey_run)
    except Exception:
        _revision, scenes = load_revision_scenes(session, journey_run.analysis_run_id)
    if not scenes:
        return None

    allowed_scene_ids = {int(scene.id) for scene in scenes}
    profile_rows = [
        row
        for row in session.scalars(
            select(SceneReaderJourneyProfile)
            .where(SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id)
            .order_by(SceneReaderJourneyProfile.scene_ordinal)
        )
        if int(row.scene_id) in allowed_scene_ids
    ]
    if len(profile_rows) != len(scenes):
        return None

    phases = list(
        session.scalars(
            select(ReaderJourneyPhase)
            .where(ReaderJourneyPhase.reader_journey_run_id == journey_run.id)
            .order_by(ReaderJourneyPhase.ordinal)
        )
    )
    summary = session.scalar(
        select(ChapterReaderJourneySummary).where(
            ChapterReaderJourneySummary.reader_journey_run_id == journey_run.id
        )
    )
    chapter = session.get(Chapter, journey_run.chapter_id)

    profiles = [
        SceneReaderJourneyProfileItem.model_validate_json(row.payload_json) for row in profile_rows
    ]
    formula = load_formula_config()
    genre = journey_run.genre or str(formula.get("default_genre", "suspense"))
    total_scenes = len(scenes)
    max_ordinal = max(scene.ordinal for scene in scenes)
    phase_boundaries = [
        {
            "ordinal": phase.ordinal,
            "start_scene_ordinal": phase.start_scene_ordinal,
            "end_scene_ordinal": phase.end_scene_ordinal,
        }
        for phase in phases
    ]
    phase_start_ordinals = {phase.start_scene_ordinal for phase in phases}
    phase_end_ordinals = {phase.end_scene_ordinal for phase in phases}

    raw_chains = build_question_chains(profiles)
    canonical = canonicalize_question_chains(raw_chains)
    ranked_chains = rank_canonical_chains(canonical, total_scenes, phase_boundaries)
    primary_chain = ranked_chains[0] if ranked_chains else None
    phase_chains = ranked_chains[1:5]
    secondary_chains = ranked_chains[5:]

    chain_importance_by_scene: dict[int, float] = {}
    for chain in ranked_chains:
        for ordinal in _chain_involved_scenes(
            {
                "created_scene_ordinal": chain.get("created_scene"),
                "carried_scene_ordinals": chain.get("carried_scene_ordinals"),
                "answered_scene_ordinal": chain.get("answered_scene"),
            }
        ):
            chain_importance_by_scene[ordinal] = max(
                chain_importance_by_scene.get(ordinal, 0.0),
                float(chain.get("importance") or 0),
            )

    primary_created_scene, primary_answer_or_transform_scenes = _primary_chain_anchor_scenes(
        primary_chain
    )
    profile_by_ordinal = {profile.scene_ordinal: profile for profile in profiles}
    paragraph_counts = {scene.ordinal: paragraph_count_for_scene(scene) for scene in scenes}

    engagement_by_ordinal: dict[int, int] = {}
    for scene in sorted(scenes, key=lambda item: item.ordinal):
        profile = profile_by_ordinal[scene.ordinal]
        engagement = compute_engagement(profile, genre=genre).model_dump()
        engagement_by_ordinal[scene.ordinal] = int(engagement["engagement_score"])

    classification_rows = classify_scene_levels(
        profiles=profiles,
        engagement_by_ordinal=engagement_by_ordinal,
        paragraph_counts=paragraph_counts,
        chain_importance_by_scene=chain_importance_by_scene,
        phase_start_ordinals=phase_start_ordinals,
        phase_end_ordinals=phase_end_ordinals,
        primary_created_scene=primary_created_scene,
        primary_answer_or_transform_scenes=primary_answer_or_transform_scenes,
        max_ordinal=max_ordinal,
    )
    classification_by_ordinal = {row["scene_ordinal"]: row for row in classification_rows}

    curve_series: dict[str, list[dict[str, Any]]] = {
        "engagement": [],
        "valence": [],
        "arousal": [],
        "curiosity": [],
        "tension": [],
        "payoff": [],
        "hook": [],
        "dropoff_risk": [],
    }
    scene_nodes: list[dict[str, Any]] = []

    evidence_counts: dict[int, int] = {}
    for row in profile_rows:
        if row.artifact_id is None:
            evidence_counts[row.scene_id] = len(
                json.loads(row.payload_json or "{}").get("evidence_paragraph_ids") or []
            )
            continue
        count = session.scalar(
            select(func.count())
            .select_from(AnalysisEvidence)
            .where(AnalysisEvidence.artifact_id == row.artifact_id)
        )
        evidence_counts[row.scene_id] = int(count or 0)

    for scene in sorted(scenes, key=lambda item: item.ordinal):
        profile = profile_by_ordinal[scene.ordinal]
        engagement = compute_engagement(profile, genre=genre).model_dump()
        row = classification_by_ordinal[scene.ordinal]
        importance = {
            "role": row["final_level"],
            "importance_score": row["importance_score"],
            "importance_formula_version": row["importance_formula_version"],
            "deterministic_reasons": row["classification_reasons"],
            "percentile": row["percentile"],
            "forced_floor_reason": row["forced_floor_reason"],
            "classification_reasons": row["classification_reasons"],
            "final_level": row["final_level"],
        }
        phase_ordinal = _phase_for_scene(scene.ordinal, phase_boundaries)
        scene_nodes.append(
            _scene_node_payload(
                scene,
                profile,
                engagement=engagement,
                importance=importance,
                phase_ordinal=phase_ordinal,
                evidence_count=evidence_counts.get(scene.id, 0),
            )
        )
        is_beat = importance["role"] == "beat"
        curve_point_meta = {
            "include_in_main_curve": not is_beat,
            "node_type": "beat" if is_beat else "scene",
        }
        curve_series["engagement"].append(
            {
                "scene_ordinal": scene.ordinal,
                "value": engagement["engagement_score"],
                **curve_point_meta,
            }
        )
        curve_series["valence"].append(
            {
                "scene_ordinal": scene.ordinal,
                "start": profile.emotional_valence_start,
                "end": profile.emotional_valence_end,
                **curve_point_meta,
            }
        )
        curve_series["arousal"].append(
            {
                "scene_ordinal": scene.ordinal,
                "start": profile.arousal_start,
                "end": profile.arousal_end,
                **curve_point_meta,
            }
        )
        curve_series["curiosity"].append(
            {"scene_ordinal": scene.ordinal, "value": profile.curiosity_score, **curve_point_meta}
        )
        curve_series["tension"].append(
            {"scene_ordinal": scene.ordinal, "value": profile.tension_score, **curve_point_meta}
        )
        curve_series["payoff"].append(
            {"scene_ordinal": scene.ordinal, "value": profile.payoff_score, **curve_point_meta}
        )
        curve_series["hook"].append(
            {"scene_ordinal": scene.ordinal, "value": profile.hook_score, **curve_point_meta}
        )
        curve_series["dropoff_risk"].append(
            {
                "scene_ordinal": scene.ordinal,
                "value": profile.dropoff_risk_score,
                **curve_point_meta,
            }
        )

    dropped_questions = diagnose_dropped_high_strength_questions(profiles)
    risk_intervals = build_risk_intervals(
        profiles,
        scene_nodes,
        engagement_by_ordinal=engagement_by_ordinal,
        dropped_questions=dropped_questions,
    )

    hook_selection = select_visible_hooks(
        profiles=profiles,
        phase_end_ordinals=phase_end_ordinals,
        max_ordinal=max_ordinal,
        primary_chain=primary_chain,
        phase_chains=phase_chains,
    )
    payoff_selection = derive_and_select_payoffs(
        profiles=profiles,
        phases=phases,
        max_ordinal=max_ordinal,
    )
    cluster_selection = build_question_clusters(
        ranked_chains,
        phase_boundaries=phase_boundaries,
    )

    hook_markers = hook_selection["hook_markers"]
    payoff_markers = payoff_selection["visible_payoff_markers"]
    _apply_v2_presentation_overrides(scene_nodes, summary)
    for node in scene_nodes:
        if node.get("dimension_insights") is None and node.get("insight_source") is None:
            attach_dimension_insights_to_node(node)
    if _is_v2_native_presentation(journey_run):
        # Replace legacy engagement<40 intervals with V2 reading_momentum formula.
        kept = [
            item
            for item in risk_intervals
            if item.get("risk_type") not in {"low_engagement"}
        ]
        v2_intervals = build_v2_dropoff_risk_intervals(scene_nodes)
        risk_intervals = kept + v2_intervals
        risk_intervals.sort(
            key=lambda item: (item["start_scene_ordinal"], item["risk_type"])
        )
        # Keep chapter peaks aligned with reading_momentum when present.
        for node in scene_nodes:
            scores = node.get("scores") or {}
            momentum = scores.get("reading_momentum")
            if momentum is None:
                continue
            engagement_by_ordinal[int(node["scene_ordinal"])] = int(round(float(momentum)))
    # Keep curve include flags aligned with node overrides (e.g. fixture Beat).
    beat_ordinals = {
        int(node["scene_ordinal"])
        for node in scene_nodes
        if node.get("role") == "beat" or node.get("node_type") == "beat"
    }
    for points in curve_series.values():
        for point in points:
            ordinal = int(point["scene_ordinal"])
            if ordinal in beat_ordinals:
                point["include_in_main_curve"] = False
                point["node_type"] = "beat"
    role_counts = {
        "core": sum(1 for node in scene_nodes if node["role"] == "core"),
        "secondary": sum(1 for node in scene_nodes if node["role"] == "secondary"),
        "beat": sum(1 for node in scene_nodes if node["role"] == "beat"),
    }
    visual_density_warnings = build_density_warnings(
        scene_count=total_scenes,
        role_counts=role_counts,
        visible_hook_count=int(hook_selection["visible_hook_count"]),
        visible_cluster_count=int(cluster_selection["visible_question_cluster_count"]),
    )

    engagement_values = [value for value in engagement_by_ordinal.values()]
    peak_ordinal = max(engagement_by_ordinal, key=engagement_by_ordinal.get)
    valley_ordinal = min(engagement_by_ordinal, key=engagement_by_ordinal.get)
    diagnosis_text = summary.one_sentence_diagnosis if summary else ""
    visible_clusters = cluster_selection["visible_question_clusters"]
    primary_cluster_title = (
        str(visible_clusters[0]["cluster_title"])
        if visible_clusters
        else (primary_chain["canonical_question"] if primary_chain else diagnosis_text)
    )
    max_low_payoff = _max_risk_interval_span(risk_intervals, "consecutive_no_payoff")
    max_fragmentation = _max_risk_interval_span(risk_intervals, "over_fragmented_beats")
    strong_hook_count = sum(
        1 for marker in hook_markers if int(marker.get("strength") or 0) >= 85
    )

    scene_level_distribution = {
        "role_counts": role_counts,
        "classifications": classification_rows,
    }
    question_lifecycle = _question_lifecycle_from_summary(summary)

    # What the main curve is called and what decision it stands for. Only the profile knows,
    # and INV-P4 says presentation rules come from the backend — a client that re-derived the
    # genre would drift from the analysis the rest of the document was built on.
    main_curve_label, main_curve_why = main_curve_naming_for_book(session, journey_run.book_id)
    # What to call the four things a scene does to the reader's open questions. The client
    # must not re-derive this from the genre (INV-P4) — it is a fact about the book, and the
    # book's profile lives here.
    hook_words = hook_vocabulary_for_book(session, journey_run.book_id)
    payload = {
        "visualization_version": VISUALIZATION_VERSION,
        "main_curve": {"label": main_curve_label, "why": main_curve_why},
        "hook_vocabulary": hook_words,
        "chapter_summary": {
            "chapter_id": journey_run.chapter_id,
            "chapter_title": chapter.title if chapter else "",
            "diagnosis": _clip_text(diagnosis_text, 120),
            "primary_traction": primary_cluster_title,
            "primary_cluster_title": primary_cluster_title,
            "core_scene_count": role_counts["core"],
            "strong_hook_count": strong_hook_count,
            "stage_payoff_count": int(payoff_selection["visible_payoff_count"]),
            "max_low_payoff_interval": max_low_payoff,
            "max_fragmentation_interval": max_fragmentation,
            "strongest_payoff": _strongest_marker(profiles, field="payoffs", label_key="summary"),
            "strongest_hook": _strongest_marker(profiles, field="hooks", label_key="summary"),
            "weak_interval": _weak_interval_text(risk_intervals),
            "counts": {
                "scene_count": total_scenes,
                "phase_count": len(phases),
                "question_chain_count": len(raw_chains),
                "canonical_chain_count": len(canonical),
                **role_counts,
            },
            "peaks": {
                "engagement_peak": {
                    "scene_ordinal": peak_ordinal,
                    "value": engagement_by_ordinal[peak_ordinal],
                },
                "engagement_valley": {
                    "scene_ordinal": valley_ordinal,
                    "value": engagement_by_ordinal[valley_ordinal],
                },
                "engagement_average": round(
                    Decimal(str(sum(engagement_values) / max(len(engagement_values), 1))).quantize(
                        Decimal("0.1"), rounding=ROUND_HALF_UP
                    ),
                    1,
                ),
            },
            "expanded_diagnosis": _expanded_diagnosis(summary),
        },
        "phases": [
            _phase_payload(phase, scene_nodes, engagement_by_ordinal) for phase in phases
        ],
        "curve_series": curve_series,
        "scene_nodes": scene_nodes,
        "role_counts": role_counts,
        "primary_question_chain": primary_chain,
        "phase_question_chains": phase_chains,
        "secondary_question_chains": secondary_chains,
        "question_clusters": cluster_selection["question_clusters"],
        "visible_question_clusters": cluster_selection["visible_question_clusters"],
        "all_hook_count": hook_selection["all_hook_count"],
        "visible_hook_count": hook_selection["visible_hook_count"],
        "suppressed_hook_count": hook_selection["suppressed_hook_count"],
        "suppressed_hooks": hook_selection["suppressed_hooks"],
        "semantic_payoff_count": payoff_selection["semantic_payoff_count"],
        "derived_payoff_count": payoff_selection["derived_payoff_count"],
        "deduped_payoff_count": payoff_selection["deduped_payoff_count"],
        "visible_payoff_count": payoff_selection["visible_payoff_count"],
        "semantic_payoffs": payoff_selection["semantic_payoffs"],
        "derived_micro_payoffs": payoff_selection["derived_micro_payoffs"],
        "scene_level_distribution": scene_level_distribution,
        "visual_density_warnings": visual_density_warnings,
        "payoff_markers": payoff_markers,
        "hook_markers": hook_markers,
        "risk_intervals": risk_intervals,
        "formula_versions": {
            "visualization_version": VISUALIZATION_VERSION,
            "chain_rank_formula_version": CHAIN_RANK_FORMULA_VERSION,
            "importance_formula_version": IMPORTANCE_FORMULA_VERSION,
            "chain_merge_formula_version": CHAIN_MERGE_FORMULA_VERSION,
            "hook_select_formula_version": HOOK_SELECT_FORMULA_VERSION,
            "payoff_derive_formula_version": PAYOFF_DERIVE_FORMULA_VERSION,
            "cluster_formula_version": CLUSTER_FORMULA_VERSION,
            "engagement_formula_version": str(formula.get("version", "1.0")),
        },
        "calibration_status": _calibration_status(journey_run),
        "question_lifecycle": question_lifecycle,
        **_narrative_loop_fields(
            profiles=profiles,
            ranked_chains=ranked_chains,
            question_lifecycle=question_lifecycle,
            risk_intervals=risk_intervals,
            journey_run=journey_run,
        ),
    }
    return attach_comprehensive_reading_presentation(payload)
