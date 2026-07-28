"""Persist validated adjudication batch results without schema migration.

Uses existing AnalysisArtifact rows (artifact_type=boundary_adjudication_batch).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisArtifact, AnalysisRun
from app.schemas.scene import BoundaryCandidateAdjudicationResult
from app.services.scene_boundary_adjudication_batching import (
    ERROR_BATCH_CHECKPOINT_INVALID,
)
from app.services.validation_errors import StructuralValidationError

ARTIFACT_TYPE = "boundary_adjudication_batch"
PLAN_ARTIFACT_TYPE = "boundary_adjudication_plan"


def _output_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def save_adjudication_batch_checkpoint(
    session: Session,
    *,
    run: AnalysisRun,
    batch_key: str,
    content_key: str,
    batch_index: int,
    target_candidate_ids: list[str],
    result: BoundaryCandidateAdjudicationResult,
    usage_summary: dict[str, Any] | None = None,
    prompt_version: str,
) -> AnalysisArtifact:
    verdicts = [item.model_dump(mode="json") for item in result.verdicts]
    payload = {
        "batch_key": batch_key,
        "content_key": content_key,
        "batch_index": batch_index,
        "target_candidate_ids": list(target_candidate_ids),
        "status": "completed",
        "verdicts": verdicts,
        "output_hash": _output_hash({"verdicts": verdicts}),
        "usage_summary": usage_summary or {},
    }
    existing = session.scalar(
        select(AnalysisArtifact).where(
            AnalysisArtifact.run_id == run.id,
            AnalysisArtifact.artifact_type == ARTIFACT_TYPE,
            AnalysisArtifact.subject_id == batch_key,
        )
    )
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if existing is not None:
        existing.payload_json = body
        existing.validation_status = "valid"
        existing.prompt_version = prompt_version
        session.flush()
        return existing
    row = AnalysisArtifact(
        run_id=run.id,
        artifact_type=ARTIFACT_TYPE,
        subject_type="adjudication_batch",
        subject_id=batch_key,
        schema_version="v1",
        prompt_version=prompt_version,
        payload_json=body,
        confidence=1.0,
        validation_status="valid",
    )
    session.add(row)
    session.flush()
    return row


def save_adjudication_plan(
    session: Session,
    *,
    run: AnalysisRun,
    candidate_ids: list[str],
    batch_total: int,
    prompt_version: str,
) -> AnalysisArtifact:
    """Persist planned candidate/batch totals for progress API (no migration)."""
    payload = {
        "status": "planned",
        "boundary_candidate_total": len(candidate_ids),
        "boundary_batch_total": int(batch_total),
        "target_candidate_ids": list(candidate_ids),
    }
    existing = session.scalar(
        select(AnalysisArtifact).where(
            AnalysisArtifact.run_id == run.id,
            AnalysisArtifact.artifact_type == PLAN_ARTIFACT_TYPE,
            AnalysisArtifact.subject_id == "plan",
        )
    )
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if existing is not None:
        existing.payload_json = body
        existing.validation_status = "valid"
        existing.prompt_version = prompt_version
        session.flush()
        return existing
    row = AnalysisArtifact(
        run_id=run.id,
        artifact_type=PLAN_ARTIFACT_TYPE,
        subject_type="adjudication_plan",
        subject_id="plan",
        schema_version="v1",
        prompt_version=prompt_version,
        payload_json=body,
        confidence=1.0,
        validation_status="valid",
    )
    session.add(row)
    session.flush()
    return row


def load_adjudication_plan(
    session: Session,
    *,
    run_id: int,
) -> dict[str, Any] | None:
    row = session.scalar(
        select(AnalysisArtifact).where(
            AnalysisArtifact.run_id == run_id,
            AnalysisArtifact.artifact_type == PLAN_ARTIFACT_TYPE,
            AnalysisArtifact.subject_id == "plan",
        )
    )
    if row is None:
        return None
    try:
        return json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        return None


def load_completed_adjudication_batches(
    session: Session,
    *,
    run_id: int,
) -> dict[str, dict[str, Any]]:
    """Map content_key -> validated payload for completed batches on a run."""
    rows = session.scalars(
        select(AnalysisArtifact).where(
            AnalysisArtifact.run_id == run_id,
            AnalysisArtifact.artifact_type == ARTIFACT_TYPE,
            AnalysisArtifact.validation_status == "valid",
        )
    ).all()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            payload = json.loads(row.payload_json)
        except json.JSONDecodeError as exc:
            raise StructuralValidationError(
                "adjudication batch checkpoint is corrupt",
                error_code=ERROR_BATCH_CHECKPOINT_INVALID,
            ) from exc
        if payload.get("status") != "completed":
            continue
        key = str(payload.get("content_key") or "")
        if not key:
            continue
        # Never expose raw provider bodies — payload only stores validated verdicts.
        if "raw_response" in payload or "prompt" in payload:
            raise StructuralValidationError(
                "adjudication batch checkpoint contains forbidden raw fields",
                error_code=ERROR_BATCH_CHECKPOINT_INVALID,
            )
        out[key] = payload
    return out


def load_reusable_adjudication_batches(
    session: Session,
    *,
    run: AnalysisRun,
) -> dict[str, dict[str, Any]]:
    """Load completed batches from this run and recovered_from_run_id source."""
    merged = load_completed_adjudication_batches(session, run_id=run.id)
    source_id = run.recovered_from_run_id or run.retry_of_run_id
    if source_id:
        for key, payload in load_completed_adjudication_batches(
            session, run_id=int(source_id)
        ).items():
            merged.setdefault(key, payload)
    return merged


def adjudication_progress_from_artifacts(
    *,
    planned_batches: list[Any],
    completed_by_content_key: dict[str, dict[str, Any]],
    candidate_total: int,
) -> dict[str, int]:
    completed = 0
    completed_candidates = 0
    for batch in planned_batches:
        content_key = getattr(batch, "content_key", None)
        if content_key is None:
            # Derive from stored batch fields when content_key not on dataclass
            content_key = None
        key = content_key
        if key is None:
            # Match by batch_index + targets in completed payloads
            targets = list(getattr(batch, "target_candidate_ids", ()))
            matched = next(
                (
                    p
                    for p in completed_by_content_key.values()
                    if p.get("batch_index") == getattr(batch, "batch_index", -1)
                    and p.get("target_candidate_ids") == targets
                ),
                None,
            )
        else:
            matched = completed_by_content_key.get(key)
        if matched:
            completed += 1
            completed_candidates += len(matched.get("target_candidate_ids") or [])
    return {
        "boundary_candidate_total": int(candidate_total),
        "boundary_candidate_completed": int(completed_candidates),
        "boundary_batch_total": len(planned_batches),
        "boundary_batch_completed": int(completed),
    }
