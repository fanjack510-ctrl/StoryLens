"""Reader Journey quality gates."""

from __future__ import annotations

import re
from collections import Counter

from app.schemas.reader_journey import (
    ChapterReaderJourneySynthesisResult,
    SceneReaderJourneyBatchResult,
    SceneReaderJourneyProfileItem,
)
from app.services.validation_errors import StructuralValidationError

GENERIC_SUMMARY_PATTERNS = (
    re.compile(r"^(推进情节|场景继续|故事发展|情节推进)"),
    re.compile(r"^(完成当前行动|状态发生变化)"),
)

OPENING_SUMMARY_PATTERNS = (
    re.compile(r".*(建立|开场|引入|情境|异常|人物出场).*"),
)

GENERIC_QUESTION_PATTERNS = (
    re.compile(r"^(接下来会发生什么|故事如何发展|情节如何推进|会发生什么)"),
    re.compile(r"^(读者想知道.*结果)$"),
)

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


def _raise(
    code: str,
    message: str,
    *,
    no_model_repair: bool = False,
    failed_field: str | None = None,
    repair_context: dict | None = None,
) -> None:
    raise StructuralValidationError(
        message,
        error_code=code,
        no_model_repair=no_model_repair,
        failed_field=failed_field,
        repair_context=repair_context,
    )


def _is_opening_summary(summary: str) -> bool:
    text = summary.strip()
    return any(pattern.match(text) for pattern in OPENING_SUMMARY_PATTERNS)


def _is_generic_question(text: str) -> bool:
    stripped = text.strip()
    return any(pattern.match(stripped) for pattern in GENERIC_QUESTION_PATTERNS)


def _paragraph_ordinal(paragraph_id: str) -> int:
    match = re.search(r"P(\d+)\s*$", paragraph_id.strip(), re.IGNORECASE)
    if match:
        return int(match.group(1))
    digits = re.search(r"(\d+)\s*$", paragraph_id.strip())
    return int(digits.group(1)) if digits else -1


def _earliest_paragraph_ordinal(paragraph_ids: list[str]) -> int | None:
    ordinals = [_paragraph_ordinal(pid) for pid in paragraph_ids if pid]
    ordinals = [value for value in ordinals if value >= 0]
    return min(ordinals) if ordinals else None


def validate_scene_profile_item(
    profile: SceneReaderJourneyProfileItem,
    *,
    allowed_paragraph_ids: set[str],
    prior_summaries: list[str] | None = None,
    is_chapter_opening: bool = False,
    prior_high_strength_outs: list[str] | None = None,
) -> None:
    if not profile.scene_value_summary.strip():
        _raise("JOURNEY_GENERIC_SUMMARY", "scene_value_summary 不能为空")
    summary = profile.scene_value_summary.strip()
    for pattern in GENERIC_SUMMARY_PATTERNS:
        if pattern.match(summary):
            _raise("JOURNEY_GENERIC_SUMMARY", "scene_value_summary 不得只是 goal/outcome 复述")

    opening = is_chapter_opening or profile.scene_ordinal == 1
    has_in = bool(profile.reader_question_in)
    has_created = bool(profile.reader_question_created)
    has_out = bool(profile.reader_question_out)

    for item in profile.reader_question_in:
        if getattr(item, "source", None) == "created_in_scene":
            _raise(
                "JOURNEY_CONTRACT_VALIDATION_CONFLICT",
                "created_in_scene 不得出现在 reader_question_in；请使用 reader_question_created",
                no_model_repair=True,
                failed_field="reader_question_in",
            )

    for item in profile.reader_question_created:
        if not item.trigger_summary.strip():
            _raise(
                "JOURNEY_QUESTION_CREATED_MISSING_TRIGGER",
                "reader_question_created 必须包含 trigger_summary",
                failed_field="reader_question_created",
            )
        if not item.evidence_paragraph_ids:
            _raise(
                "JOURNEY_QUESTION_CREATED_MISSING_TRIGGER",
                "reader_question_created 必须有 evidence_paragraph_ids",
                failed_field="reader_question_created",
            )

    for item in profile.reader_question_out:
        if not getattr(item, "origin", None):
            _raise(
                "JOURNEY_QUESTION_OUT_WITHOUT_ORIGIN",
                "reader_question_out 必须包含 origin",
                failed_field="reader_question_out",
            )

    for question in (
        [item.question for item in profile.reader_question_in]
        + [item.question for item in profile.reader_question_created]
        + [item.question for item in profile.reader_question_out]
    ):
        if _is_generic_question(question):
            _raise("JOURNEY_GENERIC_READER_QUESTION", f"读者问题过于泛化: {question[:40]}")

    prior_questions = set(prior_high_strength_outs or [])
    for item in profile.reader_question_in:
        prior_questions.add(item.question.strip())
    for item in profile.reader_question_created:
        prior_questions.add(item.question.strip())
    created_by_question = {
        item.question.strip(): item for item in profile.reader_question_created
    }
    for item in profile.reader_question_answered:
        answered = item.question.strip()
        if not answered:
            continue
        if answered not in prior_questions:
            _raise(
                "JOURNEY_ANSWER_WITHOUT_PRIOR_QUESTION",
                f"answered 问题无对应 prior: {answered[:40]}；"
                "不得反向编造问题；信息揭示应使用 payoffs/information_changes",
                failed_field="reader_question_answered",
            )
        created = created_by_question.get(answered)
        if created is None:
            # Cross-scene / carried-in answer: prior existence already proven above.
            continue
        if not item.evidence_paragraph_ids:
            _raise(
                "JOURNEY_QUESTION_EVIDENCE_INVALID",
                "同Scene answered 必须有 evidence_paragraph_ids",
                failed_field="reader_question_answered",
            )
        if not created.evidence_paragraph_ids:
            _raise(
                "JOURNEY_QUESTION_EVIDENCE_INVALID",
                "同Scene prior question 必须有 evidence_paragraph_ids",
                failed_field="reader_question_created",
            )
        created_ord = _earliest_paragraph_ordinal(created.evidence_paragraph_ids)
        answered_ord = _earliest_paragraph_ordinal(item.evidence_paragraph_ids)
        if created_ord is None or answered_ord is None:
            _raise(
                "JOURNEY_SAME_SCENE_ORDER_UNPROVEN",
                "同Scene 问答无法从 Evidence 段落序证明先后",
                failed_field="reader_question_answered",
            )
        if answered_ord < created_ord:
            _raise(
                "JOURNEY_ANSWER_BEFORE_QUESTION",
                "同Scene answered Evidence 早于 question Evidence",
                failed_field="reader_question_answered",
            )
        if answered_ord == created_ord:
            _raise(
                "JOURNEY_SAME_SCENE_ORDER_UNPROVEN",
                "同Scene 问答共享最早 Evidence 段落，顺序无法证明",
                failed_field="reader_question_answered",
            )

    if opening:
        if not has_in and not has_created and not has_out and not _is_opening_summary(summary):
            _raise(
                "JOURNEY_QUESTION_CHAIN_INVALID",
                "章节开场 Scene 需有 reader_question_created/out 或开场型 summary",
            )
    else:
        if not has_in and not has_created and not has_out:
            _raise(
                "JOURNEY_QUESTION_CHAIN_INVALID",
                "非开场 Scene 需有 carried/created/out 至少一类读者问题",
            )
        # Scene 2+ 空 q_in：模型阶段允许，程序在 persist 前确定性注入；章级禁止全部为空。

    if not has_out and not opening:
        _raise("JOURNEY_QUESTION_CHAIN_INVALID", "reader_question_out 不得全部为空")

    for item in profile.techniques:
        if not item.mechanism.strip() or not item.reader_effect.strip():
            _raise("JOURNEY_PROFILE_SCHEMA_INVALID", "technique 必须包含 mechanism 和 reader_effect")
        if not item.evidence_paragraph_ids:
            _raise("JOURNEY_EVIDENCE_OUT_OF_SCOPE", "technique 必须有 Evidence")
    for item in profile.payoffs:
        if len(item.summary.strip()) < 4:
            _raise("JOURNEY_GENERIC_SUMMARY", "payoff 必须具体")
    for item in profile.hooks:
        if len(item.summary.strip()) < 4:
            _raise("JOURNEY_GENERIC_SUMMARY", "hook 必须具体")
        structure_fields = (
            getattr(item, "known", "") or "",
            getattr(item, "gap", "") or "",
            getattr(item, "continue_drive", "") or "",
            getattr(item, "next_handoff", "") or "",
        )
        if any(structure_fields) and not all(field.strip() for field in structure_fields):
            _raise(
                "JOURNEY_HOOK_STRUCTURE_INCOMPLETE",
                "hook 需完整包含 已知—缺口—继续动力—下一场承接",
                failed_field="hooks",
            )
    for item in profile.information_changes:
        if item.certainty == "speculation" and "fact" in item.summary.lower():
            _raise("JOURNEY_PROFILE_SCHEMA_INVALID", "speculation 不得伪装成 fact")
    all_evidence = set(profile.evidence_paragraph_ids)
    oos_nodes: list[dict[str, object]] = []
    for field_name in (
        "reader_question_created",
        "reader_question_answered",
        "reader_question_out",
        "payoffs",
        "hooks",
        "techniques",
        "risk_points",
        "emotion_beats",
        "information_changes",
        "character_effects",
    ):
        for index, nested in enumerate(getattr(profile, field_name)):
            ids = list(getattr(nested, "evidence_paragraph_ids", None) or [])
            all_evidence.update(ids)
            bad = [item for item in ids if item and item not in allowed_paragraph_ids]
            if bad:
                oos_nodes.append(
                    {
                        "target_path": (
                            f"profiles[scene_id={profile.scene_id}]."
                            f"{field_name}[{index}].evidence_paragraph_ids"
                        ),
                        "field_name": field_name,
                        "index": index,
                        "invalid_evidence_ids": bad,
                        "original_invalid_node": nested.model_dump(mode="json"),
                    }
                )
    top_bad = [
        item
        for item in profile.evidence_paragraph_ids
        if item and item not in allowed_paragraph_ids
    ]
    if top_bad:
        oos_nodes.append(
            {
                "target_path": (
                    f"profiles[scene_id={profile.scene_id}].evidence_paragraph_ids"
                ),
                "field_name": "evidence_paragraph_ids",
                "index": None,
                "invalid_evidence_ids": top_bad,
                "original_invalid_node": {
                    "evidence_paragraph_ids": list(profile.evidence_paragraph_ids)
                },
            }
        )
    out_of_scope = [item for item in all_evidence if item and item not in allowed_paragraph_ids]
    if out_of_scope:
        _raise(
            "JOURNEY_EVIDENCE_OUT_OF_SCOPE",
            f"Evidence 段落不属于当前 Scene: {out_of_scope[:3]}",
            failed_field="evidence_paragraph_ids",
            repair_context={
                "error_code": "JOURNEY_EVIDENCE_OUT_OF_SCOPE",
                "target_scene_id": profile.scene_id,
                "invalid_evidence_ids": out_of_scope,
                "allowed_evidence_ids": sorted(allowed_paragraph_ids),
                "oos_nodes": oos_nodes,
            },
        )
    if prior_summaries and summary in prior_summaries[-3:]:
        _raise("JOURNEY_REPETITIVE_TECHNIQUE", "连续 Scene 不得复制相同模板文本")


def validate_scene_batch_result(
    result: SceneReaderJourneyBatchResult,
    *,
    expected_scene_ids: set[int],
    paragraph_ids_by_scene: dict[int, set[str]],
    prior_summaries: list[str] | None = None,
    prior_high_strength_outs: list[str] | None = None,
) -> None:
    if len(result.profiles) != len(expected_scene_ids):
        _raise("JOURNEY_PROFILE_SCHEMA_INVALID", "批次 Profile 数量与 Scene 不匹配")
    seen: set[int] = set()
    summaries = list(prior_summaries or [])
    prior_outs = list(prior_high_strength_outs or [])
    for profile in sorted(result.profiles, key=lambda item: item.scene_ordinal):
        if profile.scene_id in seen:
            _raise("JOURNEY_PROFILE_SCHEMA_INVALID", "每个 Scene 只能有一个 Profile")
        seen.add(profile.scene_id)
        if profile.scene_id not in expected_scene_ids:
            _raise("JOURNEY_PROFILE_SCHEMA_INVALID", f"非法 Scene ID: {profile.scene_id}")
        allowed = paragraph_ids_by_scene.get(profile.scene_id, set())
        validate_scene_profile_item(
            profile,
            allowed_paragraph_ids=allowed,
            prior_summaries=summaries,
            is_chapter_opening=profile.scene_ordinal == 1,
            prior_high_strength_outs=prior_outs,
        )
        summaries.append(profile.scene_value_summary.strip())
        prior_outs.extend(
            item.question
            for item in profile.reader_question_out
            if item.strength >= 50
        )


def _profile_has_evidenced_hook(profile: SceneReaderJourneyProfileItem) -> bool:
    return any(bool(item.evidence_paragraph_ids) for item in profile.hooks)


def assess_score_distribution(
    profiles: list[SceneReaderJourneyProfileItem],
) -> dict[str, object]:
    """Hard-validate illegal high scores; return soft distribution warnings.

    All-high hook_score alone is suspicious but not automatically fatal when each
    high score is backed by Hook objects with Evidence (DEFECT-CANARY-007).
    """
    warnings: list[dict[str, object]] = []
    ordered = sorted(profiles, key=lambda item: item.scene_ordinal)
    if not ordered:
        return {"warnings": warnings, "requires_review": False}

    for profile in ordered:
        if profile.hook_score > 100 or profile.hook_score < 0:
            _raise(
                "JOURNEY_SCORE_OUT_OF_RANGE",
                f"hook_score 越界: scene={profile.scene_ordinal} score={profile.hook_score}",
                failed_field="hook_score",
            )
        if profile.hook_score > 80:
            if not profile.hooks:
                _raise(
                    "JOURNEY_HIGH_HOOK_WITHOUT_HOOK_OBJECT",
                    f"hook_score>80 但无 Hook 对象: scene={profile.scene_ordinal}",
                    failed_field="hooks",
                )
            if not _profile_has_evidenced_hook(profile):
                _raise(
                    "JOURNEY_HIGH_HOOK_WITHOUT_EVIDENCE",
                    f"hook_score>80 但 Hook 无 Evidence: scene={profile.scene_ordinal}",
                    failed_field="hooks",
                )

    high_hooks = sum(1 for item in ordered if item.hook_score > 80)
    low_risks = sum(1 for item in ordered if item.dropoff_risk_score < 10)
    requires_review = False

    if len(ordered) >= 2 and high_hooks == len(ordered):
        code = (
            "JOURNEY_SMALL_SAMPLE_ALL_HIGH"
            if len(ordered) <= 3
            else "JOURNEY_ALL_HOOK_SCORES_HIGH"
        )
        warnings.append(
            {
                "code": code,
                "message": "全部 Scene 的 hook_score>80；已核验 Hook+Evidence，记为可疑分布而非自动失败",
                "scene_count": len(ordered),
                "hook_scores": [item.hook_score for item in ordered],
                "severity": "strong" if len(ordered) >= 10 else "moderate",
            }
        )
        requires_review = True

    hook_scores = [item.hook_score for item in ordered]
    if len(ordered) >= 3 and len(set(hook_scores)) == 1:
        warnings.append(
            {
                "code": "JOURNEY_REPEATED_SCORE_PATTERN",
                "message": f"全部 Scene hook_score 相同={hook_scores[0]}，疑似默认值或复制",
                "hook_score": hook_scores[0],
            }
        )
        requires_review = True

    # tension/curiosity mirrored onto hook_score for every scene
    if len(ordered) >= 3 and all(
        item.hook_score == item.tension_score == item.curiosity_score for item in ordered
    ):
        warnings.append(
            {
                "code": "JOURNEY_SCORE_DEFAULT_PATTERN_CONFIRMED",
                "message": "hook/tension/curiosity 三指标全 Scene 完全一致，疑似复制",
            }
        )
        requires_review = True

    if len(ordered) >= 3 and low_risks == len(ordered):
        _raise(
            "JOURNEY_UNREALISTIC_RISK_DISTRIBUTION",
            "不允许所有 dropoff_risk 都低于 10",
        )

    empty_qin = sum(1 for item in ordered if not item.reader_question_in)
    if len(ordered) >= 3 and empty_qin == len(ordered):
        _raise(
            "JOURNEY_QUESTION_CHAIN_ALL_EMPTY_IN",
            "不允许全部 Scene 的 reader_question_in 均为空；Scene 2+ 必须承接前序活跃问题",
        )

    streak = 0
    for profile in ordered:
        no_payoff = (not profile.payoffs) or profile.payoff_score < 30
        if no_payoff:
            streak += 1
            if streak >= 2:
                has_risk = any(
                    item.type in {"low_payoff", "consecutive_no_payoff"}
                    for item in profile.risk_points
                )
                if not has_risk:
                    _raise(
                        "JOURNEY_CONSECUTIVE_NO_PAYOFF",
                        f"连续{streak}个Scene无有效payoff时必须进入风险诊断（low_payoff/consecutive_no_payoff）",
                    )
        else:
            streak = 0

    return {
        "warnings": warnings,
        "requires_review": requires_review,
        "legacy_code_if_fatal": "JOURNEY_SCORE_DISTRIBUTION_SUSPICIOUS",
    }


def validate_score_distribution(profiles: list[SceneReaderJourneyProfileItem]) -> dict[str, object]:
    """Backward-compatible entry: hard errors raise; soft issues returned as warnings. """
    return assess_score_distribution(profiles)


def adaptive_phase_count_bounds(scene_count: int) -> tuple[int, int]:
    """Hard contract: 1 <= phase_count <= min(6, scene_count).

    Longer chapters may still *suggest* 3–6 phases in prompts; that is not a hard floor.
    """
    if scene_count < 1:
        return (1, 1)
    return (1, min(6, scene_count))


def validate_chapter_synthesis(
    result: ChapterReaderJourneySynthesisResult,
    *,
    total_scene_count: int,
    enforce_anti_generic: bool = True,
) -> None:
    scene_count = int(total_scene_count)
    if scene_count < 1:
        _raise("JOURNEY_PHASE_COUNT_INVALID", "scene_count 必须 >= 1")

    phases = list(result.phases)
    phase_count = len(phases)
    min_phases, max_phases = adaptive_phase_count_bounds(scene_count)
    if not (min_phases <= phase_count <= max_phases):
        _raise(
            "JOURNEY_PHASE_COUNT_INVALID",
            (
                f"phase_count={phase_count} 超出自适应范围 "
                f"[{min_phases}, {max_phases}]（scene_count={scene_count}；"
                f"硬上限 min(6, scene_count)）"
            ),
            repair_context={
                "error_code": "JOURNEY_PHASE_COUNT_INVALID",
                "scene_count": scene_count,
                "phase_count": phase_count,
                "min_phases": min_phases,
                "max_phases": max_phases,
                "guidance": (
                    "仅当超出自适应范围时调整数量；不得为凑满建议值编造虚假阶段；"
                    "数量偏多时合并无真实结构依据的 Phase；数量为 0 时至少保留 1 个覆盖全部 Scene 的 Phase。"
                ),
            },
        )

    by_ordinal = sorted(phases, key=lambda item: item.ordinal)
    expected_ordinals = list(range(1, phase_count + 1))
    actual_ordinals = [item.ordinal for item in by_ordinal]
    if actual_ordinals != expected_ordinals:
        _raise(
            "JOURNEY_PHASE_ORDER_INVALID",
            f"Phase ordinal 必须为连续 1..{phase_count}，实际={actual_ordinals}",
        )
    by_start = sorted(phases, key=lambda item: (item.start_scene_ordinal, item.ordinal))
    if [item.ordinal for item in by_start] != actual_ordinals:
        _raise(
            "JOURNEY_PHASE_ORDER_INVALID",
            "Phase 必须按 Scene 顺序排列（start_scene_ordinal 随 ordinal 递增）",
        )

    covered: set[int] = set()
    prev_end = 0
    for phase in by_ordinal:
        if phase.start_scene_ordinal > phase.end_scene_ordinal:
            _raise(
                "JOURNEY_PHASE_RANGE_NONCONTIGUOUS",
                (
                    f"Phase {phase.ordinal} 覆盖区间非连续："
                    f"start={phase.start_scene_ordinal} > end={phase.end_scene_ordinal}"
                ),
            )
        if prev_end > 0 and phase.start_scene_ordinal < prev_end:
            _raise(
                "JOURNEY_PHASE_SCENE_OVERLAP",
                (
                    f"Phase {phase.ordinal} 与前序 Phase 区间重叠："
                    f"start={phase.start_scene_ordinal} < prev_end={prev_end}"
                ),
            )
        if prev_end > 0 and phase.start_scene_ordinal == prev_end:
            _raise(
                "JOURNEY_PHASE_DUPLICATE_SCENE",
                (
                    f"Scene ordinal {phase.start_scene_ordinal} 被多个 Phase 重复归属"
                    f"（Phase 边界贴合重复）"
                ),
            )
        if prev_end > 0 and phase.start_scene_ordinal > prev_end + 1:
            _raise(
                "JOURNEY_PHASE_SCENE_GAP",
                (
                    f"Phase 之间 Scene 覆盖缺口："
                    f"prev_end={prev_end} → next_start={phase.start_scene_ordinal}"
                ),
            )
        for ordinal in range(phase.start_scene_ordinal, phase.end_scene_ordinal + 1):
            if ordinal in covered:
                _raise(
                    "JOURNEY_PHASE_DUPLICATE_SCENE",
                    f"Scene ordinal {ordinal} 被多个 Phase 重复归属",
                )
            covered.add(ordinal)
        prev_end = phase.end_scene_ordinal

    expected = set(range(1, scene_count + 1))
    if covered != expected:
        missing = sorted(expected - covered)
        extra = sorted(covered - expected)
        _raise(
            "JOURNEY_PHASE_SCENE_GAP",
            (
                "阶段必须完整覆盖全部 Scene 且不得越界；"
                f"missing={missing} extra={extra}"
            ),
        )

    if not result.one_sentence_diagnosis.strip():
        _raise("JOURNEY_SYNTHESIS_FAILED", "一句话诊断不能为空")
    diagnosis_blob = "\n".join(
        [result.one_sentence_diagnosis]
        + list(result.pacing_diagnosis)
        + list(result.chapter_strengths)
        + list(result.chapter_risks)
    )
    if enforce_anti_generic:
        for phrase in CHAPTER_BANNED_PHRASES:
            if phrase in diagnosis_blob:
                _raise(
                    "JOURNEY_CHAPTER_DIAGNOSIS_GENERIC",
                    f"章级诊断禁止泛化措辞：{phrase}",
                )
    hook_terms = Counter()
    for text in result.chapter_reader_question_chain:
        if not text.strip():
            _raise("JOURNEY_QUESTION_CHAIN_INVALID", "问题链项不能为空")
        hook_terms[text.strip()] += 1
    if result.chapter_strengths and all(
        "伏笔" in item for item in result.chapter_strengths[:3]
    ):
        _raise("JOURNEY_SCORE_DISTRIBUTION_SUSPICIOUS", "不能把普通动作全部标为强钩子")
