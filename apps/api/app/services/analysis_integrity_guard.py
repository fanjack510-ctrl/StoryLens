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
    GroundingIssue,
    GroundingReport,
    classify_integrity_status,
    extract_paragraph_ids,
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
            # Entity check only against cited evidence + full scene aliases.
            issues.extend(
                validate_entities_in_scene_or_aliases(
                    claim_text=item_claim,
                    scene_text="\n".join(text_by_id.get(pid, "") for pid in cited),
                    alias_texts=[scene_text],
                    scene_id=scene.id,
                    scene_ordinal=profile.scene_ordinal,
                    field_path=f"{collection_name}[{idx}]",
                    min_foreign_entities=2,
                )
            )

    status = classify_integrity_status(issues, fingerprint_state=fingerprint_state)
    ok = status in {"trusted", "legacy_unverified"}
    return GroundingReport(
        ok=ok,
        integrity_status=status,
        issues=issues,
        fingerprint=fingerprint,
        fingerprint_state=fingerprint_state,
    )


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
    worst = "trusted"
    rank = {
        "trusted": 0,
        "legacy_unverified": 1,
        "data_integrity_failed": 2,
        "invalid_context": 3,
    }
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
        if rank.get(report.integrity_status, 0) > rank.get(worst, 0):
            worst = report.integrity_status
        scene_reports.append(
            {
                "scene_id": profile.scene_id,
                "scene_ordinal": profile.scene_ordinal,
                "integrity_status": report.integrity_status,
                "fingerprint_state": report.fingerprint_state,
                "fingerprint_digest": fingerprint_digest_short(report.fingerprint),
                "issue_codes": sorted({i.code for i in report.issues}),
                "issue_count": len(report.issues),
                "display_allowed": report.ok and report.integrity_status != "invalid_context",
            }
        )

    blocked = [s for s in scene_reports if not s["display_allowed"] or s["integrity_status"] in {
        "data_integrity_failed",
        "invalid_context",
    }]
    return {
        "integrity_status": worst if profiles else "legacy_unverified",
        "trusted": worst == "trusted",
        "untrusted": worst in {"data_integrity_failed", "invalid_context"},
        "legacy_unverified": worst == "legacy_unverified",
        "blocked_scene_count": len(blocked),
        "scene_reports": scene_reports,
        "user_message": (
            "检测到分析结果与当前正文不一致，已暂停展示。"
            if worst in {"data_integrity_failed", "invalid_context"}
            else (
                "旧版结果未完成来源校验，仅可只读查看，不可升级为正式叙事资产。"
                if worst == "legacy_unverified"
                else None
            )
        ),
        "error_code": (
            "ANALYSIS_CONTEXT_MISMATCH"
            if worst == "invalid_context"
            else ("DATA_INTEGRITY_FAILED" if worst == "data_integrity_failed" else None)
        ),
    }


def redact_visualization_for_integrity(
    visualization: dict[str, Any] | None,
    integrity: dict[str, Any],
) -> dict[str, Any] | None:
    """Hide contaminated scene detail fields while keeping shell structure."""
    if not visualization or not isinstance(visualization, dict):
        return visualization
    if not integrity.get("untrusted"):
        # Still annotate legacy
        out = dict(visualization)
        out["integrity"] = {
            "status": integrity.get("integrity_status"),
            "legacy_unverified": bool(integrity.get("legacy_unverified")),
        }
        return out

    blocked = {
        int(s["scene_ordinal"])
        for s in integrity.get("scene_reports", [])
        if s.get("integrity_status") in {"data_integrity_failed", "invalid_context"}
    }
    pause_all = False
    nodes = []
    for node in visualization.get("scene_nodes") or []:
        if not isinstance(node, dict):
            continue
        ordinal = int(node.get("scene_ordinal") or 0)
        if pause_all or ordinal in blocked:
            nodes.append(
                {
                    "scene_id": node.get("scene_id"),
                    "scene_ordinal": ordinal,
                    "role": node.get("role"),
                    "integrity_blocked": True,
                    "integrity_status": next(
                        (
                            s["integrity_status"]
                            for s in integrity.get("scene_reports", [])
                            if int(s["scene_ordinal"]) == ordinal
                        ),
                        "data_integrity_failed",
                    ),
                    "title": "分析结果校验未通过",
                    "overview": "检测到部分结论与当前正文不一致，相关结果已暂停展示。",
                    "hooks": [],
                    "payoffs": [],
                    "questions": [],
                    "techniques": [],
                    "evidence": [],
                }
            )
        else:
            nodes.append(node)
    out = dict(visualization)
    out["scene_nodes"] = nodes
    out["integrity"] = {
        "status": integrity.get("integrity_status"),
        "error_code": integrity.get("error_code"),
        "user_message": integrity.get("user_message"),
        "blocked_scene_count": integrity.get("blocked_scene_count"),
    }
    return out
