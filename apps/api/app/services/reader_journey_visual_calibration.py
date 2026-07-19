"""Phase 1C-C.2.1 Reader Journey visual calibration — zero model calls, read-only profiles."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from app.schemas.reader_journey import SceneReaderJourneyProfileItem

VISUALIZATION_VERSION = "1.1"
IMPORTANCE_FORMULA_VERSION = "1.1"
HOOK_SELECT_FORMULA_VERSION = "1.1"
PAYOFF_DERIVE_FORMULA_VERSION = "1.1"
CLUSTER_FORMULA_VERSION = "1.1"

HOOK_VISIBLE_STRENGTH = 90
PAYOFF_VISIBLE_STRENGTH = 55
STRONG_HOOK_FLOOR = 90
STRONG_PAYOFF_FLOOR = 75
CORE_ABSOLUTE_FLOOR = 72
SECONDARY_ABSOLUTE_FLOOR = 40
CORE_TARGET_MAX_RATIO = 0.45
CORE_WARNING_RATIO = 0.5
HOOK_VISIBLE_MAX_RATIO = 0.6
MAX_VISIBLE_CLUSTERS = 5
CORE_TARGET_MAX_ABS = 6

CORE_PERCENTILE_FLOOR = 70
SECONDARY_PERCENTILE_FLOOR = 35
SHORT_CONNECTOR_PARAGRAPH_MAX = 3
HANDOFF_VISIBLE_STRENGTH = 50
CLUSTER_ALIAS_THRESHOLD = 0.42
CLUSTER_ESCALATION_THRESHOLD = 0.18
CLUSTER_ENTITY_ALIAS_OVERLAP = 0.4
CLUSTER_CONFIDENCE_FLOOR = 0.4
SECONDARY_SPARSE_TARGET_RATIO = 0.35
SECONDARY_SPARSE_MIN = 4

SceneLevel = Literal["core", "secondary", "beat"]
ForcedFloorReason = Literal[
    "chapter_end",
    "primary_question_created",
    "primary_transform_or_answer",
    "phase_key_turn",
    "first_core_info",
    "strong_payoff",
    "strong_hook",
]

HARD_FORCED_REASONS: frozenset[ForcedFloorReason] = frozenset(
    {
        "chapter_end",
        "primary_question_created",
        "primary_transform_or_answer",
        "strong_payoff",
    }
)
SOFT_FORCED_REASONS: frozenset[ForcedFloorReason] = frozenset(
    {
        "phase_key_turn",
        "strong_hook",
        "first_core_info",
    }
)

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

FORCED_REASON_PRIORITY: tuple[ForcedFloorReason, ...] = (
    "chapter_end",
    "primary_question_created",
    "primary_transform_or_answer",
    "strong_payoff",
    "phase_key_turn",
    "first_core_info",
    "strong_hook",
)

INFO_CHANGE_DERIVATION: dict[str, tuple[str, int, float]] = {
    "confirmation": ("information", 55, 0.75),
    "payoff": ("information", 62, 0.8),
    "identity_clue": ("identity", 60, 0.78),
    "rule_clue": ("rule", 60, 0.78),
    "new_information": ("information", 48, 0.62),
    "misdirection": ("information", 42, 0.55),
    "horror_payoff": ("horror_payoff", 68, 0.8),
    "stage_completion": ("stage_completion", 65, 0.8),
}

ANSWER_DEGREE_STRENGTH: dict[str, int] = {
    "full": 78,
    "partial": 62,
    "misleading": 48,
}


def _clamp_score(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _normalize_question(text: str) -> str:
    return WEAK_WORD_RE.sub("", text.strip().lower())


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


def _first_core_info_scene(profiles: list[SceneReaderJourneyProfileItem]) -> int | None:
    """First scene with identity/rule clue or identity/danger question created."""
    for profile in sorted(profiles, key=lambda item: item.scene_ordinal):
        for change in profile.information_changes:
            if change.type in {"identity_clue", "rule_clue"}:
                return profile.scene_ordinal
        for created in profile.reader_question_created:
            question = str(created.question or "")
            qtype = classify_question_type(question)
            if qtype in {"identity", "danger"}:
                return profile.scene_ordinal
    return None


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


def _chain_tokens(question: str) -> set[str]:
    """Stable 2-char tokens from normalized question text for clustering."""
    normalized = _normalize_question(question)
    tokens: set[str] = set()
    for index in range(max(len(normalized) - 1, 0)):
        token = normalized[index : index + 2]
        if token in ENTITY_STOP:
            continue
        if all(char in WEAK_WORDS for char in token):
            continue
        tokens.add(token)
    return tokens


def _question_similarity(left: str, right: str) -> tuple[float, float, str]:
    bigram_score = _jaccard(_bigrams(left), _bigrams(right))
    left_tokens = _chain_tokens(left)
    right_tokens = _chain_tokens(right)
    shared = left_tokens & right_tokens
    token_overlap = (
        len(shared) / max(len(left_tokens | right_tokens), 1)
        if (left_tokens or right_tokens)
        else 0.0
    )
    containment = 0.0
    left_n = _normalize_question(left)
    right_n = _normalize_question(right)
    if left_n and right_n:
        shorter, longer = (left_n, right_n) if len(left_n) <= len(right_n) else (right_n, left_n)
        if shorter in longer:
            containment = len(shorter) / max(len(longer), 1)
    combined = 0.50 * bigram_score + 0.35 * token_overlap + 0.15 * containment
    if (
        bigram_score >= CLUSTER_ALIAS_THRESHOLD
        or containment >= 0.7
        or (token_overlap >= CLUSTER_ENTITY_ALIAS_OVERLAP and bigram_score >= 0.2)
        or len(shared) >= 3
    ):
        relationship = "alias"
    elif combined >= CLUSTER_ESCALATION_THRESHOLD or len(shared) >= 3:
        relationship = "escalation"
    else:
        relationship = "below_threshold"
    confidence = min(1.0, 0.35 + combined * 0.65)
    return combined, confidence, relationship


def _compute_importance_score(
    profile: SceneReaderJourneyProfileItem,
    *,
    engagement_score: int,
    paragraph_count: int,
    chain_importance: float,
) -> int:
    paragraph_scale = min(100.0, paragraph_count / 8.0 * 100.0)
    raw = (
        0.20 * engagement_score
        + 0.15 * profile.hook_score
        + 0.15 * profile.payoff_score
        + 0.15 * profile.information_gain_score
        + 0.10 * profile.tension_score
        + 0.10 * chain_importance
        + 0.05 * paragraph_scale
    )
    return _clamp_score(raw)


def _percentile_by_score(scores: dict[int, int]) -> dict[int, int]:
    if not scores:
        return {}
    ordered = sorted(scores.items(), key=lambda item: item[1])
    if len(ordered) == 1:
        return {ordered[0][0]: 100}
    result: dict[int, int] = {}
    for index, (ordinal, _score) in enumerate(ordered):
        result[ordinal] = _clamp_score(100 * index / (len(ordered) - 1))
    return result


def _detect_forced_reasons(
    profile: SceneReaderJourneyProfileItem,
    *,
    scene_ordinal: int,
    max_ordinal: int,
    primary_created_scene: int | None,
    primary_answer_or_transform_scenes: set[int],
    phase_end_ordinals: set[int],
    first_core_info_scene: int | None,
) -> list[ForcedFloorReason]:
    reasons: list[ForcedFloorReason] = []
    if scene_ordinal == max_ordinal:
        reasons.append("chapter_end")
    if primary_created_scene is not None and scene_ordinal == primary_created_scene:
        reasons.append("primary_question_created")
    if scene_ordinal in primary_answer_or_transform_scenes:
        reasons.append("primary_transform_or_answer")
    if scene_ordinal in phase_end_ordinals:
        reasons.append("phase_key_turn")
    if first_core_info_scene is not None and scene_ordinal == first_core_info_scene:
        reasons.append("first_core_info")
    max_payoff = max((item.strength for item in profile.payoffs), default=profile.payoff_score)
    if profile.payoff_score >= STRONG_PAYOFF_FLOOR or max_payoff >= STRONG_PAYOFF_FLOOR:
        reasons.append("strong_payoff")
    max_hook = max((item.strength for item in profile.hooks), default=profile.hook_score)
    if profile.hook_score >= STRONG_HOOK_FLOOR or max_hook >= STRONG_HOOK_FLOOR:
        reasons.append("strong_hook")
    return reasons


def _primary_forced_reason(reasons: list[ForcedFloorReason]) -> str | None:
    if not reasons:
        return None
    for reason in FORCED_REASON_PRIORITY:
        if reason in reasons:
            return reason
    return reasons[0]


def classify_scene_levels(
    *,
    profiles: list[SceneReaderJourneyProfileItem],
    engagement_by_ordinal: dict[int, int],
    paragraph_counts: dict[int, int],
    chain_importance_by_scene: dict[int, float],
    phase_start_ordinals: set[int],
    phase_end_ordinals: set[int],
    primary_created_scene: int | None,
    primary_answer_or_transform_scenes: set[int],
    max_ordinal: int,
) -> list[dict[str, Any]]:
    """Classify scene display levels with absolute thresholds, floors, and scarcity."""
    ordered = sorted(profiles, key=lambda item: item.scene_ordinal)
    scene_count = len(ordered)
    if scene_count == 0:
        return []

    first_core_info = _first_core_info_scene(ordered)
    scores: dict[int, int] = {}
    forced_map: dict[int, list[ForcedFloorReason]] = {}
    for profile in ordered:
        ordinal = profile.scene_ordinal
        scores[ordinal] = _compute_importance_score(
            profile,
            engagement_score=engagement_by_ordinal.get(ordinal, 0),
            paragraph_count=paragraph_counts.get(ordinal, 1),
            chain_importance=chain_importance_by_scene.get(ordinal, 0.0),
        )
        forced_map[ordinal] = _detect_forced_reasons(
            profile,
            scene_ordinal=ordinal,
            max_ordinal=max_ordinal,
            primary_created_scene=primary_created_scene,
            primary_answer_or_transform_scenes=primary_answer_or_transform_scenes,
            phase_end_ordinals=phase_end_ordinals,
            first_core_info_scene=first_core_info,
        )

    percentiles = _percentile_by_score(scores)
    rows: dict[int, dict[str, Any]] = {}

    for profile in ordered:
        ordinal = profile.scene_ordinal
        score = scores[ordinal]
        percentile = percentiles[ordinal]
        forced_reasons = forced_map[ordinal]
        forced_floor_reason = _primary_forced_reason(forced_reasons)
        reasons: list[str] = []

        if forced_floor_reason:
            level: SceneLevel = "core"
            reasons.append(f"forced_core:{forced_floor_reason}")
        elif score >= CORE_ABSOLUTE_FLOOR and percentile >= CORE_PERCENTILE_FLOOR:
            level = "core"
            reasons.append("absolute_threshold_core")
        elif score >= SECONDARY_ABSOLUTE_FLOOR or percentile >= SECONDARY_PERCENTILE_FLOOR:
            level = "secondary"
            reasons.append(
                "absolute_threshold_secondary"
                if score >= SECONDARY_ABSOLUTE_FLOOR
                else "percentile_threshold_secondary"
            )
        else:
            level = "beat"
            reasons.append("below_secondary_threshold")

        if ordinal in phase_start_ordinals and ordinal != 1 and level == "beat":
            level = "secondary"
            reasons.append("phase_start_floor_secondary")

        rows[ordinal] = {
            "scene_ordinal": ordinal,
            "importance_score": score,
            "percentile": percentile,
            "forced_floor_reason": forced_floor_reason,
            "forced_reasons": list(forced_reasons),
            "final_level": level,
            "classification_reasons": reasons,
            "importance_formula_version": IMPORTANCE_FORMULA_VERSION,
        }

    # Short connectors demote only non-forced secondary/core candidates.
    for profile in ordered:
        ordinal = profile.scene_ordinal
        row = rows[ordinal]
        paragraph_count = paragraph_counts.get(ordinal, 1)
        if (
            paragraph_count <= SHORT_CONNECTOR_PARAGRAPH_MAX
            and not row["forced_floor_reason"]
            and row["final_level"] != "beat"
        ):
            row["final_level"] = "beat"
            row["classification_reasons"].append("short_connector_demote_beat")

    max_cores = min(
        CORE_TARGET_MAX_ABS,
        max(3, int(round(scene_count * CORE_TARGET_MAX_RATIO))),
    )
    core_count = sum(1 for row in rows.values() if row["final_level"] == "core")
    if core_count > max_cores:
        demote_count = core_count - max_cores
        # Prefer demoting soft forced / absolute cores; never demote hard floors.
        demote_candidates = []
        for ordinal in sorted(rows):
            row = rows[ordinal]
            if row["final_level"] != "core":
                continue
            reason = row["forced_floor_reason"]
            if reason in HARD_FORCED_REASONS:
                continue
            soft_rank = 0
            if reason in SOFT_FORCED_REASONS:
                soft_rank = FORCED_REASON_PRIORITY.index(reason) if reason in FORCED_REASON_PRIORITY else 50
            else:
                soft_rank = 100
            demote_candidates.append((soft_rank, row["importance_score"], row["percentile"], row))
        demote_candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        for _rank, _score, _pct, row in demote_candidates[:demote_count]:
            row["final_level"] = "secondary"
            row["classification_reasons"].append(
                f"scarcity_demote_{row['forced_floor_reason'] or 'soft_core'}"
            )

    secondary_count = sum(1 for row in rows.values() if row["final_level"] == "secondary")
    secondary_target = max(SECONDARY_SPARSE_MIN, int(round(scene_count * SECONDARY_SPARSE_TARGET_RATIO)))
    if secondary_count < secondary_target:
        promote_candidates = [
            rows[ordinal]
            for ordinal in sorted(rows)
            if rows[ordinal]["final_level"] == "beat"
            and (
                ordinal in phase_end_ordinals
                or ordinal in phase_start_ordinals
                or rows[ordinal]["importance_score"] >= SECONDARY_ABSOLUTE_FLOOR
            )
        ]
        promote_candidates.sort(
            key=lambda item: (item["importance_score"], item["percentile"]),
            reverse=True,
        )
        needed = secondary_target - secondary_count
        for row in promote_candidates[:needed]:
            row["final_level"] = "secondary"
            row["classification_reasons"].append("sparse_secondary_promote")

    return [rows[profile.scene_ordinal] for profile in ordered]


def _chain_scene_ordinals(chain: dict[str, Any] | None) -> set[int]:
    if not chain:
        return set()
    scenes = {int(chain.get("created_scene") or chain.get("created_scene_ordinal") or 0)}
    scenes.update(int(value) for value in chain.get("carried_scene_ordinals") or [])
    scenes.update(int(value) for value in chain.get("transformed_scenes") or [])
    answered = chain.get("answered_scene") or chain.get("answered_scene_ordinal")
    if answered is not None:
        scenes.add(int(answered))
    return {value for value in scenes if value > 0}


def _chain_anchor_ordinals(chain: dict[str, Any] | None) -> set[int]:
    """Create / transform / answer scenes only — excludes mere carry-forward."""
    if not chain:
        return set()
    scenes = {int(chain.get("created_scene") or chain.get("created_scene_ordinal") or 0)}
    scenes.update(int(value) for value in chain.get("transformed_scenes") or [])
    answered = chain.get("answered_scene") or chain.get("answered_scene_ordinal")
    if answered is not None:
        scenes.add(int(answered))
    if str(chain.get("status") or "") in {"transformed", "answered", "partially_answered"}:
        # answered already covered; keep created
        pass
    return {value for value in scenes if value > 0}


def _phase_create_transform_scenes(phase_chains: list[dict[str, Any]]) -> set[int]:
    scenes: set[int] = set()
    for chain in phase_chains:
        created = int(chain.get("created_scene") or chain.get("created_scene_ordinal") or 0)
        if created > 0:
            scenes.add(created)
        scenes.update(int(value) for value in chain.get("transformed_scenes") or [])
        if str(chain.get("status") or "") == "transformed":
            answered = chain.get("answered_scene") or chain.get("answered_scene_ordinal")
            if answered is not None:
                scenes.add(int(answered))
    return scenes


def _next_scene_handoff_visible(
    profile: SceneReaderJourneyProfileItem,
    hook_strength: int,
    profiles_by_ordinal: dict[int, SceneReaderJourneyProfileItem],
) -> bool:
    if hook_strength < HANDOFF_VISIBLE_STRENGTH:
        return False
    next_profile = profiles_by_ordinal.get(profile.scene_ordinal + 1)
    if next_profile is None:
        return False
    for hook in profile.hooks:
        handoff = hook.next_handoff.strip()
        if not handoff:
            continue
        normalized_handoff = _normalize_question(handoff)
        for item in next_profile.reader_question_in:
            if _normalize_question(item.question) in normalized_handoff or normalized_handoff in _normalize_question(
                item.question
            ):
                return True
        for item in next_profile.reader_question_created:
            if _normalize_question(item.question) in normalized_handoff or normalized_handoff in _normalize_question(
                item.question
            ):
                return True
        for item in next_profile.reader_question_out:
            if _normalize_question(item.question) in normalized_handoff or normalized_handoff in _normalize_question(
                item.question
            ):
                return True
    return False


def _hook_suppression_reason(
    *,
    visible: bool,
    strength: int,
    scene_ordinal: int,
    max_ordinal: int,
    phase_end_ordinals: set[int],
    primary_scenes: set[int],
    phase_create_transform: set[int],
    handoff_visible: bool,
) -> str:
    if visible:
        return ""
    if strength >= HOOK_VISIBLE_STRENGTH:
        return "selected_stronger_hook_in_scene"
    if scene_ordinal in primary_scenes:
        return "selected_stronger_hook_in_scene"
    if scene_ordinal in phase_create_transform:
        return "selected_stronger_hook_in_scene"
    if scene_ordinal in phase_end_ordinals or scene_ordinal == max_ordinal:
        return "selected_stronger_hook_in_scene"
    if handoff_visible:
        return "selected_stronger_hook_in_scene"
    if strength < HOOK_VISIBLE_STRENGTH:
        return "below_visible_strength_threshold"
    return "not_primary_or_phase_anchor"


def select_visible_hooks(
    *,
    profiles: list[SceneReaderJourneyProfileItem],
    phase_end_ordinals: set[int],
    max_ordinal: int,
    primary_chain: dict[str, Any] | None,
    phase_chains: list[dict[str, Any]],
) -> dict[str, Any]:
    """Select one visible hook marker per scene for the main chart."""
    ordered = sorted(profiles, key=lambda item: item.scene_ordinal)
    profiles_by_ordinal = {profile.scene_ordinal: profile for profile in ordered}
    primary_scenes = _chain_anchor_ordinals(primary_chain)
    phase_create_transform = _phase_create_transform_scenes(phase_chains)

    all_hook_count = sum(len(profile.hooks) for profile in ordered)
    hook_markers: list[dict[str, Any]] = []
    suppressed_hooks: list[dict[str, Any]] = []

    for profile in ordered:
        if not profile.hooks:
            continue
        strongest = max(profile.hooks, key=lambda item: item.strength)
        strength = int(strongest.strength)
        handoff_visible = _next_scene_handoff_visible(profile, strength, profiles_by_ordinal)
        visible = (
            strength >= HOOK_VISIBLE_STRENGTH
            or profile.scene_ordinal in primary_scenes
            or profile.scene_ordinal in phase_create_transform
            or profile.scene_ordinal in phase_end_ordinals
            or profile.scene_ordinal == max_ordinal
            or handoff_visible
        )
        marker = {
            "scene_ordinal": profile.scene_ordinal,
            "scene_id": profile.scene_id,
            "type": strongest.type,
            "summary": strongest.summary,
            "gap": strongest.gap,
            "continue_drive": strongest.continue_drive,
            "strength": strength,
            "evidence_paragraph_ids": list(strongest.evidence_paragraph_ids),
            "visible": visible,
        }
        if visible:
            hook_markers.append(marker)
        else:
            suppressed_hooks.append(
                {
                    **marker,
                    "suppression_reason": _hook_suppression_reason(
                        visible=False,
                        strength=strength,
                        scene_ordinal=profile.scene_ordinal,
                        max_ordinal=max_ordinal,
                        phase_end_ordinals=phase_end_ordinals,
                        primary_scenes=primary_scenes,
                        phase_create_transform=phase_create_transform,
                        handoff_visible=handoff_visible,
                    ),
                }
            )

        for hook in profile.hooks:
            if hook is strongest:
                continue
            suppressed_hooks.append(
                {
                    "scene_ordinal": profile.scene_ordinal,
                    "scene_id": profile.scene_id,
                    "type": hook.type,
                    "summary": hook.summary,
                    "gap": hook.gap,
                    "continue_drive": hook.continue_drive,
                    "strength": int(hook.strength),
                    "evidence_paragraph_ids": list(hook.evidence_paragraph_ids),
                    "visible": False,
                    "suppression_reason": "selected_stronger_hook_in_scene",
                }
            )

    visible_hook_count = len(hook_markers)
    # Density guard: demote weakest strength-only markers when over ratio.
    scene_count = max(len(ordered), 1)
    if visible_hook_count / scene_count > HOOK_VISIBLE_MAX_RATIO:
        structural = (
            primary_scenes
            | phase_create_transform
            | phase_end_ordinals
            | {max_ordinal}
        )
        soft = [
            marker
            for marker in hook_markers
            if marker["scene_ordinal"] not in structural
        ]
        soft.sort(key=lambda item: (int(item["strength"]), int(item["scene_ordinal"])))
        while soft and len(hook_markers) / scene_count > HOOK_VISIBLE_MAX_RATIO:
            victim = soft.pop(0)
            hook_markers = [item for item in hook_markers if item is not victim]
            suppressed_hooks.append(
                {
                    **victim,
                    "visible": False,
                    "suppression_reason": "density_suppress_strength_only",
                }
            )
        visible_hook_count = len(hook_markers)

    return {
        "all_hook_count": all_hook_count,
        "visible_hook_count": visible_hook_count,
        "suppressed_hook_count": all_hook_count - visible_hook_count,
        "hook_markers": hook_markers,
        "suppressed_hooks": suppressed_hooks,
        "formula_version": HOOK_SELECT_FORMULA_VERSION,
    }


def _dedupe_key(*, scene_ordinal: int, payoff_type: str, summary: str) -> tuple[int, str, str]:
    return scene_ordinal, payoff_type, _normalize_question(summary)


def _derive_micro_payoffs(profile: SceneReaderJourneyProfileItem) -> list[dict[str, Any]]:
    derived: list[dict[str, Any]] = []
    for answered in profile.reader_question_answered:
        derived.append(
            {
                "source_type": "reader_question_answered",
                "source_scene_id": profile.scene_id,
                "scene_ordinal": profile.scene_ordinal,
                "payoff_type": "information",
                "summary": answered.answer_summary,
                "strength": ANSWER_DEGREE_STRENGTH.get(answered.answer_degree, 55),
                "evidence_ids": list(answered.evidence_paragraph_ids),
                "derivation_rule": f"reader_question_answered:{answered.answer_degree}",
                "confidence": 0.85 if answered.answer_degree == "full" else 0.72,
            }
        )
    for change in profile.information_changes:
        mapping = INFO_CHANGE_DERIVATION.get(change.type)
        if mapping is None:
            continue
        payoff_type, strength, confidence = mapping
        derived.append(
            {
                "source_type": "information_change",
                "source_scene_id": profile.scene_id,
                "scene_ordinal": profile.scene_ordinal,
                "payoff_type": payoff_type,
                "summary": change.summary,
                "strength": strength,
                "evidence_ids": list(change.evidence_paragraph_ids),
                "derivation_rule": f"information_change:{change.type}",
                "confidence": confidence,
            }
        )
    return derived


def _semantic_payoff_records(profile: SceneReaderJourneyProfileItem) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for payoff in profile.payoffs:
        records.append(
            {
                "source_type": "semantic",
                "source_scene_id": profile.scene_id,
                "scene_ordinal": profile.scene_ordinal,
                "payoff_type": payoff.type,
                "summary": payoff.summary,
                "strength": int(payoff.strength),
                "evidence_ids": list(payoff.evidence_paragraph_ids),
                "derivation_rule": "profile.payoffs",
                "confidence": 0.9,
            }
        )
    return records


def _phase_end_ordinals(phases: list[Any]) -> dict[int, dict[str, Any]]:
    by_end: dict[int, dict[str, Any]] = {}
    for phase in phases:
        if isinstance(phase, dict):
            end = int(phase.get("end_scene_ordinal") or 0)
            payload = phase
        else:
            end = int(getattr(phase, "end_scene_ordinal", 0) or 0)
            payload = {
                "ordinal": getattr(phase, "ordinal", None),
                "end_scene_ordinal": end,
                "reading_payoff": getattr(phase, "reading_payoff", ""),
                "primary_reader_question": getattr(phase, "primary_reader_question", ""),
            }
        if end > 0:
            by_end[end] = payload
    return by_end


def derive_and_select_payoffs(
    *,
    profiles: list[SceneReaderJourneyProfileItem],
    phases: list[Any],
    max_ordinal: int,
) -> dict[str, Any]:
    """Derive micro payoffs from existing profile fields and select visible markers."""
    ordered = sorted(profiles, key=lambda item: item.scene_ordinal)
    semantic_payoffs: list[dict[str, Any]] = []
    derived_micro_payoffs: list[dict[str, Any]] = []
    for profile in ordered:
        semantic_payoffs.extend(_semantic_payoff_records(profile))
        derived_micro_payoffs.extend(_derive_micro_payoffs(profile))
        if profile.information_gain_score >= 60 and not profile.payoffs:
            derived_micro_payoffs.append(
                {
                    "source_type": "information_gain_score",
                    "source_scene_id": profile.scene_id,
                    "scene_ordinal": profile.scene_ordinal,
                    "payoff_type": "information",
                    "summary": profile.scene_value_summary or "信息增益兑现",
                    "strength": min(70, int(profile.information_gain_score)),
                    "evidence_ids": list(profile.evidence_paragraph_ids)[:4],
                    "derivation_rule": "information_gain_score>=60",
                    "confidence": 0.58,
                }
            )

    # Phase reading_payoff as stage-level derived markers (no invented prose beyond phase field).
    for phase in phases:
        if isinstance(phase, dict):
            end = int(phase.get("end_scene_ordinal") or 0)
            reading = str(phase.get("reading_payoff") or "").strip()
            scene_id = int(phase.get("end_scene_id") or 0)
        else:
            end = int(getattr(phase, "end_scene_ordinal", 0) or 0)
            reading = str(getattr(phase, "reading_payoff", "") or "").strip()
            scene_id = 0
        if end <= 0 or not reading:
            continue
        profile = next((item for item in ordered if item.scene_ordinal == end), None)
        derived_micro_payoffs.append(
            {
                "source_type": "phase_reading_payoff",
                "source_scene_id": profile.scene_id if profile else scene_id,
                "scene_ordinal": end,
                "payoff_type": "stage_completion",
                "summary": reading,
                "strength": 66,
                "evidence_ids": list(profile.evidence_paragraph_ids)[:4] if profile else [],
                "derivation_rule": "phase.reading_payoff",
                "confidence": 0.7,
            }
        )

    deduped: dict[tuple[int, str, str], dict[str, Any]] = {}
    for record in semantic_payoffs + derived_micro_payoffs:
        key = _dedupe_key(
            scene_ordinal=int(record["scene_ordinal"]),
            payoff_type=str(record["payoff_type"]),
            summary=str(record["summary"]),
        )
        existing = deduped.get(key)
        if existing is None or int(record["strength"]) > int(existing["strength"]):
            deduped[key] = record
    all_payoffs = list(deduped.values())

    phase_by_end = _phase_end_ordinals(phases)
    visible_payoff_markers: list[dict[str, Any]] = []
    seen_scenes: set[int] = set()
    for record in sorted(all_payoffs, key=lambda item: (-int(item["strength"]), int(item["scene_ordinal"]))):
        scene_ordinal = int(record["scene_ordinal"])
        strength = int(record["strength"])
        phase = phase_by_end.get(scene_ordinal)
        derivation = str(record.get("derivation_rule", ""))
        answered_payoff = derivation.startswith("reader_question_answered")
        answer_degree = derivation.split(":")[-1]
        high_value_type = str(record.get("payoff_type")) in {
            "identity",
            "rule",
            "horror_payoff",
            "stage_completion",
        }
        visible = (
            strength >= PAYOFF_VISIBLE_STRENGTH
            or strength >= STRONG_PAYOFF_FLOOR
            or (answered_payoff and answer_degree in {"full", "partial"})
            or phase is not None
            or scene_ordinal == max_ordinal
            or scene_ordinal == max_ordinal - 1
            or record.get("source_type") == "semantic"
            or record.get("source_type") == "phase_reading_payoff"
            or (high_value_type and strength >= 50)
            or derivation.startswith("information_change:confirmation")
            or derivation.startswith("information_change:identity_clue")
            or derivation.startswith("information_change:rule_clue")
        )
        if not visible:
            continue
        # One primary visible marker per scene on the main chart.
        if scene_ordinal in seen_scenes:
            continue
        seen_scenes.add(scene_ordinal)
        visible_payoff_markers.append(
            {
                "scene_ordinal": scene_ordinal,
                "scene_id": record["source_scene_id"],
                "type": record["payoff_type"],
                "summary": record["summary"],
                "strength": strength,
                "source_type": record["source_type"],
                "derivation_rule": record["derivation_rule"],
                "evidence_paragraph_ids": list(record["evidence_ids"]),
                "confidence": record["confidence"],
            }
        )

    visible_payoff_markers.sort(
        key=lambda item: (-int(item["strength"]), int(item["scene_ordinal"]))
    )
    return {
        "semantic_payoffs": semantic_payoffs,
        "derived_micro_payoffs": derived_micro_payoffs,
        "all_payoffs": all_payoffs,
        "visible_payoff_markers": visible_payoff_markers,
        "semantic_payoff_count": len(semantic_payoffs),
        "derived_payoff_count": len(derived_micro_payoffs),
        "deduped_payoff_count": len(all_payoffs),
        "visible_payoff_count": len(visible_payoff_markers),
        "formula_version": PAYOFF_DERIVE_FORMULA_VERSION,
    }


def _cluster_id(cluster_type: str, primary_question: str, created_scene: int) -> str:
    digest = hashlib.sha256(
        f"{cluster_type}:{created_scene}:{_normalize_question(primary_question)}".encode()
    ).hexdigest()[:16]
    return f"qcl-{digest}"


def _chain_member_payload(chain: dict[str, Any], *, relationship: str) -> dict[str, Any]:
    question = str(chain.get("canonical_question") or chain.get("question_summary") or "")
    chain_id = str(chain.get("canonical_id") or chain.get("question_chain_id") or "")
    return {
        "chain_id": chain_id,
        "question": question,
        "relationship": relationship,
        "importance": int(chain.get("importance") or chain.get("strength") or 0),
        "created_scene": int(chain.get("created_scene") or chain.get("created_scene_ordinal") or 0),
        "status": str(chain.get("status") or "created"),
    }


CLUSTER_ANCHOR_TERMS: tuple[str, ...] = (
    "陈伶",
    "原主",
    "少年",
    "戏鬼",
    "水鬼",
    "父母",
    "母亲",
    "父亲",
    "戏袍",
    "昨晚",
    "被杀",
    "呼唤",
    "记忆",
    "噪音",
    "穿越",
    "儿子",
    "身份",
)


def _shared_anchor_terms(left: str, right: str, *, corpus_anchors: set[str] | None = None) -> set[str]:
    anchors = set(CLUSTER_ANCHOR_TERMS)
    if corpus_anchors:
        anchors |= corpus_anchors
    return {term for term in anchors if term in left and term in right}


def _discover_corpus_anchors(ranked_chains: list[dict[str, Any]]) -> set[str]:
    """Keep seeded anchors that recur in the corpus (freq >= 2)."""
    from collections import Counter

    freq: Counter[str] = Counter()
    for chain in ranked_chains:
        question = str(chain.get("canonical_question") or chain.get("question_summary") or "")
        for term in CLUSTER_ANCHOR_TERMS:
            if term in question:
                freq[term] += 1
    return {token for token, count in freq.items() if count >= 2}


def _can_cluster(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    corpus_anchors: set[str] | None = None,
) -> tuple[bool, float, str]:
    left_q = str(left.get("canonical_question") or left.get("question_summary") or "")
    right_q = str(right.get("canonical_question") or right.get("question_summary") or "")
    left_type = str(left.get("question_type") or classify_question_type(left_q))
    right_type = str(right.get("question_type") or classify_question_type(right_q))
    strong_shared = _shared_anchor_terms(left_q, right_q, corpus_anchors=corpus_anchors)
    _score, confidence, relationship = _question_similarity(left_q, right_q)

    if relationship == "alias" and confidence >= CLUSTER_CONFIDENCE_FLOOR:
        if left_type != right_type and not strong_shared:
            # Identical wording across unrelated types is still refinement only with anchors.
            if _normalize_question(left_q) != _normalize_question(right_q):
                return False, confidence, "question_type_mismatch"
        return True, confidence, "alias" if left_type == right_type else "refinement"

    if strong_shared and confidence >= 0.35:
        if left_type != right_type:
            related = {
                frozenset({"identity", "information"}),
                frozenset({"identity", "other"}),
                frozenset({"danger", "information"}),
                frozenset({"danger", "other"}),
                frozenset({"information", "other"}),
                frozenset({"relationship", "identity"}),
                frozenset({"relationship", "other"}),
                frozenset({"goal", "other"}),
            }
            if frozenset({left_type, right_type}) not in related:
                return False, confidence, "question_type_mismatch"
        return True, max(confidence, 0.55), "escalation"

    return False, confidence, relationship


def build_question_clusters(
    ranked_chains: list[dict[str, Any]],
    *,
    phase_boundaries: list[dict[str, int]],
) -> dict[str, Any]:
    """Group ranked chains into question clusters for the main chart."""
    if not ranked_chains:
        return {
            "question_clusters": [],
            "visible_question_clusters": [],
            "question_cluster_count": 0,
            "visible_question_cluster_count": 0,
            "formula_version": CLUSTER_FORMULA_VERSION,
        }

    corpus_anchors = _discover_corpus_anchors(ranked_chains)
    # Greedy assignment (no transitive union) to avoid mega-clusters via weak bridges.
    clusters: list[dict[str, Any]] = []
    for chain in ranked_chains:
        best_index: int | None = None
        best_confidence = -1.0
        best_relationship = "below_threshold"
        for index, cluster in enumerate(clusters):
            primary_chain = next(
                (
                    item
                    for item in ranked_chains
                    if str(item.get("canonical_id") or item.get("question_chain_id") or "")
                    == cluster["primary_chain_id"]
                ),
                None,
            )
            if primary_chain is None:
                primary_chain = {
                    "canonical_question": cluster["primary_question"],
                    "question_type": cluster["cluster_type"],
                    "canonical_id": cluster["primary_chain_id"],
                }
            ok, confidence, relationship = _can_cluster(
                primary_chain,
                chain,
                corpus_anchors=corpus_anchors,
            )
            if not ok:
                continue
            if confidence > best_confidence:
                best_index = index
                best_confidence = confidence
                best_relationship = relationship
        if best_index is None:
            question = str(chain.get("canonical_question") or chain.get("question_summary") or "")
            cluster_type = str(chain.get("question_type") or classify_question_type(question))
            created_scene = int(chain.get("created_scene") or chain.get("created_scene_ordinal") or 0)
            chain_id = str(chain.get("canonical_id") or chain.get("question_chain_id") or "")
            clusters.append(
                {
                    "cluster_id": _cluster_id(cluster_type, question, created_scene),
                    "cluster_type": cluster_type,
                    "cluster_title": question,
                    "member_chain_ids": [chain_id],
                    "primary_chain_id": chain_id,
                    "members": [_chain_member_payload(chain, relationship="primary")],
                    "relationships": [],
                    "confidence": 1.0,
                    "merge_reason": "singleton",
                    "importance": int(chain.get("importance") or chain.get("strength") or 0),
                    "created_scene": created_scene,
                    "primary_question": question,
                    "_primary_chain": chain,
                }
            )
            continue

        cluster = clusters[best_index]
        chain_id = str(chain.get("canonical_id") or chain.get("question_chain_id") or "")
        if chain_id in cluster["member_chain_ids"]:
            continue
        cluster["member_chain_ids"].append(chain_id)
        cluster["members"].append(_chain_member_payload(chain, relationship=best_relationship))
        cluster["relationships"].append(
            {
                "from_chain_id": chain_id,
                "to_chain_id": cluster["primary_chain_id"],
                "relationship": best_relationship,
            }
        )
        cluster["confidence"] = round(min(float(cluster["confidence"]), best_confidence), 2)
        if best_relationship == "escalation":
            cluster["merge_reason"] = "escalation"
        elif cluster["merge_reason"] == "singleton":
            cluster["merge_reason"] = best_relationship
        # Keep highest-importance chain as primary title.
        if int(chain.get("importance") or chain.get("strength") or 0) > int(cluster["importance"]):
            question = str(chain.get("canonical_question") or chain.get("question_summary") or "")
            cluster["importance"] = int(chain.get("importance") or chain.get("strength") or 0)
            cluster["cluster_title"] = question
            cluster["primary_question"] = question
            cluster["primary_chain_id"] = chain_id
            cluster["cluster_type"] = str(
                chain.get("question_type") or classify_question_type(question)
            )
            cluster["created_scene"] = int(
                chain.get("created_scene") or chain.get("created_scene_ordinal") or 0
            )
            cluster["_primary_chain"] = chain
            cluster["cluster_id"] = _cluster_id(
                cluster["cluster_type"], question, cluster["created_scene"]
            )

    for cluster in clusters:
        cluster.pop("_primary_chain", None)

    clusters.sort(key=lambda item: (-int(item["importance"]), item["created_scene"], item["cluster_id"]))

    visible: list[dict[str, Any]] = []
    if clusters:
        visible.append(clusters[0])

    def _phase_for_scene(scene_ordinal: int) -> int | None:
        for phase in phase_boundaries:
            if phase["start_scene_ordinal"] <= scene_ordinal <= phase["end_scene_ordinal"]:
                return int(phase["ordinal"])
        return None

    used_phases: set[int] = set()
    for cluster in clusters[1:]:
        if len(visible) >= MAX_VISIBLE_CLUSTERS:
            break
        phase_id = _phase_for_scene(int(cluster["created_scene"]))
        if phase_id is None or phase_id in used_phases:
            continue
        visible.append(cluster)
        used_phases.add(phase_id)

    visible_ids = {item["cluster_id"] for item in visible}
    for cluster in clusters:
        if len(visible) >= MAX_VISIBLE_CLUSTERS:
            break
        if cluster["cluster_id"] in visible_ids:
            continue
        visible.append(cluster)
        visible_ids.add(cluster["cluster_id"])

    return {
        "question_clusters": clusters,
        "visible_question_clusters": visible[:MAX_VISIBLE_CLUSTERS],
        "question_cluster_count": len(clusters),
        "visible_question_cluster_count": min(len(visible), MAX_VISIBLE_CLUSTERS),
        "formula_version": CLUSTER_FORMULA_VERSION,
    }


def build_density_warnings(
    *,
    scene_count: int,
    role_counts: dict[str, int],
    visible_hook_count: int,
    visible_cluster_count: int,
) -> list[dict[str, str]]:
    """Emit deterministic visual density warnings for suspicious distributions."""
    warnings: list[dict[str, str]] = []
    if scene_count <= 0:
        return warnings

    core_ratio = role_counts.get("core", 0) / scene_count
    if core_ratio > CORE_WARNING_RATIO:
        warnings.append(
            {
                "code": "VISUAL_CORE_DISTRIBUTION_SUSPICIOUS",
                "message": (
                    f"Core scenes占{role_counts.get('core', 0)}/{scene_count} "
                    f"({core_ratio:.0%})，超过目标上限{CORE_WARNING_RATIO:.0%}"
                ),
            }
        )

    hook_ratio = visible_hook_count / scene_count
    if hook_ratio > HOOK_VISIBLE_MAX_RATIO:
        warnings.append(
            {
                "code": "VISUAL_HOOK_DISTRIBUTION_SUSPICIOUS",
                "message": (
                    f"可见Hook占{visible_hook_count}/{scene_count} "
                    f"({hook_ratio:.0%})，超过目标上限{HOOK_VISIBLE_MAX_RATIO:.0%}"
                ),
            }
        )

    _ = visible_cluster_count
    return warnings
