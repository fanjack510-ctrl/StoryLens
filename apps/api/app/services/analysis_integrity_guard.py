"""Read-time Reader Journey integrity scan (does not mutate stored payloads)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, Chapter, Paragraph, Scene, SceneReaderJourneyProfile
from app.services.analysis_context_fingerprint import (
    compute_source_context_fingerprint,
    fingerprint_digest_short,
    paragraph_content_hash,
)
from app.services.analysis_grounding import (
    ERROR_CONTEXT_MISMATCH,
    ERROR_EVIDENCE_CLAIM,
    ERROR_EVIDENCE_SCOPE,
    ERROR_GROUNDING_ENTITY,
    GroundingIssue,
    GroundingReport,
    classify_integrity_status,
    extract_paragraph_ids,
    is_craft_commentary_text,
    is_severe_grounding_issue,
    validate_claim_entities_against_evidence,
    validate_entities_in_scene_or_aliases,
    validate_evidence_scope,
)


CLAIM_FIELDS = (
    "scene_value_summary",
    "overview",
    "title",
    "scene_title",
)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _paragraphs_for_scene(session: Session, scene: Scene) -> list[Paragraph]:
    start = session.scalar(select(Paragraph).where(Paragraph.id == scene.start_paragraph_id))
    end = session.scalar(select(Paragraph).where(Paragraph.id == scene.end_paragraph_id))
    if start is None or end is None:
        return []
    lo = min(start.paragraph_index, end.paragraph_index)
    hi = max(start.paragraph_index, end.paragraph_index)
    return list(
        session.scalars(
            select(Paragraph)
            .where(
                Paragraph.chapter_id == scene.chapter_id,
                Paragraph.paragraph_index >= lo,
                Paragraph.paragraph_index <= hi,
            )
            .order_by(Paragraph.paragraph_index)
        )
    )


def ensure_analysis_run_scope(
    session: Session,
    *,
    analysis_run_id: int,
    book_id: int | None = None,
    chapter_id: int | None = None,
) -> AnalysisRun:
    """Raise ValueError(ANALYSIS_RUN_SCOPE_MISMATCH) when route scope disagrees."""
    from app.services.analysis_grounding import ERROR_RUN_SCOPE

    run = session.get(AnalysisRun, analysis_run_id)
    if run is None:
        raise LookupError("ANALYSIS_RUN_NOT_FOUND")
    if chapter_id is not None and str(run.subject_id) != str(chapter_id):
        raise ValueError(ERROR_RUN_SCOPE)
    if book_id is not None:
        chapter = session.get(Chapter, int(run.subject_id)) if str(run.subject_id).isdigit() else None
        if chapter is None or int(chapter.book_id) != int(book_id):
            raise ValueError(ERROR_RUN_SCOPE)
    return run


def scan_journey_profile_grounding(
    session: Session,
    *,
    profile: SceneReaderJourneyProfile,
    book_id: int,
    chapter_id: int,
    analysis_run_id: int,
    prompt_version: str | None = None,
    contract_version: str | None = None,
    formula_version: str | None = None,
) -> GroundingReport:
    scene = session.get(Scene, profile.scene_id)
    issues: list[GroundingIssue] = []
    fingerprint_state = "missing_legacy"
    fingerprint: str | None = None

    if scene is None:
        issues.append(
            GroundingIssue(
                code=ERROR_CONTEXT_MISMATCH,
                message="Scene记录缺失",
                scene_id=profile.scene_id,
                scene_ordinal=profile.scene_ordinal,
            )
        )
        status = classify_integrity_status(issues, fingerprint_state="mismatch")
        return GroundingReport(ok=False, integrity_status=status, issues=issues, fingerprint_state="mismatch")

    if int(scene.book_id) != int(book_id) or int(scene.chapter_id) != int(chapter_id):
        issues.append(
            GroundingIssue(
                code=ERROR_CONTEXT_MISMATCH,
                message="Scene不属于当前Book/Chapter",
                scene_id=scene.id,
                scene_ordinal=profile.scene_ordinal,
            )
        )

    paras = _paragraphs_for_scene(session, scene)
    ordered_ids = [p.id for p in paras]
    hashes = [paragraph_content_hash(p.raw_text) for p in paras]
    text_by_id = {p.id: (p.raw_text or "") for p in paras}
    scene_text = "\n".join(text_by_id[pid] for pid in ordered_ids)
    book_prefix = f"B{int(book_id):04d}-"

    try:
        payload = json.loads(profile.payload_json or "{}")
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    stored_fp = payload.get("source_context_fingerprint")
    expected_fp = compute_source_context_fingerprint(
        book_id=book_id,
        chapter_id=chapter_id,
        analysis_run_id=analysis_run_id,
        scene_id=scene.id,
        ordered_paragraph_ids=ordered_ids,
        paragraph_content_hashes=hashes,
        prompt_version=prompt_version,
        contract_version=contract_version,
        formula_version=formula_version,
    )
    fingerprint = expected_fp
    if isinstance(stored_fp, str) and stored_fp:
        if stored_fp != expected_fp:
            fingerprint_state = "mismatch"
            issues.append(
                GroundingIssue(
                    code=ERROR_CONTEXT_MISMATCH,
                    message="source_context_fingerprint与当前正文不一致",
                    scene_id=scene.id,
                    scene_ordinal=profile.scene_ordinal,
                )
            )
        else:
            fingerprint_state = "ok"
    else:
        fingerprint_state = "missing_legacy"

    evidence_ids = [
        str(x)
        for x in (payload.get("evidence_paragraph_ids") or [])
        if isinstance(x, (str, int))
    ]
    if not evidence_ids:
        evidence_ids = extract_paragraph_ids(_as_text(payload))

    issues.extend(
        validate_evidence_scope(
            evidence_paragraph_ids=evidence_ids,
            allowed_paragraph_ids=ordered_ids,
            book_prefix=book_prefix,
            scene_id=scene.id,
            scene_ordinal=profile.scene_ordinal,
        )
    )

    claim_parts = [profile.scene_value_summary or ""]
    for key in CLAIM_FIELDS:
        claim_parts.append(_as_text(payload.get(key)))
    claim_text = "\n".join(p for p in claim_parts if p)

    # Per-item claim ↔ evidence bindings (hooks/payoffs/questions).
    for collection_name in (
        "hooks",
        "payoffs",
        "reader_question_in",
        "reader_question_out",
        "reader_question_created",
        "reader_question_answered",
        "risk_points",
        "techniques",
        "writing_takeaways",
    ):
        items = payload.get(collection_name) or []
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            item_claim = " ".join(
                _as_text(item.get(k))
                for k in (
                    "summary",
                    "question",
                    "known",
                    "gap",
                    "continue_drive",
                    "next_handoff",
                    "name",
                    "description",
                    "takeaway",
                )
            )
            cited = [
                str(x)
                for x in (item.get("evidence_paragraph_ids") or [])
                if isinstance(x, (str, int))
            ]
            if not cited or not item_claim.strip():
                continue
            issues.extend(
                validate_evidence_scope(
                    evidence_paragraph_ids=cited,
                    allowed_paragraph_ids=ordered_ids,
                    book_prefix=book_prefix,
                    scene_id=scene.id,
                    scene_ordinal=profile.scene_ordinal,
                )
            )
            # Claim↔entity heuristics are only reliable once a fingerprint exists.
            # Legacy artifacts without fingerprint still get wrong-book scope checks,
            # but craft-language false positives must not block whole journeys.
            if fingerprint_state != "ok":
                continue
            issues.extend(
                validate_claim_entities_against_evidence(
                    claim_text=item_claim,
                    evidence_texts=text_by_id,
                    cited_paragraph_ids=cited,
                    scene_id=scene.id,
                    scene_ordinal=profile.scene_ordinal,
                    field_path=f"{collection_name}[{idx}]",
                    min_unsupported_entities=1,
                )
            )
            issues.extend(
                validate_entities_in_scene_or_aliases(
                    claim_text=item_claim,
                    scene_text="\n".join(text_by_id.get(pid, "") for pid in cited) + "\n" + scene_text,
                    alias_texts=[scene_text],
                    scene_id=scene.id,
                    scene_ordinal=profile.scene_ordinal,
                    field_path=f"{collection_name}[{idx}]",
                    min_foreign_entities=2,
                )
            )

    status = classify_integrity_status(issues, fingerprint_state=fingerprint_state)
    ok = status in {"trusted", "legacy_unverified", "partially_trusted"}
    return GroundingReport(
        ok=ok,
        integrity_status=status,
        issues=issues,
        fingerprint=fingerprint,
        fingerprint_state=fingerprint_state,
    )


def _field_results_from_issues(issues: list[GroundingIssue]) -> list[dict[str, Any]]:
    by_field: dict[str, list[GroundingIssue]] = {}
    for issue in issues:
        key = issue.field_path or "_scene"
        by_field.setdefault(key, []).append(issue)
    out: list[dict[str, Any]] = []
    for field_name, field_issues in by_field.items():
        severe = any(is_severe_grounding_issue(i) for i in field_issues)
        out.append(
            {
                "field_name": field_name,
                "status": "failed" if severe else "degraded",
                "evidence_status": "failed",
                "display_policy": "hide_scene" if severe else "hide_field",
                "error_codes": sorted({i.code for i in field_issues}),
            }
        )
    return out


def _aggregate_overall_status(scene_statuses: list[str]) -> str:
    if not scene_statuses:
        return "legacy_unverified"
    failed = [s for s in scene_statuses if s in {"data_integrity_failed", "invalid_context"}]
    partial = [s for s in scene_statuses if s == "partially_trusted"]
    legacy = [s for s in scene_statuses if s == "legacy_unverified"]
    trusted = [s for s in scene_statuses if s == "trusted"]
    # Multiple severely polluted core scenes → hard fail.
    if len(failed) >= 2 or (len(failed) >= 1 and len(failed) / max(1, len(scene_statuses)) >= 0.5):
        return "data_integrity_failed"
    if len(failed) == 1:
        return "partially_trusted"
    if partial:
        return "partially_trusted"
    if legacy and not trusted:
        return "legacy_unverified"
    if legacy and trusted:
        return "partially_trusted"
    return "trusted"


def scan_reader_journey_integrity(
    session: Session,
    *,
    journey_run,
) -> dict[str, Any]:
    profiles = list(
        session.scalars(
            select(SceneReaderJourneyProfile)
            .where(SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id)
            .order_by(SceneReaderJourneyProfile.scene_ordinal)
        )
    )
    scene_reports: list[dict[str, Any]] = []
    field_results: list[dict[str, Any]] = []
    for profile in profiles:
        report = scan_journey_profile_grounding(
            session,
            profile=profile,
            book_id=journey_run.book_id,
            chapter_id=journey_run.chapter_id,
            analysis_run_id=journey_run.analysis_run_id,
            prompt_version=journey_run.scene_prompt_version,
            contract_version=journey_run.scene_contract_version,
            formula_version=journey_run.formula_version,
        )
        fields = _field_results_from_issues(report.issues)
        for item in fields:
            item = dict(item)
            item["scene_id"] = profile.scene_id
            item["scene_ordinal"] = profile.scene_ordinal
            field_results.append(item)
        safe = report.integrity_status in {"trusted", "legacy_unverified", "partially_trusted"}
        scene_reports.append(
            {
                "scene_id": profile.scene_id,
                "scene_ordinal": profile.scene_ordinal,
                "integrity_status": report.integrity_status,
                "status": report.integrity_status,
                "fingerprint_state": report.fingerprint_state,
                "fingerprint_digest": fingerprint_digest_short(report.fingerprint),
                "issue_codes": sorted({i.code for i in report.issues}),
                "failed_fields": [f["field_name"] for f in fields],
                "error_codes": sorted({i.code for i in report.issues}),
                "issue_count": len(report.issues),
                "safe_to_display": safe,
                "display_allowed": safe,
                "field_results": fields,
            }
        )

    overall = _aggregate_overall_status([s["integrity_status"] for s in scene_reports])
    blocked = [
        s
        for s in scene_reports
        if s["integrity_status"] in {"data_integrity_failed", "invalid_context"}
    ]
    display_policy = {
        "trusted": "show_full",
        "partially_trusted": "show_partial",
        "legacy_unverified": "show_legacy",
        "data_integrity_failed": "block",
        "invalid_context": "block",
    }.get(overall, "block")

    legacy_warning = None
    user_message = None
    if overall == "legacy_unverified":
        legacy_warning = "旧版分析尚未完成来源校验，仅供参考。"
        user_message = legacy_warning
    elif overall == "partially_trusted":
        user_message = "部分分析结果未通过校验，受影响内容已单独隐藏。"
    elif overall in {"data_integrity_failed", "invalid_context"}:
        user_message = "检测到分析内容可能不属于当前正文，已停止展示不可信结果。"

    return {
        "integrity_status": overall,
        "overall_status": overall,
        "overall_display_policy": display_policy,
        "trusted": overall == "trusted",
        "partially_trusted": overall == "partially_trusted",
        "untrusted": overall in {"data_integrity_failed", "invalid_context"},
        "legacy_unverified": overall == "legacy_unverified",
        "legacy_warning": legacy_warning,
        "blocked_scene_count": len(blocked),
        "blocked_sections": [
            {
                "scene_id": s["scene_id"],
                "scene_ordinal": s["scene_ordinal"],
                "reason": s["integrity_status"],
                "error_codes": s["error_codes"],
            }
            for s in blocked
        ],
        "scene_reports": scene_reports,
        "scene_integrity": scene_reports,
        "field_integrity": field_results,
        "integrity_summary": {
            "scene_count": len(scene_reports),
            "blocked_scene_count": len(blocked),
            "field_issue_count": len(field_results),
            "fingerprint_missing": all(
                s.get("fingerprint_state") == "missing_legacy" for s in scene_reports
            )
            if scene_reports
            else True,
        },
        "user_message": user_message,
        "error_code": (
            "DATA_INTEGRITY_FAILED"
            if overall in {"data_integrity_failed", "invalid_context"}
            else None
        ),
    }


def is_chart_eligible_node(node: dict[str, Any] | None) -> bool:
    """Chart series consume numeric scene nodes; markers/summaries are not required to have scores."""
    if not node or not isinstance(node, dict):
        return False
    if node.get("integrity_blocked"):
        return False
    node_type = str(node.get("node_type") or node.get("role") or "scene").lower()
    non_chart = {
        "phase_summary",
        "separator",
        "annotation",
        "hook_event",
        "payoff_event",
        "diagnostic_marker",
        "redacted_placeholder",
        "legacy_summary",
    }
    if node_type in non_chart:
        return False
    scores = node.get("scores")
    engagement = node.get("engagement")
    return isinstance(scores, dict) or isinstance(engagement, dict)


def redact_visualization_for_integrity(
    visualization: dict[str, Any] | None,
    integrity: dict[str, Any],
) -> dict[str, Any] | None:
    """Apply graded redaction. Never wipe an entire legacy/partial journey for soft issues."""
    if not visualization or not isinstance(visualization, dict):
        return visualization

    status = str(integrity.get("integrity_status") or "")
    out = dict(visualization)
    out["integrity"] = {
        "status": status,
        "overall_display_policy": integrity.get("overall_display_policy"),
        "legacy_unverified": bool(integrity.get("legacy_unverified")),
        "partially_trusted": bool(integrity.get("partially_trusted")),
        "legacy_warning": integrity.get("legacy_warning"),
        "user_message": integrity.get("user_message"),
        "error_code": integrity.get("error_code"),
        "blocked_scene_count": integrity.get("blocked_scene_count"),
        "blocked_sections": integrity.get("blocked_sections"),
    }

    # Legacy + trusted: keep full visualization (legacy shows warning only).
    if status in {"trusted", "legacy_unverified"}:
        return out

    blocked = {
        int(s["scene_ordinal"])
        for s in integrity.get("scene_reports", [])
        if s.get("integrity_status") in {"data_integrity_failed", "invalid_context"}
    }
    hide_fields_by_scene: dict[int, set[str]] = {}
    for fr in integrity.get("field_integrity") or []:
        if fr.get("display_policy") != "hide_field":
            continue
        ord_ = int(fr.get("scene_ordinal") or 0)
        name = str(fr.get("field_name") or "")
        # hooks[0] → hooks
        base = name.split("[", 1)[0]
        hide_fields_by_scene.setdefault(ord_, set()).add(base)

    nodes = []
    for node in visualization.get("scene_nodes") or []:
        if not isinstance(node, dict):
            continue
        ordinal = int(node.get("scene_ordinal") or 0)
        if status in {"data_integrity_failed", "invalid_context"} and ordinal in blocked:
            nodes.append(
                {
                    "scene_id": node.get("scene_id"),
                    "scene_ordinal": ordinal,
                    "role": node.get("role"),
                    "node_type": node.get("node_type") or "redacted_placeholder",
                    "integrity_blocked": True,
                    "integrity_status": "data_integrity_failed",
                    "chart_eligible": False,
                    "title": "分析结果校验未通过",
                    "overview": "该项暂不展示",
                    "hooks": [],
                    "payoffs": [],
                    "questions": [],
                    "techniques": [],
                    "evidence": [],
                }
            )
            continue
        if status == "partially_trusted" and ordinal in blocked:
            # Isolate one severe scene but keep chart shell fields if present.
            redacted = dict(node)
            for key in ("hooks", "payoffs", "questions", "techniques", "evidence"):
                redacted[key] = []
            redacted["overview"] = "该项暂不展示"
            redacted["integrity_blocked"] = True
            redacted["integrity_status"] = "data_integrity_failed"
            redacted["chart_eligible"] = is_chart_eligible_node(node)
            nodes.append(redacted)
            continue
        if status == "partially_trusted":
            redacted = dict(node)
            for field_name in hide_fields_by_scene.get(ordinal, set()):
                if field_name in redacted and isinstance(redacted[field_name], list):
                    redacted[field_name] = []
            redacted["chart_eligible"] = is_chart_eligible_node(redacted)
            nodes.append(redacted)
            continue
        annotated = dict(node)
        annotated["chart_eligible"] = is_chart_eligible_node(annotated)
        nodes.append(annotated)

    out["scene_nodes"] = nodes
    return out
