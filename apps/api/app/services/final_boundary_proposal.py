"""Build a chapter-final scene boundary proposal from review candidates.

Generic structural rules only — no book/chapter/content-specific heuristics.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BoundaryReviewDecision, BoundaryReviewSession, Paragraph
from app.services.scene_fragment_consolidation import BoundaryMeta, consolidate_boundary_ids
from app.services.scene_pipeline import scene_ranges


@dataclass
class FinalBoundaryProposal:
    review_id: int
    analysis_run_id: int
    chapter_id: int
    validation_status: str  # valid | unresolved
    proposal_fingerprint: str
    final_boundary_left_ids: list[str]
    final_scene_ranges: list[dict[str, Any]]
    source_summary: dict[str, Any]
    unresolved_reason: str | None = None
    paragraph_count: int = 0
    scene_count: int = 0
    selected_transition_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "analysis_run_id": self.analysis_run_id,
            "chapter_id": self.chapter_id,
            "validation_status": self.validation_status,
            "proposal_fingerprint": self.proposal_fingerprint,
            "final_boundary_left_ids": list(self.final_boundary_left_ids),
            "final_scene_ranges": list(self.final_scene_ranges),
            "source_summary": dict(self.source_summary),
            "unresolved_reason": self.unresolved_reason,
            "paragraph_count": self.paragraph_count,
            "scene_count": self.scene_count,
            "selected_transition_ids": list(self.selected_transition_ids),
        }


def _paragraphs(session: Session, chapter_id: int) -> list[Paragraph]:
    return list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )


def _fingerprint(review_id: int, left_ids: list[str], status: str) -> str:
    payload = {
        "review_id": review_id,
        "left_ids": left_ids,
        "status": status,
        "contract": "final_boundary_proposal.v1",
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _rank_candidate(item: BoundaryReviewDecision) -> tuple:
    """Higher is better. Generic structural preference only."""
    accepted = 1 if item.user_decision in {"accept", "manually_added"} else 0
    rejected = -1 if item.user_decision == "reject" else 0
    legal = 1 if item.deterministic_legal else 0
    model_boundary = 1 if item.model_boundary_candidate else 0
    conflict_penalty = -1 if item.semantic_conflict and not item.deterministic_legal else 0
    confidence = float(item.model_confidence or 0.0)
    manual = 1 if item.user_decision == "manually_added" or not item.model_candidate else 0
    return (accepted, rejected, legal, model_boundary, conflict_penalty, manual, confidence)


def _should_keep_group(items: list[BoundaryReviewDecision]) -> BoundaryReviewDecision | None:
    if not items:
        return None
    # Explicit user reject wins when every decision at this gap is rejected.
    if all(item.user_decision == "reject" for item in items):
        return None
    # Prefer any accepted / manual.
    accepted = [item for item in items if item.user_decision in {"accept", "manually_added"}]
    if accepted:
        return max(accepted, key=_rank_candidate)
    # Pending / mixed: pick best structural candidate that claims a boundary.
    ranked = sorted(items, key=_rank_candidate, reverse=True)
    best = ranked[0]
    if best.user_decision == "reject":
        return None
    if best.deterministic_legal:
        return best
    if best.model_boundary_candidate and not (
        best.semantic_conflict and not best.deterministic_legal
    ):
        return best
    if best.user_decision == "manually_added":
        return best
    # Conflict without legal reason: do not force a cut.
    if best.semantic_conflict and not best.deterministic_legal:
        return None
    if best.model_boundary_candidate:
        return best
    return None


def build_final_boundary_proposal(
    session: Session, review: BoundaryReviewSession
) -> FinalBoundaryProposal:
    paragraphs = _paragraphs(session, review.chapter_id)
    position = {item.id: index for index, item in enumerate(paragraphs)}
    decisions = list(
        session.scalars(
            select(BoundaryReviewDecision).where(
                BoundaryReviewDecision.review_session_id == review.id
            )
        )
    )

    by_left: dict[str, list[BoundaryReviewDecision]] = {}
    for item in decisions:
        left = str(item.left_paragraph_id or "")
        if not left:
            continue
        by_left.setdefault(left, []).append(item)

    selected: list[BoundaryReviewDecision] = []
    for left_id in sorted(by_left.keys(), key=lambda x: position.get(x, 10**9)):
        if left_id not in position:
            continue
        if position[left_id] >= len(paragraphs) - 1:
            continue
        chosen = _should_keep_group(by_left[left_id])
        if chosen is not None:
            selected.append(chosen)

    # Deduplicate by left id (already unique) and normalize order.
    left_ids = []
    seen: set[str] = set()
    selected_by_left: dict[str, BoundaryReviewDecision] = {}
    for item in selected:
        left = item.left_paragraph_id
        if left in seen:
            continue
        seen.add(left)
        left_ids.append(left)
        selected_by_left[left] = item

    boundary_meta = {
        left: BoundaryMeta(
            reason_codes=frozenset(
                [item.model_reason_code] if item and item.model_reason_code else []
            ),
            concise_reason=(
                (item.deterministic_reason or item.manual_reason_type or item.user_reason or "")
                if item
                else ""
            ),
        )
        for left, item in selected_by_left.items()
    }

    consolidated = consolidate_boundary_ids(paragraphs, left_ids, boundary_meta)
    source_summary = {
        "candidate_decision_count": len(decisions),
        "selected_before_consolidate": len(left_ids),
        "selected_after_consolidate": len(consolidated),
        "accepted_prior": sum(1 for d in decisions if d.user_decision == "accept"),
        "rejected_prior": sum(1 for d in decisions if d.user_decision == "reject"),
        "pending_prior": sum(1 for d in decisions if d.user_decision == "pending"),
        "conflict_prior": sum(1 for d in decisions if d.semantic_conflict),
    }

    try:
        ranges = scene_ranges(
            paragraphs,
            consolidated,
            consolidate_short_fragments=False,
            boundary_meta=boundary_meta,
        )
    except ValueError as exc:
        fp = _fingerprint(review.id, consolidated, "unresolved")
        return FinalBoundaryProposal(
            review_id=review.id,
            analysis_run_id=review.analysis_run_id,
            chapter_id=review.chapter_id,
            validation_status="unresolved",
            proposal_fingerprint=fp,
            final_boundary_left_ids=list(consolidated),
            final_scene_ranges=[],
            source_summary=source_summary,
            unresolved_reason=str(exc) or "当前候选无法形成完整、合法的场景划分",
            paragraph_count=len(paragraphs),
            scene_count=0,
            selected_transition_ids=[
                selected_by_left[left].transition_id
                for left in consolidated
                if left in selected_by_left
            ],
        )

    # Empty scenes / inverted ranges already rejected by scene_ranges.
    for start, end in ranges:
        if start.paragraph_index > end.paragraph_index:
            fp = _fingerprint(review.id, consolidated, "unresolved")
            return FinalBoundaryProposal(
                review_id=review.id,
                analysis_run_id=review.analysis_run_id,
                chapter_id=review.chapter_id,
                validation_status="unresolved",
                proposal_fingerprint=fp,
                final_boundary_left_ids=list(consolidated),
                final_scene_ranges=[],
                source_summary=source_summary,
                unresolved_reason="存在空场景或倒序边界",
                paragraph_count=len(paragraphs),
                scene_count=0,
            )

    scene_payload = [
        {
            "ordinal": index,
            "start_paragraph_id": start.id,
            "end_paragraph_id": end.id,
            "start_paragraph_index": start.paragraph_index,
            "end_paragraph_index": end.paragraph_index,
            "paragraph_ids": [
                p.id
                for p in paragraphs
                if start.paragraph_index <= p.paragraph_index <= end.paragraph_index
            ],
        }
        for index, (start, end) in enumerate(ranges, start=1)
    ]
    fp = _fingerprint(review.id, consolidated, "valid")
    return FinalBoundaryProposal(
        review_id=review.id,
        analysis_run_id=review.analysis_run_id,
        chapter_id=review.chapter_id,
        validation_status="valid",
        proposal_fingerprint=fp,
        final_boundary_left_ids=list(consolidated),
        final_scene_ranges=scene_payload,
        source_summary=source_summary,
        unresolved_reason=None,
        paragraph_count=len(paragraphs),
        scene_count=len(scene_payload),
        selected_transition_ids=[
            selected_by_left[left].transition_id
            for left in consolidated
            if left in selected_by_left
        ],
    )


def apply_final_proposal_decisions(
    session: Session,
    review: BoundaryReviewSession,
    proposal: FinalBoundaryProposal,
) -> None:
    """Map proposal onto decision rows; pending no longer blocks confirm."""
    selected = set(proposal.final_boundary_left_ids)
    decisions = list(
        session.scalars(
            select(BoundaryReviewDecision).where(
                BoundaryReviewDecision.review_session_id == review.id
            )
        )
    )
    for item in decisions:
        if item.left_paragraph_id in selected:
            if item.user_decision not in {"accept", "manually_added"}:
                item.user_decision = "accept"
            item.final_boundary = True
        else:
            if item.user_decision == "manually_added":
                item.user_decision = "reject"
            elif item.user_decision != "reject":
                item.user_decision = "reject"
            item.final_boundary = False
    session.flush()
