"""Semantic-review checkpoints and offline recovery for v3.5 detection batches."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisRun,
    BoundaryDetectionBatchCheckpoint,
    Chapter,
    ModelInvocation,
    Paragraph,
)
from app.schemas.scene import (
    CandidateReviewIssue,
    CandidateReviewValidationResult,
    CompactTransitionCandidateDecision,
    CompactTransitionClassificationResultV35,
)
from app.services.scene_boundary_adjudicator import (
    validate_candidate_detection_for_review,
    validate_candidate_detection_structure,
)
from app.services.scene_transitions import AdjacentTransition, build_adjacent_transitions
from app.services.transition_batch_planner import TransitionBatch, plan_transition_batches


COMPLETED_CHECKPOINT_STATUSES = {"completed", "conflicted_completed"}
STRUCTURAL_REPAIR_KINDS = {
    "json_repair",
    "schema_repair",
    "truncation_retry",
    "business_repair",
    "evidence_repair",
    "structural_repair",
}


class PlannedDetectionBatch(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    batch_index: int
    window_index: int
    batch: TransitionBatch
    transitions: list[AdjacentTransition]


class BoundaryRecoveryReport(BaseModel):
    source_run_id: int
    total_detection_batch_count: int
    recovered_batch_count: int
    conflicted_batch_count: int
    semantic_conflict_count: int
    remaining_batch_indices: list[int] = Field(default_factory=list)
    recovered: list[dict[str, object]] = Field(default_factory=list)
    failed_structural: list[dict[str, object]] = Field(default_factory=list)


def planned_detection_batches(
    session: Session, run: AnalysisRun
) -> list[PlannedDetectionBatch]:
    chapter = session.get(Chapter, int(run.subject_id))
    if chapter is None:
        raise ValueError("chapter not found for checkpoint planning")
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter.id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    from app.services.scene_pipeline import build_windows

    planned: list[PlannedDetectionBatch] = []
    batch_index = 1
    for window_index, window in enumerate(build_windows(paragraphs), 1):
        transitions = build_adjacent_transitions([item.id for item in window])
        for batch in plan_transition_batches(transitions, contract_version="3.5"):
            planned.append(
                PlannedDetectionBatch(
                    batch_index=batch_index,
                    window_index=window_index,
                    batch=batch,
                    transitions=transitions,
                )
            )
            batch_index += 1
    return planned


def _transition_map(
    transitions: list[AdjacentTransition], owned_transition_ids: tuple[str, ...]
) -> dict[str, dict[str, str]]:
    owned = set(owned_transition_ids)
    return {
        item.transition_id: {
            "left_paragraph_id": item.left_paragraph_id,
            "right_paragraph_id": item.right_paragraph_id,
        }
        for item in transitions
        if item.transition_id in owned
    }


def upsert_detection_checkpoint(
    session: Session,
    *,
    run: AnalysisRun,
    chapter_id: int,
    planned: PlannedDetectionBatch,
    invocation_id: int | None,
    validation: CandidateReviewValidationResult | None,
    status: str,
    source_run_id: int | None = None,
) -> BoundaryDetectionBatchCheckpoint:
    checkpoint = session.scalar(
        select(BoundaryDetectionBatchCheckpoint).where(
            BoundaryDetectionBatchCheckpoint.run_id == run.id,
            BoundaryDetectionBatchCheckpoint.batch_index == planned.batch_index,
            BoundaryDetectionBatchCheckpoint.prompt_version == run.prompt_version,
        )
    )
    if checkpoint is None:
        checkpoint = BoundaryDetectionBatchCheckpoint(
            run_id=run.id,
            chapter_id=chapter_id,
            batch_index=planned.batch_index,
            window_index=planned.window_index,
            prompt_version=run.prompt_version,
            contract_version="3.5",
            status=status,
        )
        session.add(checkpoint)
    checkpoint.invocation_id = invocation_id
    checkpoint.source_run_id = source_run_id
    checkpoint.owned_transition_ids_json = json.dumps(
        list(planned.batch.owned_transition_ids), ensure_ascii=False
    )
    checkpoint.context_paragraph_ids_json = json.dumps(
        list(planned.batch.context_paragraph_ids), ensure_ascii=False
    )
    checkpoint.transition_map_json = json.dumps(
        _transition_map(planned.transitions, planned.batch.owned_transition_ids),
        ensure_ascii=False,
        sort_keys=True,
    )
    checkpoint.valid_decisions_json = (
        json.dumps(
            [item.model_dump(mode="json") for item in validation.valid_decisions],
            ensure_ascii=False,
        )
        if validation
        else "[]"
    )
    checkpoint.conflicted_decisions_json = (
        json.dumps(
            [item.model_dump(mode="json") for item in validation.conflicted_decisions],
            ensure_ascii=False,
        )
        if validation
        else "[]"
    )
    checkpoint.issues_json = (
        json.dumps(
            [item.model_dump(mode="json") for item in validation.issues],
            ensure_ascii=False,
        )
        if validation
        else "[]"
    )
    checkpoint.status = status
    checkpoint.completed_at = (
        datetime.now(timezone.utc) if status in COMPLETED_CHECKPOINT_STATUSES else None
    )
    if validation is not None:
        canonical = json.dumps(
            {
                "valid": json.loads(checkpoint.valid_decisions_json),
                "conflicted": json.loads(checkpoint.conflicted_decisions_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        checkpoint.parsed_response_hash = hashlib.sha256(canonical.encode()).hexdigest()
    session.commit()
    session.refresh(checkpoint)
    return checkpoint


def checkpoint_validation(
    checkpoint: BoundaryDetectionBatchCheckpoint,
) -> CandidateReviewValidationResult:
    return CandidateReviewValidationResult(
        valid_decisions=[
            CompactTransitionCandidateDecision.model_validate(item)
            for item in json.loads(checkpoint.valid_decisions_json or "[]")
        ],
        conflicted_decisions=[
            CompactTransitionCandidateDecision.model_validate(item)
            for item in json.loads(checkpoint.conflicted_decisions_json or "[]")
        ],
        issues=[
            CandidateReviewIssue.model_validate(item)
            for item in json.loads(checkpoint.issues_json or "[]")
        ],
    )


def ordered_checkpoint_decisions(
    checkpoint: BoundaryDetectionBatchCheckpoint,
) -> list[CompactTransitionCandidateDecision]:
    validation = checkpoint_validation(checkpoint)
    by_id = {
        item.transition_id: item
        for item in validation.valid_decisions + validation.conflicted_decisions
    }
    expected = json.loads(checkpoint.owned_transition_ids_json or "[]")
    return [by_id[item] for item in expected if item in by_id]


def completed_checkpoint(
    session: Session, run_id: int, batch_index: int, prompt_version: str
) -> BoundaryDetectionBatchCheckpoint | None:
    return session.scalar(
        select(BoundaryDetectionBatchCheckpoint).where(
            BoundaryDetectionBatchCheckpoint.run_id == run_id,
            BoundaryDetectionBatchCheckpoint.batch_index == batch_index,
            BoundaryDetectionBatchCheckpoint.prompt_version == prompt_version,
            BoundaryDetectionBatchCheckpoint.status.in_(COMPLETED_CHECKPOINT_STATUSES),
        )
    )


def _detection_attempt_groups(
    invocations: list[ModelInvocation],
) -> list[list[ModelInvocation]]:
    groups: list[list[ModelInvocation]] = []
    current: list[ModelInvocation] | None = None
    for invocation in invocations:
        if invocation.invocation_kind == "boundary_candidate_detection":
            current = [invocation]
            groups.append(current)
        elif current is not None and invocation.invocation_kind in STRUCTURAL_REPAIR_KINDS:
            current.append(invocation)
        elif invocation.invocation_kind == "boundary_candidate_adjudication":
            current = None
    return groups


def recover_boundary_detection_from_invocations(
    session: Session, run_id: int, *, persist: bool = True
) -> BoundaryRecoveryReport:
    """Recover v3.5 checkpoints without calling a Provider or rewriting invocations."""
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise ValueError("analysis run not found")
    if run.prompt_version != "v3.5":
        raise ValueError("only v3.5 detection runs can be recovered")
    chapter = session.get(Chapter, int(run.subject_id))
    if chapter is None:
        raise ValueError("chapter not found")
    planned = planned_detection_batches(session, run)
    invocations = list(
        session.scalars(
            select(ModelInvocation)
            .where(ModelInvocation.run_id == run.id)
            .order_by(ModelInvocation.id)
        )
    )
    groups = _detection_attempt_groups(invocations)
    existing = list(
        session.scalars(
            select(BoundaryDetectionBatchCheckpoint)
            .where(
                BoundaryDetectionBatchCheckpoint.run_id == run.id,
                BoundaryDetectionBatchCheckpoint.status.in_(
                    COMPLETED_CHECKPOINT_STATUSES
                ),
            )
            .order_by(BoundaryDetectionBatchCheckpoint.batch_index)
        )
    )
    existing_by_index = {item.batch_index: item for item in existing}
    linked_invocation_ids = {
        item.invocation_id for item in existing if item.invocation_id is not None
    }
    if linked_invocation_ids:
        groups = [
            group
            for group in groups
            if not any(item.id in linked_invocation_ids for item in group)
        ]
    pending_plans = [
        item for item in planned if item.batch_index not in existing_by_index
    ]
    report = BoundaryRecoveryReport(
        source_run_id=run.id,
        total_detection_batch_count=len(planned),
        recovered_batch_count=len(existing),
        conflicted_batch_count=sum(
            item.status == "conflicted_completed" for item in existing
        ),
        semantic_conflict_count=sum(
            len(json.loads(item.issues_json or "[]")) for item in existing
        ),
    )
    recovered_indices: set[int] = set(existing_by_index)
    for item in existing:
        issues = json.loads(item.issues_json or "[]")
        report.recovered.append(
            {
                "batch_index": item.batch_index,
                "invocation_id": item.invocation_id,
                "status": item.status,
                "conflict_transition_ids": [
                    issue["transition_id"] for issue in issues
                ],
                "issues": issues,
            }
        )
    for index, plan in enumerate(pending_plans):
        if index >= len(groups):
            continue
        chosen: tuple[ModelInvocation, CandidateReviewValidationResult] | None = None
        for invocation in reversed(groups[index]):
            if not invocation.parsed_response_json:
                continue
            try:
                parsed = CompactTransitionClassificationResultV35.model_validate_json(
                    invocation.parsed_response_json
                )
                validate_candidate_detection_structure(
                    parsed.decisions, list(plan.batch.owned_transition_ids)
                )
                validation = validate_candidate_detection_for_review(
                    parsed.decisions, list(plan.batch.owned_transition_ids)
                )
            except (ValidationError, ValueError, json.JSONDecodeError):
                continue
            chosen = invocation, validation
            break
        if chosen is None:
            report.failed_structural.append(
                {"batch_index": plan.batch_index, "attempt_count": len(groups[index])}
            )
            continue
        invocation, validation = chosen
        status = "conflicted_completed" if validation.issues else "completed"
        if persist:
            upsert_detection_checkpoint(
                session,
                run=run,
                chapter_id=chapter.id,
                planned=plan,
                invocation_id=invocation.id,
                validation=validation,
                status=status,
                source_run_id=run.id,
            )
        recovered_indices.add(plan.batch_index)
        report.recovered_batch_count += 1
        report.conflicted_batch_count += int(bool(validation.issues))
        report.semantic_conflict_count += len(validation.issues)
        report.recovered.append(
            {
                "batch_index": plan.batch_index,
                "invocation_id": invocation.id,
                "status": status,
                "conflict_transition_ids": [
                    item.transition_id for item in validation.issues
                ],
                "issues": [
                    item.model_dump(mode="json") for item in validation.issues
                ],
            }
        )
    report.remaining_batch_indices = [
        item.batch_index for item in planned if item.batch_index not in recovered_indices
    ]
    return report


def clone_recovered_checkpoints(
    session: Session, source_run_id: int, target_run: AnalysisRun
) -> int:
    source = list(
        session.scalars(
            select(BoundaryDetectionBatchCheckpoint)
            .where(
                BoundaryDetectionBatchCheckpoint.run_id == source_run_id,
                BoundaryDetectionBatchCheckpoint.status.in_(COMPLETED_CHECKPOINT_STATUSES),
            )
            .order_by(BoundaryDetectionBatchCheckpoint.batch_index)
        )
    )
    copied = 0
    for item in source:
        existing = completed_checkpoint(
            session, target_run.id, item.batch_index, target_run.prompt_version
        )
        if existing is not None:
            continue
        session.add(
            BoundaryDetectionBatchCheckpoint(
                run_id=target_run.id,
                chapter_id=item.chapter_id,
                batch_index=item.batch_index,
                window_index=item.window_index,
                prompt_version=target_run.prompt_version,
                contract_version=item.contract_version,
                owned_transition_ids_json=item.owned_transition_ids_json,
                context_paragraph_ids_json=item.context_paragraph_ids_json,
                transition_map_json=item.transition_map_json,
                invocation_id=item.invocation_id,
                source_run_id=source_run_id,
                parsed_response_hash=item.parsed_response_hash,
                valid_decisions_json=item.valid_decisions_json,
                conflicted_decisions_json=item.conflicted_decisions_json,
                issues_json=item.issues_json,
                status=item.status,
                completed_at=item.completed_at,
            )
        )
        copied += 1
    session.commit()
    return copied
