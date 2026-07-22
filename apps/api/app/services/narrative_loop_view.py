"""Unified NarrativeLoopView adapter over existing Reader Journey artifacts.

Presentation / consistency layer only — does not change model prompts, weights,
thresholds, or persisted profile payloads.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.schemas.reader_journey import SceneReaderJourneyProfileItem
from app.services.narrative_relation_assessment import (
    HARD_BLOCK_USER_MESSAGE,
    SOFT_CONFLICT_USER_MESSAGE,
    classify_conflicts,
    derive_reading_resistance,
    is_hard_block,
    reconcile_narrative_loops,
)

NARRATIVE_LOOP_VIEW_VERSION = "1.0.0"

# Presentation gates (not score formulas). Align with existing UI copy thresholds.
HIGH_PAYOFF_SCORE = 70
MID_PAYOFF_SCORE = 40
OPEN_RISK_MIN_SPAN = 2

LOOP_STATUS_OPEN = "open"
LOOP_STATUS_PARTIAL = "partially_resolved"
LOOP_STATUS_RESOLVED = "resolved"
LOOP_STATUS_TRANSFORMED = "transformed"
LOOP_STATUS_ABANDONED = "abandoned"
LOOP_STATUS_INCONSISTENT = "inconsistent"

PAYOFF_PARTIAL = "partial"
PAYOFF_FULL = "full"
PAYOFF_REVERSAL = "reversal"
PAYOFF_TRANSFORMED = "transformed_question"

INCONSISTENT_USER_MESSAGE = "当前关系识别结果不一致，暂不作为确定结论"


def _clip(text: str, max_chars: int = 160) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1] + "…"


def _loop_id(*parts: Any) -> str:
    raw = "|".join(str(part) for part in parts if part is not None)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"nl-{digest}"


def _norm_question(text: str | None) -> str:
    return " ".join((text or "").strip().lower().split())


def _map_chain_status(status: str | None) -> str:
    key = (status or "").strip().lower()
    if key in {"answered", "paid_off", "resolved"}:
        return LOOP_STATUS_RESOLVED
    if key in {"partially_answered", "partial", "progressing"}:
        return LOOP_STATUS_PARTIAL
    if key in {"transformed"}:
        return LOOP_STATUS_TRANSFORMED
    if key in {"dropped", "abandoned", "overdue"}:
        return LOOP_STATUS_ABANDONED
    if key in {"created", "carried", "open"}:
        return LOOP_STATUS_OPEN
    return LOOP_STATUS_OPEN


def _map_lifecycle_status(status: str | None) -> str:
    key = (status or "").strip().lower()
    if key in {"paid_off", "resolved"}:
        return LOOP_STATUS_RESOLVED
    if key in {"partial", "progressing"}:
        return LOOP_STATUS_PARTIAL
    if key in {"abandoned", "overdue"}:
        return LOOP_STATUS_ABANDONED
    if key in {"transformed"}:
        return LOOP_STATUS_TRANSFORMED
    return LOOP_STATUS_OPEN


def _payoff_kind_from_answer_degree(degree: str | None) -> str:
    key = (degree or "").strip().lower()
    if key in {"full", "complete", "answered"}:
        return PAYOFF_FULL
    if key in {"misleading", "reversal"}:
        return PAYOFF_REVERSAL
    if key in {"transformed", "transform"}:
        return PAYOFF_TRANSFORMED
    return PAYOFF_PARTIAL


def _evidence_refs(ids: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in ids or []:
        text = str(item).strip()
        if text and text not in out:
            out.append(text)
    return out


def _profile_by_ordinal(
    profiles: list[SceneReaderJourneyProfileItem],
) -> dict[int, SceneReaderJourneyProfileItem]:
    return {profile.scene_ordinal: profile for profile in profiles}


def _attach_scene_entities(
    loop: dict[str, Any],
    profile: SceneReaderJourneyProfileItem | None,
    *,
    as_payoff_scene: bool = False,
) -> None:
    if profile is None:
        return
    for hook in profile.hooks:
        entry = {
            "scene_ordinal": profile.scene_ordinal,
            "type": hook.type,
            "summary": hook.summary,
            "strength": hook.strength,
            "known": hook.known,
            "gap": hook.gap,
            "continue_drive": hook.continue_drive,
            "next_handoff": hook.next_handoff,
            "evidence_paragraph_ids": _evidence_refs(hook.evidence_paragraph_ids),
        }
        if entry not in loop["hook"]:
            loop["hook"].append(entry)
        if hook.gap and not loop["information_gap"]:
            loop["information_gap"] = _clip(hook.gap)
        loop["evidence"].extend(entry["evidence_paragraph_ids"])

    if as_payoff_scene or profile.payoffs or profile.reader_question_answered:
        answered_kinds = {
            _norm_question(item.question): _payoff_kind_from_answer_degree(item.answer_degree)
            for item in profile.reader_question_answered
        }
        for payoff in profile.payoffs:
            matched_kind = answered_kinds.get(_norm_question(loop.get("question")))
            if matched_kind is None and len(answered_kinds) == 1:
                matched_kind = next(iter(answered_kinds.values()))
            # Lifecycle/paid_off scenes: treat linked semantic payoffs as full when no degree.
            if matched_kind is None and as_payoff_scene and loop.get("status") == LOOP_STATUS_RESOLVED:
                matched_kind = PAYOFF_FULL
            entry = {
                "scene_ordinal": profile.scene_ordinal,
                "type": matched_kind
                or (
                    PAYOFF_FULL
                    if payoff.type in {"stage_completion", "identity"}
                    else PAYOFF_PARTIAL
                ),
                "source_type": payoff.type,
                "summary": payoff.summary,
                "strength": payoff.strength,
                "evidence_paragraph_ids": _evidence_refs(payoff.evidence_paragraph_ids),
            }
            loop["payoffs"].append(entry)
            loop["evidence"].extend(entry["evidence_paragraph_ids"])
        if not profile.payoffs:
            for answered in profile.reader_question_answered:
                if _norm_question(answered.question) != _norm_question(loop.get("question")):
                    continue
                loop["payoffs"].append(
                    {
                        "scene_ordinal": profile.scene_ordinal,
                        "type": _payoff_kind_from_answer_degree(answered.answer_degree),
                        "source_type": "reader_question_answered",
                        "summary": answered.answer_summary or answered.question,
                        "strength": None,
                        "evidence_paragraph_ids": _evidence_refs(answered.evidence_paragraph_ids),
                    }
                )


def _dedupe_evidence(loop: dict[str, Any]) -> None:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in loop.get("evidence") or []:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    loop["evidence"] = ordered


def _empty_loop(
    *,
    loop_id: str,
    question: str,
    scope: dict[str, Any],
    status: str,
    confidence: float = 0.5,
) -> dict[str, Any]:
    return {
        "loop_id": loop_id,
        "scope": scope,
        "question": _clip(question),
        "information_gap": "",
        "hook": [],
        "developments": [],
        "payoffs": [],
        "residual_question": "",
        "status": status,
        "evidence": [],
        "confidence": confidence,
        "consistency_status": "consistent",
        "conflicts": [],
        "payoff_score_by_scene": {},
        "open_from_scene": None,
        "nodes_spanned": 0,
        "has_partial_response": False,
    }


def _loops_from_lifecycle(
    lifecycle: list[dict[str, Any]],
    profiles_by_ord: dict[int, SceneReaderJourneyProfileItem],
    scope: dict[str, Any],
) -> list[dict[str, Any]]:
    loops: list[dict[str, Any]] = []
    for item in lifecycle:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question_text") or item.get("question") or "").strip()
        if not question:
            continue
        qid = str(item.get("question_id") or _loop_id("life", question, item.get("setup_scene")))
        setup = int(item.get("setup_scene") or 0)
        developments = [int(v) for v in (item.get("development_scenes") or []) if v is not None]
        payoff_scene = item.get("payoff_scene")
        payoff_ord = int(payoff_scene) if payoff_scene is not None else None
        status = _map_lifecycle_status(str(item.get("status") or ""))
        loop = _empty_loop(
            loop_id=qid if qid.startswith("nl-") or qid.startswith("q") else _loop_id("life", qid),
            question=question,
            scope=dict(scope),
            status=status,
            confidence=float(item.get("strength") or 50) / 100.0,
        )
        loop["open_from_scene"] = setup or None
        involved = sorted({setup, *developments, *( [payoff_ord] if payoff_ord else [])} - {0, None})
        loop["developments"] = [
            {"scene_ordinal": ord_, "kind": "development"} for ord_ in developments
        ]
        if setup:
            _attach_scene_entities(loop, profiles_by_ord.get(setup))
        for ord_ in developments:
            _attach_scene_entities(loop, profiles_by_ord.get(ord_))
        if payoff_ord:
            _attach_scene_entities(loop, profiles_by_ord.get(payoff_ord), as_payoff_scene=True)
        if status in {LOOP_STATUS_OPEN, LOOP_STATUS_PARTIAL, LOOP_STATUS_TRANSFORMED}:
            outs = profiles_by_ord.get(max(involved) if involved else setup)
            if outs:
                for out_item in outs.reader_question_out:
                    if _norm_question(out_item.question) == _norm_question(question):
                        loop["residual_question"] = _clip(out_item.question)
        loop["nodes_spanned"] = max(1, len(involved))
        loop["has_partial_response"] = any(
            p.get("type") == PAYOFF_PARTIAL for p in loop["payoffs"]
        ) or status == LOOP_STATUS_PARTIAL
        for ord_ in involved:
            profile = profiles_by_ord.get(ord_)
            if profile is not None:
                loop["payoff_score_by_scene"][str(ord_)] = int(profile.payoff_score)
        _dedupe_evidence(loop)
        loops.append(loop)
    return loops


def _loops_from_chains(
    chains: list[dict[str, Any]],
    profiles_by_ord: dict[int, SceneReaderJourneyProfileItem],
    scope: dict[str, Any],
) -> list[dict[str, Any]]:
    loops: list[dict[str, Any]] = []
    for chain in chains:
        if not isinstance(chain, dict):
            continue
        question = str(
            chain.get("canonical_question")
            or chain.get("question_summary")
            or chain.get("question")
            or ""
        ).strip()
        if not question:
            continue
        created = int(
            chain.get("created_scene")
            or chain.get("created_scene_ordinal")
            or 0
        )
        carried = [
            int(v)
            for v in (
                chain.get("carried_scene_ordinals")
                or chain.get("development_scenes")
                or []
            )
            if v is not None
        ]
        answered = chain.get("answered_scene") or chain.get("answered_scene_ordinal")
        answered_ord = int(answered) if answered is not None else None
        status = _map_chain_status(str(chain.get("status") or ""))
        cid = str(
            chain.get("canonical_id")
            or chain.get("question_chain_id")
            or _loop_id("chain", question, created)
        )
        raw_conf = chain.get("confidence")
        if raw_conf is None:
            raw_conf = chain.get("strength") or 50
        conf = float(raw_conf)
        if conf > 1:
            conf = conf / 100.0
        loop = _empty_loop(
            loop_id=cid if cid.startswith(("nl-", "qc-", "cc-")) else _loop_id("chain", cid),
            question=question,
            scope=dict(scope),
            status=status,
            confidence=max(0.0, min(1.0, conf)),
        )
        loop["open_from_scene"] = created or None
        loop["developments"] = [{"scene_ordinal": ord_, "kind": "carried"} for ord_ in carried]
        involved = sorted({created, *carried, *([answered_ord] if answered_ord else [])} - {0})
        for ord_ in involved:
            _attach_scene_entities(
                loop,
                profiles_by_ord.get(ord_),
                as_payoff_scene=(answered_ord is not None and ord_ == answered_ord),
            )
            profile = profiles_by_ord.get(ord_)
            if profile is not None:
                loop["payoff_score_by_scene"][str(ord_)] = int(profile.payoff_score)
        if status in {LOOP_STATUS_OPEN, LOOP_STATUS_PARTIAL, LOOP_STATUS_TRANSFORMED}:
            loop["residual_question"] = question
        loop["nodes_spanned"] = max(1, len(involved))
        loop["has_partial_response"] = status == LOOP_STATUS_PARTIAL or any(
            p.get("type") == PAYOFF_PARTIAL for p in loop["payoffs"]
        )
        _dedupe_evidence(loop)
        loops.append(loop)
    return loops


def _orphan_hook_loops(
    profiles: list[SceneReaderJourneyProfileItem],
    existing: list[dict[str, Any]],
    scope: dict[str, Any],
) -> list[dict[str, Any]]:
    known_questions = {_norm_question(loop.get("question")) for loop in existing}
    known_hook_summaries = {
        _norm_question(hook.get("summary"))
        for loop in existing
        for hook in loop.get("hook") or []
    }
    orphans: list[dict[str, Any]] = []
    for profile in sorted(profiles, key=lambda item: item.scene_ordinal):
        for hook in profile.hooks:
            summary = (hook.summary or "").strip()
            if not summary:
                continue
            norm = _norm_question(summary)
            gap_norm = _norm_question(hook.gap)
            if norm in known_questions or gap_norm in known_questions:
                continue
            if norm in known_hook_summaries:
                continue
            question = hook.gap or summary
            loop = _empty_loop(
                loop_id=_loop_id("hook", profile.scene_ordinal, summary),
                question=question,
                scope=dict(scope),
                status=LOOP_STATUS_OPEN,
                confidence=max(0.2, min(1.0, hook.strength / 100.0)),
            )
            loop["information_gap"] = _clip(hook.gap or "")
            loop["open_from_scene"] = profile.scene_ordinal
            loop["nodes_spanned"] = 1
            _attach_scene_entities(loop, profile)
            loop["payoff_score_by_scene"][str(profile.scene_ordinal)] = int(profile.payoff_score)
            _dedupe_evidence(loop)
            orphans.append(loop)
            known_hook_summaries.add(norm)
            known_questions.add(_norm_question(question))
    return orphans


def _detect_conflicts(
    loops: list[dict[str, Any]],
    profiles: list[SceneReaderJourneyProfileItem],
    *,
    legacy_risk_intervals: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for profile in profiles:
        has_entities = bool(profile.payoffs)
        if int(profile.payoff_score) >= HIGH_PAYOFF_SCORE and not has_entities:
            conflicts.append(
                {
                    "code": "payoff_score_without_entity",
                    "scene_ordinal": profile.scene_ordinal,
                    "message": (
                        f"Scene {profile.scene_ordinal}: payoff_score="
                        f"{profile.payoff_score} but payoffs[] is empty"
                    ),
                }
            )
        for payoff in profile.payoffs:
            if not payoff.evidence_paragraph_ids:
                conflicts.append(
                    {
                        "code": "payoff_entity_without_evidence",
                        "scene_ordinal": profile.scene_ordinal,
                        "message": (
                            f"Scene {profile.scene_ordinal}: payoff entity "
                            f"has no evidence_paragraph_ids"
                        ),
                    }
                )
        if profile.hooks and not (
            profile.reader_question_created
            or profile.reader_question_out
            or profile.reader_question_in
        ):
            # Hook present but no question fields on same scene — may still link via chain.
            matched = False
            for loop in loops:
                if any(h.get("scene_ordinal") == profile.scene_ordinal for h in loop.get("hook") or []):
                    if loop.get("question"):
                        matched = True
                        break
            if not matched:
                conflicts.append(
                    {
                        "code": "hook_without_question",
                        "scene_ordinal": profile.scene_ordinal,
                        "message": (
                            f"Scene {profile.scene_ordinal}: hook present but no "
                            "linked reader question"
                        ),
                    }
                )

    for loop in loops:
        for payoff in loop.get("payoffs") or []:
            # Payoff pointing at missing hook identity is soft when hook list empty
            # but loop has question — only flag when explicit hook_id present.
            if payoff.get("hook_ref") and not any(
                h.get("summary") == payoff.get("hook_ref") for h in loop.get("hook") or []
            ):
                conflicts.append(
                    {
                        "code": "payoff_points_to_missing_hook",
                        "loop_id": loop.get("loop_id"),
                        "message": "Payoff references a hook that is not on this loop",
                    }
                )

    for interval in legacy_risk_intervals or []:
        if interval.get("risk_type") != "consecutive_no_payoff":
            continue
        start = int(interval.get("start_scene_ordinal") or 0)
        end = int(interval.get("end_scene_ordinal") or start)
        for loop in loops:
            if loop.get("status") not in {LOOP_STATUS_RESOLVED}:
                continue
            payoff_scenes = {
                int(p.get("scene_ordinal") or 0) for p in loop.get("payoffs") or []
            }
            if any(start <= ord_ <= end for ord_ in payoff_scenes):
                conflicts.append(
                    {
                        "code": "risk_no_payoff_but_loop_resolved",
                        "loop_id": loop.get("loop_id"),
                        "start_scene_ordinal": start,
                        "end_scene_ordinal": end,
                        "message": (
                            f"Risk interval {start}—{end} claims no payoff while "
                            f"loop {loop.get('loop_id')} is resolved"
                        ),
                    }
                )

    return conflicts


def _apply_conflicts_to_loops(
    loops: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> None:
    by_scene: dict[int, list[dict[str, Any]]] = {}
    by_loop: dict[str, list[dict[str, Any]]] = {}
    for conflict in conflicts:
        ord_ = conflict.get("scene_ordinal")
        if ord_ is not None:
            by_scene.setdefault(int(ord_), []).append(conflict)
        lid = conflict.get("loop_id")
        if lid:
            by_loop.setdefault(str(lid), []).append(conflict)

    for loop in loops:
        related: list[dict[str, Any]] = list(by_loop.get(str(loop.get("loop_id")), []))
        for hook in loop.get("hook") or []:
            related.extend(by_scene.get(int(hook.get("scene_ordinal") or 0), []))
        for payoff in loop.get("payoffs") or []:
            related.extend(by_scene.get(int(payoff.get("scene_ordinal") or 0), []))
        for key, score in (loop.get("payoff_score_by_scene") or {}).items():
            if int(score) >= HIGH_PAYOFF_SCORE and not loop.get("payoffs"):
                related.append(
                    {
                        "code": "payoff_score_without_entity",
                        "scene_ordinal": int(key),
                        "message": (
                            f"Scene {key}: high payoff_score without linked payoff entity"
                        ),
                    }
                )
        # Dedupe by code+scene
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for item in related:
            token = f"{item.get('code')}:{item.get('scene_ordinal')}:{item.get('message')}"
            if token in seen:
                continue
            seen.add(token)
            unique.append(item)
        if not unique:
            continue
        loop["conflicts"] = unique
        hard, soft = classify_conflicts(unique)
        if hard:
            loop["consistency_status"] = "inconsistent"
            loop["status"] = LOOP_STATUS_INCONSISTENT
            loop["hard_blocked"] = True
        elif soft:
            # Soft divergence keeps original loop status for ranking; UI uses soft banner.
            loop["consistency_status"] = "soft_conflict"
            loop["soft_conflict"] = True
            loop["hard_blocked"] = False


def derive_loop_risks(loops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Legacy open-loop risks — prefer reading_resistance for new UI."""
    risks: list[dict[str, Any]] = []
    for loop in loops:
        if loop.get("hard_blocked") or (
            loop.get("consistency_status") == "inconsistent" and is_hard_block(loop.get("conflicts"))
        ):
            risks.append(
                {
                    "risk_type": "narrative_loop_inconsistent",
                    "loop_id": loop.get("loop_id"),
                    "question": loop.get("question"),
                    "start_scene_ordinal": loop.get("open_from_scene"),
                    "end_scene_ordinal": loop.get("open_from_scene"),
                    "span": loop.get("nodes_spanned") or 1,
                    "has_partial_response": bool(loop.get("has_partial_response")),
                    "summary": HARD_BLOCK_USER_MESSAGE,
                    "deterministic": False,
                    "conflicts": loop.get("conflicts") or [],
                }
            )
            continue
        display = str(loop.get("display_status") or loop.get("status") or "")
        if display not in {LOOP_STATUS_OPEN, LOOP_STATUS_PARTIAL}:
            continue
        span = int(loop.get("nodes_spanned") or 1)
        if span < OPEN_RISK_MIN_SPAN and display == LOOP_STATUS_PARTIAL:
            continue
        if span < OPEN_RISK_MIN_SPAN and not loop.get("hook"):
            continue
        start = int(loop.get("open_from_scene") or 0)
        end = start + max(0, span - 1)
        risks.append(
            {
                "risk_type": "open_narrative_loop",
                "loop_id": loop.get("loop_id"),
                "question": loop.get("question"),
                "start_scene_ordinal": start or None,
                "end_scene_ordinal": end or None,
                "span": span,
                "has_partial_response": bool(loop.get("has_partial_response")),
                "summary": _open_loop_risk_summary(loop),
                "deterministic": True,
            }
        )
    return risks


def _open_loop_risk_summary(loop: dict[str, Any]) -> str:
    question = _clip(str(loop.get("question") or "未命名问题"), 80)
    start = loop.get("open_from_scene")
    span = int(loop.get("nodes_spanned") or 1)
    partial = "存在部分回应，" if loop.get("has_partial_response") else "尚无有效回应，"
    start_text = f"从场景 {start} 起" if start else "从当前节点起"
    return f"开放问题「{question}」{start_text}已跨越 {span} 个节点，{partial}可能降低阅读动力。"


def scene_payoff_claim(
    loops: list[dict[str, Any]],
    scene_ordinal: int,
    *,
    payoff_score: int | None = None,
) -> dict[str, Any]:
    """Unified claim for chart/inspector — never assert 有效兑现 from score alone."""
    related = [
        loop
        for loop in loops
        if any(int(p.get("scene_ordinal") or 0) == scene_ordinal for p in loop.get("payoffs") or [])
        or str(scene_ordinal) in (loop.get("payoff_score_by_scene") or {})
        or (
            (loop.get("primary_relation") or {}).get("payoff_ref") or {}
        ).get("scene_ordinal")
        == scene_ordinal
    ]
    hard_blocked = [
        loop
        for loop in related
        if loop.get("hard_blocked") or loop.get("consistency_status") == "inconsistent"
    ]
    if hard_blocked:
        return {
            "claim": "inconsistent",
            "label": HARD_BLOCK_USER_MESSAGE,
            "deterministic": False,
            "loops": [loop.get("loop_id") for loop in related],
            "payoff_types": [],
            "evidence_paragraph_ids": [],
        }

    payoffs = [
        payoff
        for loop in related
        for payoff in (loop.get("payoffs") or [])
        if int(payoff.get("scene_ordinal") or 0) == scene_ordinal
    ]
    if payoffs:
        kinds = [str(p.get("type") or PAYOFF_PARTIAL) for p in payoffs]
        evidence: list[str] = []
        for payoff in payoffs:
            evidence.extend(payoff.get("evidence_paragraph_ids") or [])
        if PAYOFF_FULL in kinds:
            label = "有效兑现"
            claim = "full"
        elif PAYOFF_TRANSFORMED in kinds:
            label = "转化为新问题"
            claim = "transformed"
        elif PAYOFF_REVERSAL in kinds:
            label = "反转兑现"
            claim = "reversal"
        else:
            label = "部分兑现"
            claim = "partial"
        return {
            "claim": claim,
            "label": label,
            "deterministic": True,
            "loops": [loop.get("loop_id") for loop in related],
            "payoff_types": kinds,
            "evidence_paragraph_ids": list(dict.fromkeys(evidence)),
        }

    # No entity payoffs: use ranked primary relation (incl. score-inferred).
    for loop in related:
        primary = loop.get("primary_relation") or {}
        pref = primary.get("payoff_ref") or {}
        if pref.get("scene_ordinal") != scene_ordinal:
            continue
        grade = primary.get("grade")
        if grade and grade != "unsupported":
            soft = bool(loop.get("soft_conflict"))
            return {
                "claim": f"relation_{grade}",
                "label": primary.get("grade_label_zh")
                or primary.get("label_zh")
                or (SOFT_CONFLICT_USER_MESSAGE if soft else INCONSISTENT_USER_MESSAGE),
                "deterministic": grade == "confirmed" and not soft,
                "grade": grade,
                "loops": [loop.get("loop_id") for loop in related],
                "payoff_types": [str(pref.get("type") or "")] if pref.get("type") else [],
                "evidence_paragraph_ids": list(pref.get("evidence_paragraph_ids") or []),
                "soft_conflict": soft,
            }

    if payoff_score is not None and payoff_score >= MID_PAYOFF_SCORE:
        return {
            "claim": "score_only",
            "label": SOFT_CONFLICT_USER_MESSAGE,
            "deterministic": False,
            "grade": "candidate",
            "loops": [loop.get("loop_id") for loop in related],
            "payoff_types": [],
            "evidence_paragraph_ids": [],
            "soft_conflict": True,
        }

    return {
        "claim": "none",
        "label": "未兑现",
        "deterministic": True,
        "loops": [loop.get("loop_id") for loop in related],
        "payoff_types": [],
        "evidence_paragraph_ids": [],
    }


def build_narrative_loop_bundle(
    profiles: list[SceneReaderJourneyProfileItem],
    *,
    question_chains: list[dict[str, Any]] | None = None,
    question_lifecycle: list[dict[str, Any]] | None = None,
    legacy_risk_intervals: list[dict[str, Any]] | None = None,
    book_id: int | None = None,
    chapter_id: int | None = None,
    analysis_run_id: int | None = None,
    journey_run_id: int | None = None,
    scene_contract_version: str | None = None,
    artifact_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Build NarrativeLoopView list + derived risks + consistency report."""
    scope = {
        "book_id": book_id,
        "chapter_id": chapter_id,
        "analysis_run_id": analysis_run_id,
        "journey_run_id": journey_run_id,
        "scene_contract_version": scene_contract_version,
        "artifact_fingerprint": artifact_fingerprint,
        "level": "chapter",
    }
    profiles_by_ord = _profile_by_ordinal(profiles)
    loops: list[dict[str, Any]] = []
    if question_lifecycle:
        loops.extend(_loops_from_lifecycle(question_lifecycle, profiles_by_ord, scope))
    if not loops and question_chains:
        loops.extend(_loops_from_chains(question_chains, profiles_by_ord, scope))
    elif question_chains and not question_lifecycle:
        loops.extend(_loops_from_chains(question_chains, profiles_by_ord, scope))

    # Prefer lifecycle; still merge chains that introduce new questions.
    if question_lifecycle and question_chains:
        existing = {_norm_question(loop.get("question")) for loop in loops}
        extras = [
            chain
            for chain in question_chains
            if _norm_question(
                str(
                    chain.get("canonical_question")
                    or chain.get("question_summary")
                    or chain.get("question")
                    or ""
                )
            )
            not in existing
        ]
        loops.extend(_loops_from_chains(extras, profiles_by_ord, scope))

    loops.extend(_orphan_hook_loops(profiles, loops, scope))

    conflicts = _detect_conflicts(
        loops, profiles, legacy_risk_intervals=legacy_risk_intervals
    )
    _apply_conflicts_to_loops(loops, conflicts)
    loops = reconcile_narrative_loops(loops)
    loop_risks = derive_loop_risks(loops)
    reading_resistance = derive_reading_resistance(loops)

    hard_conflicts = [c for c in conflicts if is_hard_block([c])]
    soft_conflicts = [c for c in conflicts if not is_hard_block([c])]
    if hard_conflicts:
        consistency_status = "inconsistent"
        user_message = HARD_BLOCK_USER_MESSAGE
    elif soft_conflicts:
        consistency_status = "soft_conflict"
        user_message = SOFT_CONFLICT_USER_MESSAGE
    else:
        consistency_status = "consistent"
        user_message = None

    scene_claims = {
        str(profile.scene_ordinal): scene_payoff_claim(
            loops,
            profile.scene_ordinal,
            payoff_score=int(profile.payoff_score),
        )
        for profile in profiles
    }

    return {
        "narrative_loop_view_version": NARRATIVE_LOOP_VIEW_VERSION,
        "narrative_loops": loops,
        "narrative_loop_risks": loop_risks,
        "reading_resistance": reading_resistance,
        "scene_payoff_claims": scene_claims,
        "consistency_report": {
            "status": consistency_status,
            "conflict_count": len(conflicts),
            "hard_conflict_count": len(hard_conflicts),
            "soft_conflict_count": len(soft_conflicts),
            "conflicts": conflicts,
            "user_message": user_message,
            "scope": scope,
        },
    }
