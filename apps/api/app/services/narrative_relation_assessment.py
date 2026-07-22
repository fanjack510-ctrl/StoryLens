"""Multi-dimensional Hook→Payoff relation assessment (presentation only).

Does not modify model prompts, formula weights for journey scores, or stored
artifacts. Produces ranked candidate relations for UI drawing.
"""

from __future__ import annotations

import re
from typing import Any

# Centralized presentation weights — do not scatter in call sites.
RELATION_WEIGHTS: dict[str, float] = {
    "semantic_response": 25.0,
    "entity_continuity": 15.0,
    "causal_continuity": 20.0,
    "expectation_match": 15.0,
    "evidence_completeness": 15.0,
    "distance_reasonableness": 5.0,
    "data_consistency": 5.0,
}

GRADE_CONFIRMED = "confirmed"
GRADE_PROBABLE = "probable"
GRADE_CANDIDATE = "candidate"
GRADE_UNSUPPORTED = "unsupported"

GRADE_LABELS_ZH: dict[str, str] = {
    GRADE_CONFIRMED: "明确回应",
    GRADE_PROBABLE: "较可信回应",
    GRADE_CANDIDATE: "候选回应",
    GRADE_UNSUPPORTED: "尚未找到可信回应",
}

SOFT_CONFLICT_USER_MESSAGE = "系统找到较可信的承接，但部分分析结果仍存在分歧。"
HARD_BLOCK_USER_MESSAGE = "当前关系识别存在严重冲突，暂不作为确定结论。"

HARD_BLOCK_CODES = frozenset(
    {
        "scope_book_mismatch",
        "scope_chapter_mismatch",
        "run_mismatch",
        "fingerprint_mismatch",
        "data_integrity_failed",
        "cross_book_contamination",
        "no_text_evidence",
    }
)

SOFT_CONFLICT_CODES = frozenset(
    {
        "payoff_score_without_entity",
        "payoff_entity_without_evidence",
        "hook_without_question",
        "risk_no_payoff_but_loop_resolved",
        "score_entity_divergence",
    }
)

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]{2,}")


def _tokens(text: str | None) -> set[str]:
    """Tokenize for overlap: latin words + Chinese character bigrams."""
    raw = (text or "").lower().strip()
    if not raw:
        return set()
    out: set[str] = set(_TOKEN_RE.findall(raw))
    # Contiguous CJK runs become one regex match; add bigrams for overlap.
    cjk = re.findall(r"[\u4e00-\u9fff]+", raw)
    for run in cjk:
        if len(run) == 1:
            out.add(run)
        else:
            for i in range(len(run) - 1):
                out.add(run[i : i + 2])
            if len(run) >= 3:
                out.add(run[:3])
    return out


def _clip(text: str, max_chars: int = 120) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1] + "…"


def grade_from_total(total: float) -> str:
    if total >= 80:
        return GRADE_CONFIRMED
    if total >= 60:
        return GRADE_PROBABLE
    if total >= 40:
        return GRADE_CANDIDATE
    return GRADE_UNSUPPORTED


def is_hard_block(conflicts: list[dict[str, Any]] | None) -> bool:
    for item in conflicts or []:
        code = str(item.get("code") or "")
        if code in HARD_BLOCK_CODES:
            return True
        if code.startswith("scope_") or "cross_book" in code:
            return True
    return False


def classify_conflicts(
    conflicts: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hard: list[dict[str, Any]] = []
    soft: list[dict[str, Any]] = []
    for item in conflicts or []:
        code = str(item.get("code") or "")
        if code in HARD_BLOCK_CODES or code.startswith("scope_") or "cross_book" in code:
            hard.append(item)
        else:
            soft.append(item)
    return hard, soft


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _semantic_response_score(
    question: str,
    gap: str,
    payoff_summary: str,
    payoff_type: str | None,
) -> tuple[float, str]:
    q_tokens = _tokens(question) | _tokens(gap)
    p_tokens = _tokens(payoff_summary)
    overlap = _jaccard(q_tokens, p_tokens)
    shared = q_tokens & p_tokens
    kind = (payoff_type or "").lower()
    # Score-only synthetic answers get lower semantic ceiling.
    if kind == "score_inferred":
        base = 45.0 + overlap * 25.0 + (8.0 if shared else 0.0)
        return min(70.0, base), "分数信号提示回应，但缺少实体摘要"

    type_base = {
        "full": 62.0,
        "partial": 48.0,
        "reversal": 55.0,
        "transformed_question": 52.0,
    }.get(kind, 28.0 if payoff_summary.strip() else 8.0)

    score = type_base + overlap * 40.0
    if shared:
        # Shared object/topic tokens matter more than pure Jaccard on short Chinese.
        score += min(25.0, 6.0 * len(shared))
    if kind == "full" and shared:
        score = max(score, 82.0)
    score = min(100.0, score)
    if shared and kind in {"full", "partial", "reversal", "transformed_question"}:
        return max(score, 58.0), "回应摘要与问题/缺口存在共享话题"
    if overlap >= 0.2:
        return score, "回应摘要与问题/缺口语义相关"
    if overlap >= 0.08 or shared:
        return max(score, 45.0), "回应与问题有部分语义重叠"
    if payoff_summary.strip():
        return max(32.0, score), "存在回应文本但语义重叠较弱"
    return 10.0, "缺少可核对的回应摘要"


def _entity_continuity_score(
    hook_summaries: list[str],
    question: str,
    payoff_summary: str,
) -> tuple[float, str]:
    hook_tokens: set[str] = set()
    for item in hook_summaries:
        hook_tokens |= _tokens(item)
    hook_tokens |= _tokens(question)
    p_tokens = _tokens(payoff_summary)
    overlap = _jaccard(hook_tokens, p_tokens)
    shared = hook_tokens & p_tokens
    if overlap >= 0.25 or len(shared) >= 2:
        return min(100.0, 70.0 + overlap * 40.0 + 5.0 * len(shared)), "对象/实体有连续提及"
    if shared:
        return min(100.0, 75.0 + 4.0 * len(shared)), "对象连续较弱但仍相关"
    if overlap >= 0.1:
        return 55.0, "对象连续较弱但仍相关"
    if not hook_tokens:
        return 40.0, "缺少钩子实体，连续性无法确认"
    return 20.0, "同对象连续性不足"


def _expectation_match_score(
    question: str,
    gap: str,
    continue_drive: str,
    payoff_summary: str,
    payoff_type: str | None,
) -> tuple[float, str]:
    expect_tokens = _tokens(question) | _tokens(gap) | _tokens(continue_drive)
    p_tokens = _tokens(payoff_summary)
    overlap = _jaccard(expect_tokens, p_tokens)
    shared = expect_tokens & p_tokens
    kind = (payoff_type or "").lower()
    if kind == "full":
        return (90.0 if (overlap >= 0.12 or shared) else 72.0), "完整兑现匹配读者期待"
    if kind == "partial":
        return 70.0 if (overlap >= 0.08 or shared) else 55.0, "部分回应，期待尚未完全满足"
    if kind == "reversal":
        return 75.0, "反转式回应仍对期待作出处理"
    if kind == "transformed_question":
        return 68.0, "转化为新问题，原期待被改写"
    if kind == "score_inferred":
        return 50.0, "仅有分数提示，期待匹配待核对"
    if overlap >= 0.2 or shared:
        return 80.0, "回应覆盖读者等待点"
    return 35.0, "回应与读者期待匹配较弱"


def _causal_continuity_score(
    hook_scene: int | None,
    payoff_scene: int | None,
    developments: list[int],
    payoff_type: str | None,
) -> tuple[float, str]:
    if hook_scene is None or payoff_scene is None:
        return 25.0, "缺少场景顺序，因果难确认"
    if payoff_scene < hook_scene:
        return 5.0, "回应场景早于钩子，因果不合理"
    gap = payoff_scene - hook_scene
    between = [d for d in developments if hook_scene < d < payoff_scene]
    score = 70.0
    if gap == 0:
        score = 85.0
        reason = "同场或紧邻回应"
    elif gap == 1:
        score = 90.0
        reason = "下一场直接回应"
    elif between:
        score = 80.0
        reason = "经发展节点后回应"
    elif gap <= 3:
        score = 65.0
        reason = "短距离后回应"
    else:
        score = 45.0
        reason = "回应距离偏远"
    if (payoff_type or "").lower() in {"reversal", "transformed_question"}:
        score = min(100.0, score + 5.0)
    return score, reason


def _evidence_completeness_score(
    evidence_ids: list[str] | None,
    *,
    has_entity: bool,
) -> tuple[float, str]:
    ids = [str(x).strip() for x in (evidence_ids or []) if str(x).strip()]
    if ids:
        return min(100.0, 60.0 + 10.0 * len(ids)), "具备正文证据定位"
    if has_entity:
        return 35.0, "有回应实体但缺少证据"
    return 15.0, "无实体且无证据"


def _distance_reasonableness_score(
    hook_scene: int | None,
    payoff_scene: int | None,
) -> tuple[float, str]:
    if hook_scene is None or payoff_scene is None:
        return 40.0, "距离未知"
    gap = payoff_scene - hook_scene
    if gap < 0:
        return 0.0, "顺序倒置"
    if gap <= 2:
        return 95.0, "距离合理"
    if gap <= 5:
        return 70.0, "距离尚可"
    if gap <= 10:
        return 45.0, "距离偏长"
    return 20.0, "距离过远"


def _data_consistency_score(
    *,
    has_entity: bool,
    payoff_score: int | None,
    evidence_ids: list[str] | None,
    soft_conflicts: list[dict[str, Any]],
) -> tuple[float, str]:
    score = 90.0
    reasons: list[str] = []
    if payoff_score is not None and payoff_score >= 70 and not has_entity:
        score -= 35.0
        reasons.append("高分无实体")
    if has_entity and not (evidence_ids or []):
        score -= 25.0
        reasons.append("实体无证据")
    if soft_conflicts:
        score -= min(30.0, 8.0 * len(soft_conflicts))
        reasons.append("存在软分歧")
    score = max(0.0, min(100.0, score))
    return score, "；".join(reasons) if reasons else "数据字段基本一致"


def assess_hook_payoff_relation(
    *,
    loop_id: str,
    question: str,
    information_gap: str,
    hook: dict[str, Any] | None,
    payoff: dict[str, Any] | None,
    developments: list[int],
    payoff_score: int | None,
    soft_conflicts: list[dict[str, Any]] | None = None,
    hard_conflicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score one candidate Hook→Payoff relation."""
    hard = list(hard_conflicts or [])
    soft = list(soft_conflicts or [])
    if hard:
        return {
            "loop_id": loop_id,
            "grade": GRADE_UNSUPPORTED,
            "total_score": 0.0,
            "blocked": True,
            "block_level": "hard",
            "label_zh": HARD_BLOCK_USER_MESSAGE,
            "dimensions": {},
            "reasons": [str(item.get("message") or item.get("code")) for item in hard],
            "conflicts": hard + soft,
            "is_primary": False,
            "payoff_ref": payoff,
            "hook_ref": hook,
        }

    hook = hook or {}
    payoff = payoff or {}
    has_entity = bool(payoff.get("summary") or payoff.get("source_type") not in {None, "score_inferred"})
    if payoff.get("source_type") == "score_inferred":
        has_entity = False

    hook_scene = hook.get("scene_ordinal")
    payoff_scene = payoff.get("scene_ordinal")
    evidence_ids = list(payoff.get("evidence_paragraph_ids") or [])
    payoff_type = str(payoff.get("type") or "")
    payoff_summary = str(payoff.get("summary") or "")
    continue_drive = str(hook.get("continue_drive") or "")
    hook_summaries = [str(hook.get("summary") or ""), str(hook.get("gap") or "")]

    dims: dict[str, dict[str, Any]] = {}
    semantic, r1 = _semantic_response_score(question, information_gap, payoff_summary, payoff_type)
    dims["semantic_response"] = {"score": semantic, "reason": r1}
    entity, r2 = _entity_continuity_score(hook_summaries, question, payoff_summary)
    dims["entity_continuity"] = {"score": entity, "reason": r2}
    causal, r3 = _causal_continuity_score(
        int(hook_scene) if hook_scene is not None else None,
        int(payoff_scene) if payoff_scene is not None else None,
        developments,
        payoff_type,
    )
    dims["causal_continuity"] = {"score": causal, "reason": r3}
    expect, r4 = _expectation_match_score(
        question, information_gap, continue_drive, payoff_summary, payoff_type
    )
    dims["expectation_match"] = {"score": expect, "reason": r4}
    evidence, r5 = _evidence_completeness_score(evidence_ids, has_entity=has_entity or bool(payoff_summary))
    dims["evidence_completeness"] = {"score": evidence, "reason": r5}
    distance, r6 = _distance_reasonableness_score(
        int(hook_scene) if hook_scene is not None else None,
        int(payoff_scene) if payoff_scene is not None else None,
    )
    dims["distance_reasonableness"] = {"score": distance, "reason": r6}
    consistency, r7 = _data_consistency_score(
        has_entity=has_entity or bool(payoff.get("source_type") not in {None, "score_inferred"}),
        payoff_score=payoff_score,
        evidence_ids=evidence_ids,
        soft_conflicts=soft,
    )
    # For score_inferred, treat as soft divergence on consistency.
    if payoff.get("source_type") == "score_inferred":
        consistency = min(consistency, 40.0)
        r7 = "高分无实体（分数推断候选）"
    dims["data_consistency"] = {"score": consistency, "reason": r7}

    total = 0.0
    weight_sum = sum(RELATION_WEIGHTS.values()) or 100.0
    for key, weight in RELATION_WEIGHTS.items():
        total += (dims[key]["score"] / 100.0) * weight
    total = round(100.0 * total / weight_sum, 1)
    grade = grade_from_total(total)

    # Soft conflicts never elevate to confirmed.
    if soft and grade == GRADE_CONFIRMED:
        grade = GRADE_PROBABLE
        total = min(total, 79.0)

    reasons = [dims[k]["reason"] for k in RELATION_WEIGHTS]
    label = GRADE_LABELS_ZH[grade]
    if soft and grade in {GRADE_PROBABLE, GRADE_CANDIDATE, GRADE_CONFIRMED}:
        label = SOFT_CONFLICT_USER_MESSAGE

    return {
        "loop_id": loop_id,
        "grade": grade,
        "total_score": total,
        "blocked": False,
        "block_level": "soft" if soft else "none",
        "label_zh": label,
        "grade_label_zh": GRADE_LABELS_ZH[grade],
        "dimensions": dims,
        "reasons": reasons,
        "conflicts": soft,
        "is_primary": False,
        "payoff_ref": {
            "scene_ordinal": payoff.get("scene_ordinal"),
            "type": payoff.get("type"),
            "summary": _clip(str(payoff.get("summary") or ""), 120),
            "source_type": payoff.get("source_type"),
            "evidence_paragraph_ids": evidence_ids[:8],
        },
        "hook_ref": {
            "scene_ordinal": hook.get("scene_ordinal"),
            "summary": _clip(str(hook.get("summary") or ""), 120),
            "gap": _clip(str(hook.get("gap") or ""), 80),
        },
        "weights": dict(RELATION_WEIGHTS),
    }


def _synthetic_score_payoffs(loop: dict[str, Any]) -> list[dict[str, Any]]:
    """When high payoff_score exists without entities, emit score-inferred candidates."""
    out: list[dict[str, Any]] = []
    if loop.get("payoffs"):
        return out
    for key, score in (loop.get("payoff_score_by_scene") or {}).items():
        try:
            scene = int(key)
            value = int(score)
        except (TypeError, ValueError):
            continue
        if value < 40:
            continue
        out.append(
            {
                "scene_ordinal": scene,
                "type": "score_inferred",
                "source_type": "score_inferred",
                "summary": "",
                "strength": value,
                "evidence_paragraph_ids": [],
            }
        )
    return out


def reconcile_loop_relations(loop: dict[str, Any]) -> dict[str, Any]:
    """Attach ranked relations and display_status to a NarrativeLoopView dict."""
    hard, soft = classify_conflicts(loop.get("conflicts"))
    # Scope fields on loop.scope may also signal hard blocks.
    scope = loop.get("scope") or {}
    if scope.get("hard_block"):
        hard.append(
            {
                "code": str(scope.get("hard_block_code") or "data_integrity_failed"),
                "message": str(scope.get("hard_block_message") or HARD_BLOCK_USER_MESSAGE),
            }
        )

    hook = (loop.get("hook") or [None])[0]
    developments = [
        int(item.get("scene_ordinal"))
        for item in (loop.get("developments") or [])
        if item.get("scene_ordinal") is not None
    ]
    payoffs = list(loop.get("payoffs") or []) + _synthetic_score_payoffs(loop)
    payoff_scores = loop.get("payoff_score_by_scene") or {}

    assessments: list[dict[str, Any]] = []
    if not payoffs:
        assessments.append(
            assess_hook_payoff_relation(
                loop_id=str(loop.get("loop_id")),
                question=str(loop.get("question") or ""),
                information_gap=str(loop.get("information_gap") or ""),
                hook=hook,
                payoff=None,
                developments=developments,
                payoff_score=None,
                soft_conflicts=soft,
                hard_conflicts=hard,
            )
        )
    else:
        for payoff in payoffs:
            scene = payoff.get("scene_ordinal")
            score_val = None
            if scene is not None and str(scene) in payoff_scores:
                score_val = int(payoff_scores[str(scene)])
            elif scene is not None and scene in payoff_scores:
                score_val = int(payoff_scores[scene])
            assessments.append(
                assess_hook_payoff_relation(
                    loop_id=str(loop.get("loop_id")),
                    question=str(loop.get("question") or ""),
                    information_gap=str(loop.get("information_gap") or ""),
                    hook=hook,
                    payoff=payoff,
                    developments=developments,
                    payoff_score=score_val,
                    soft_conflicts=soft,
                    hard_conflicts=hard,
                )
            )

    assessments.sort(key=lambda item: (-float(item.get("total_score") or 0), item.get("grade") or ""))
    if assessments:
        assessments[0]["is_primary"] = True

    primary = assessments[0] if assessments else None
    artifact_status = str(loop.get("status") or "open")
    display_status = artifact_status
    has_entity_payoffs = any(
        p.get("source_type") != "score_inferred" and (p.get("summary") or p.get("type"))
        for p in (loop.get("payoffs") or [])
    )
    if hard:
        display_status = "inconsistent"
    elif artifact_status in {"resolved", "transformed", "abandoned"} and has_entity_payoffs:
        # Soft evidence divergence must not reopen an already entity-backed resolution.
        display_status = artifact_status
    elif primary and primary.get("grade") == GRADE_CONFIRMED:
        ptype = str((primary.get("payoff_ref") or {}).get("type") or "")
        if ptype == "transformed_question":
            display_status = "transformed"
        elif ptype == "partial":
            display_status = "partially_resolved"
        else:
            display_status = "resolved"
    elif primary and primary.get("grade") == GRADE_PROBABLE:
        ptype = str((primary.get("payoff_ref") or {}).get("type") or "")
        display_status = "partially_resolved" if ptype == "partial" else "resolved"
    elif primary and primary.get("grade") == GRADE_CANDIDATE:
        display_status = "partially_resolved"
    elif primary and primary.get("grade") == GRADE_UNSUPPORTED:
        if display_status not in {"abandoned", "transformed"}:
            display_status = "open"

    warning = None
    if hard:
        warning = HARD_BLOCK_USER_MESSAGE
    elif soft and primary and primary.get("grade") in {GRADE_PROBABLE, GRADE_CANDIDATE, GRADE_CONFIRMED}:
        warning = SOFT_CONFLICT_USER_MESSAGE

    return {
        **loop,
        # Keep original status for artifact fidelity; add display overlay.
        "display_status": display_status,
        "primary_relation": primary,
        "candidate_relations": assessments[1:],
        "relation_assessments": assessments,
        "hard_blocked": bool(hard),
        "soft_conflict": bool(soft) and not hard,
        "relation_warning": warning,
        "consistency_status": "inconsistent" if hard else ("soft_conflict" if soft else "consistent"),
    }


def reconcile_narrative_loops(loops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [reconcile_loop_relations(loop) for loop in loops]


# --- Reading resistance (阅读阻力) -------------------------------------------

READING_RESISTANCE_REASONS_ZH = {
    "weak_progress": "推进较弱",
    "insufficient_response": "回应不足",
    "long_transition": "过渡偏长",
    "information_repeat": "信息重复",
    "emotion_break": "情绪中断",
    "unclear_goal": "目标不清",
    "over_explanation": "说明过多",
    "stalled_suspense": "悬念停滞",
    "over_fragmented": "场景可能切得过细",
}


def derive_reading_resistance(
    loops: list[dict[str, Any]],
    *,
    scene_nodes: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Derive reading-resistance intervals for UI (not attrition-only empty-payoff)."""
    nodes = sorted(scene_nodes or [], key=lambda item: int(item.get("scene_ordinal") or 0))
    by_ord = {int(n.get("scene_ordinal") or 0): n for n in nodes}
    items: list[dict[str, Any]] = []

    for loop in loops:
        if loop.get("hard_blocked"):
            continue
        display = str(loop.get("display_status") or loop.get("status") or "")
        if display in {"resolved", "transformed", "abandoned"}:
            continue
        primary = loop.get("primary_relation") or {}
        grade = primary.get("grade")
        span = int(loop.get("nodes_spanned") or 1)
        start = int(loop.get("open_from_scene") or 0) or None
        has_dev = bool(loop.get("developments"))
        has_partial = bool(loop.get("has_partial_response")) or grade == GRADE_CANDIDATE

        # Open but actively developing — not automatic resistance.
        if display in {"open", "partially_resolved"} and has_dev and span < 3 and has_partial:
            continue
        if display == "open" and has_dev and span <= 2:
            continue

        reasons: list[str] = []
        if display in {"open", "partially_resolved"} and span >= 3 and not has_partial:
            reasons.append("insufficient_response")
            reasons.append("stalled_suspense")
        if display == "open" and span >= 4 and not has_dev:
            reasons.append("weak_progress")
            reasons.append("unclear_goal")

        # Scene-local signals near the open span.
        if start and nodes:
            end = start + max(0, span - 1)
            momenta: list[float] = []
            plots: list[float] = []
            for ord_ in range(start, end + 1):
                node = by_ord.get(ord_)
                if not node:
                    continue
                scores = node.get("scores") or {}
                mom = scores.get("reading_momentum")
                if mom is None and isinstance(node.get("engagement"), dict):
                    mom = node["engagement"].get("engagement_score")
                if isinstance(mom, (int, float)):
                    momenta.append(float(mom))
                plot = scores.get("plot_progress")
                if isinstance(plot, (int, float)):
                    plots.append(float(plot))
                role = str(node.get("role") or "")
                if role == "beat" and span >= 3:
                    reasons.append("over_fragmented")
                para_count = int(node.get("paragraph_count") or 0)
                # Necessary short transition: low momentum alone is not enough.
                if para_count > 0 and para_count <= 2 and span <= 2:
                    continue
                if para_count >= 8 and (mom is not None and float(mom) < 40):
                    reasons.append("long_transition")
                pacing_fit = scores.get("pacing_fit")
                if isinstance(pacing_fit, (int, float)) and float(pacing_fit) < 35:
                    reasons.append("over_explanation")

            if len(momenta) >= 2 and momenta[-1] + 8 < momenta[0] and not has_partial and span >= 3:
                reasons.append("weak_progress")
            if len(plots) >= 2 and plots[-1] <= plots[0] and span >= 3:
                reasons.append("weak_progress")

        # Deduplicate reasons preserving order.
        uniq: list[str] = []
        for code in reasons:
            if code not in uniq:
                uniq.append(code)
        if not uniq:
            continue

        items.append(
            {
                "resistance_type": "reading_resistance",
                "loop_id": loop.get("loop_id"),
                "question": loop.get("question"),
                "start_scene_ordinal": start,
                "end_scene_ordinal": (start + max(0, span - 1)) if start else None,
                "span": span,
                "reason_codes": uniq,
                "reasons_zh": [READING_RESISTANCE_REASONS_ZH.get(c, c) for c in uniq],
                "summary": _reading_resistance_summary(loop, uniq),
                "has_partial_response": has_partial,
                "severity": False,
            }
        )
    return items


def _reading_resistance_summary(loop: dict[str, Any], reason_codes: list[str]) -> str:
    question = _clip(str(loop.get("question") or "未命名问题"), 40)
    labels = [READING_RESISTANCE_REASONS_ZH.get(c, c) for c in reason_codes[:3]]
    joined = "、".join(labels) if labels else "阅读体验可能受阻"
    start = loop.get("open_from_scene")
    span = int(loop.get("nodes_spanned") or 1)
    where = f"从场景 {start} 起跨越 {span} 个节点，" if start else ""
    return f"开放问题「{question}」{where}出现{joined}。"
