"""Output-bounded adjudication batching helpers (v1.1.2).

Splits target candidates into fixed-size contiguous batches with optional
context-only neighbor candidates. Does not change detection batching.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.schemas.scene import (
    BoundaryCandidateAdjudicationResult,
    BoundaryCandidateVerdict,
    CompactTransitionCandidateDecision,
)
from app.services.scene_transitions import AdjacentTransition
from app.services.transition_batch_planner import conservative_token_estimate
from app.services.validation_errors import StructuralValidationError

MAX_TARGET_CANDIDATES_PER_BATCH = 10
MAX_ADJUDICATION_INPUT_TOKENS = 12_000
ADJUDICATION_PROMPT_VERSION = "v1.1.2"
ADJUDICATION_SCHEMA_VERSION = "v1"

ERROR_BATCH_COVERAGE_INVALID = "SCENE_BOUNDARY_BATCH_COVERAGE_INVALID"
ERROR_BATCH_SCHEMA_INVALID = "SCENE_BOUNDARY_BATCH_SCHEMA_INVALID"
ERROR_OUTPUT_TRUNCATED = "SCENE_BOUNDARY_OUTPUT_TRUNCATED"
ERROR_OUTPUT_TRUNCATED_AT_HARD_CAP = "SCENE_BOUNDARY_OUTPUT_TRUNCATED_AT_HARD_CAP"
ERROR_OUTPUT_BUDGET_TOO_LOW = "SCENE_BOUNDARY_OUTPUT_BUDGET_TOO_LOW"
ERROR_BATCH_CHECKPOINT_INVALID = "SCENE_BOUNDARY_BATCH_CHECKPOINT_INVALID"


@dataclass(frozen=True)
class AdjudicationOutputBatch:
    batch_index: int
    target_candidate_ids: tuple[str, ...]
    context_only_candidate_ids: tuple[str, ...]
    context_paragraph_ids: tuple[str, ...]
    input_token_estimate: int
    batch_key: str
    content_key: str
    candidate_content_hash: str


def _build_one_batch(
    *,
    batch_index: int,
    all_ids: list[str],
    start: int,
    targets: list[str],
    by_id: dict[str, AdjacentTransition],
    all_candidates: list[AdjacentTransition],
    paragraph_text: dict[str, str],
    run_id: int | None,
    prompt_version: str,
    schema_version: str,
    max_input_tokens: int,
) -> AdjudicationOutputBatch:
    context_only: list[str] = []
    if start > 0:
        context_only.append(all_ids[start - 1])
    end = start + len(targets)
    if end < len(all_ids):
        context_only.append(all_ids[end])
    paragraph_ids = _paragraph_context_for_targets(
        targets, context_only, by_id, all_candidates
    )
    payload = {
        "target_candidate_ids": targets,
        "context_only_candidate_ids": context_only,
        "paragraphs": [
            {"id": pid, "text": paragraph_text.get(pid, "")} for pid in paragraph_ids
        ],
    }
    estimate = conservative_token_estimate(payload)
    if estimate > max_input_tokens:
        raise ValueError("one adjudication candidate exceeds the input token budget")
    content_hash = _candidate_content_hash(targets, paragraph_text, by_id)
    ckey = compute_content_batch_key(
        batch_index=batch_index,
        target_candidate_ids=targets,
        candidate_content_hash=content_hash,
        prompt_version=prompt_version,
        schema_version=schema_version,
    )
    bkey = compute_batch_key(
        run_id=run_id,
        batch_index=batch_index,
        target_candidate_ids=targets,
        candidate_content_hash=content_hash,
        prompt_version=prompt_version,
        schema_version=schema_version,
    )
    return AdjudicationOutputBatch(
        batch_index=batch_index,
        target_candidate_ids=tuple(targets),
        context_only_candidate_ids=tuple(context_only),
        context_paragraph_ids=tuple(paragraph_ids),
        input_token_estimate=estimate,
        batch_key=bkey,
        content_key=ckey,
        candidate_content_hash=content_hash,
    )


def plan_output_bounded_adjudication_batches(
    candidate_ids: list[str],
    all_candidates: list[AdjacentTransition],
    paragraph_text: dict[str, str],
    *,
    max_target_per_batch: int = MAX_TARGET_CANDIDATES_PER_BATCH,
    max_input_tokens: int = MAX_ADJUDICATION_INPUT_TOKENS,
    run_id: int | None = None,
    prompt_version: str = ADJUDICATION_PROMPT_VERSION,
    schema_version: str = ADJUDICATION_SCHEMA_VERSION,
) -> list[AdjudicationOutputBatch]:
    """Split targets into contiguous batches of at most max_target_per_batch."""
    if not candidate_ids:
        return []
    if max_target_per_batch < 1:
        raise ValueError("max_target_per_batch must be >= 1")
    by_id = {item.transition_id: item for item in all_candidates}
    for tid in candidate_ids:
        if tid not in by_id:
            raise ValueError("invalid adjudication candidate")

    chunks: list[tuple[int, list[str]]] = []
    for start in range(0, len(candidate_ids), max_target_per_batch):
        chunks.append((start, candidate_ids[start : start + max_target_per_batch]))

    # If any chunk exceeds input budget, bisect contiguous targets until it fits.
    refined: list[tuple[int, list[str]]] = []
    for start, targets in chunks:
        stack = [(start, targets)]
        while stack:
            s, t = stack.pop(0)
            try:
                _build_one_batch(
                    batch_index=0,
                    all_ids=candidate_ids,
                    start=s,
                    targets=t,
                    by_id=by_id,
                    all_candidates=all_candidates,
                    paragraph_text=paragraph_text,
                    run_id=run_id,
                    prompt_version=prompt_version,
                    schema_version=schema_version,
                    max_input_tokens=max_input_tokens,
                )
                refined.append((s, t))
            except ValueError:
                if len(t) <= 1:
                    raise
                mid = max(1, len(t) // 2)
                stack.insert(0, (s + mid, t[mid:]))
                stack.insert(0, (s, t[:mid]))

    return [
        _build_one_batch(
            batch_index=i,
            all_ids=candidate_ids,
            start=start,
            targets=targets,
            by_id=by_id,
            all_candidates=all_candidates,
            paragraph_text=paragraph_text,
            run_id=run_id,
            prompt_version=prompt_version,
            schema_version=schema_version,
            max_input_tokens=max_input_tokens,
        )
        for i, (start, targets) in enumerate(refined)
    ]


def _paragraph_context_for_targets(
    targets: list[str],
    context_only: list[str],
    by_id: dict[str, AdjacentTransition],
    all_candidates: list[AdjacentTransition],
) -> list[str]:
    ids: list[str] = []
    for tid in list(dict.fromkeys([*context_only, *targets])):
        candidate = by_id[tid]
        index = all_candidates.index(candidate)
        start = max(0, index - 3)
        end = min(len(all_candidates), index + 4)
        ids.append(all_candidates[start].left_paragraph_id)
        ids.extend(item.right_paragraph_id for item in all_candidates[start:end])
    return list(dict.fromkeys(ids))


def _candidate_content_hash(
    target_ids: list[str],
    paragraph_text: dict[str, str],
    by_id: dict[str, AdjacentTransition],
) -> str:
    parts: list[str] = []
    for tid in target_ids:
        t = by_id[tid]
        left = paragraph_text.get(t.left_paragraph_id, "")
        right = paragraph_text.get(t.right_paragraph_id, "")
        parts.append(f"{tid}|{t.left_paragraph_id}|{t.right_paragraph_id}|{left}|{right}")
    blob = "\n".join(parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def compute_content_batch_key(
    *,
    batch_index: int,
    target_candidate_ids: list[str],
    candidate_content_hash: str,
    prompt_version: str,
    schema_version: str,
    stage: str = "scene_boundary_adjudication",
) -> str:
    payload = {
        "stage": stage,
        "batch_index": batch_index,
        "target_candidate_ids": list(target_candidate_ids),
        "candidate_content_hash": candidate_content_hash,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compute_batch_key(
    *,
    run_id: int | None,
    batch_index: int,
    target_candidate_ids: list[str],
    candidate_content_hash: str,
    prompt_version: str,
    schema_version: str,
    stage: str = "scene_boundary_adjudication",
) -> str:
    payload = {
        "task_id": run_id,
        "stage": stage,
        "batch_index": batch_index,
        "target_candidate_ids": list(target_candidate_ids),
        "candidate_content_hash": candidate_content_hash,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_batch_coverage(
    value: BoundaryCandidateAdjudicationResult,
    *,
    target_candidate_ids: list[str],
    context_only_candidate_ids: list[str] | None = None,
    known_candidate_ids: set[str] | None = None,
) -> None:
    """Validate batch verdict coverage; raises StructuralValidationError on failure."""
    context_only = set(context_only_candidate_ids or [])
    known = known_candidate_ids or set(target_candidate_ids) | context_only
    ids = [item.transition_id for item in value.verdicts]
    if len(ids) != len(set(ids)):
        raise StructuralValidationError(
            "adjudication batch has duplicate candidate ids",
            error_code=ERROR_BATCH_COVERAGE_INVALID,
        )
    if ids != list(target_candidate_ids):
        raise StructuralValidationError(
            "adjudication batch must cover target candidates exactly once in order",
            error_code=ERROR_BATCH_COVERAGE_INVALID,
        )
    for tid in ids:
        if tid in context_only:
            raise StructuralValidationError(
                "context-only candidate leaked into batch verdicts",
                error_code=ERROR_BATCH_COVERAGE_INVALID,
            )
        if tid not in known:
            raise StructuralValidationError(
                "unknown candidate id in adjudication batch",
                error_code=ERROR_BATCH_COVERAGE_INVALID,
            )
    for verdict in value.verdicts:
        legal_accept = (
            verdict.scope_relation == "primary_scene_change"
            and verdict.continuity_relation == "new_scene_chain"
        )
        if verdict.accept != legal_accept:
            raise StructuralValidationError(
                "adjudication verdict conflicts with deterministic rules",
                error_code=ERROR_BATCH_SCHEMA_INVALID,
            )


def merge_adjudication_batches(
    *,
    original_candidate_order: list[str],
    batch_results: list[tuple[list[str], BoundaryCandidateAdjudicationResult]],
) -> BoundaryCandidateAdjudicationResult:
    """Merge validated batch results in original candidate order."""
    by_id: dict[str, BoundaryCandidateVerdict] = {}
    for target_ids, result in batch_results:
        validate_batch_coverage(result, target_candidate_ids=target_ids)
        for verdict in result.verdicts:
            if verdict.transition_id in by_id:
                raise StructuralValidationError(
                    "duplicate candidate across adjudication batches",
                    error_code=ERROR_BATCH_COVERAGE_INVALID,
                )
            by_id[verdict.transition_id] = verdict
    missing = [tid for tid in original_candidate_order if tid not in by_id]
    if missing:
        raise StructuralValidationError(
            "incomplete adjudication merge; missing candidates",
            error_code=ERROR_BATCH_COVERAGE_INVALID,
        )
    extra = [tid for tid in by_id if tid not in set(original_candidate_order)]
    if extra:
        raise StructuralValidationError(
            "adjudication merge contains unknown candidates",
            error_code=ERROR_BATCH_COVERAGE_INVALID,
        )
    return BoundaryCandidateAdjudicationResult(
        contract_version="1.0",
        verdicts=[by_id[tid] for tid in original_candidate_order],
    )


def adjudication_snapshot_v112(
    *,
    chapter_id: str,
    title: str,
    batch: AdjudicationOutputBatch,
    candidates: list[AdjacentTransition],
    decisions: list[CompactTransitionCandidateDecision],
    paragraph_text: dict[str, str],
) -> dict[str, object]:
    by_id = {item.transition_id: item for item in candidates}
    decision_by_id = {item.transition_id: item for item in decisions}

    def enrich(tid: str, role: str) -> dict[str, object]:
        return {
            **by_id[tid].as_dict(),
            "transition_ordinal": candidates.index(by_id[tid]) + 1,
            "first_pass": decision_by_id[tid].model_dump(),
            "candidate_role": role,
        }

    return {
        "chapter_id": chapter_id,
        "chapter_title": title,
        "contract_version": "1.1.2",
        "total_transition_count": len(candidates),
        "batch_index": batch.batch_index,
        "batch_key": batch.batch_key,
        "target_candidate_ids": list(batch.target_candidate_ids),
        "context_only_candidate_ids": list(batch.context_only_candidate_ids),
        "target_candidates": [
            enrich(tid, "target") for tid in batch.target_candidate_ids
        ],
        "context_only_candidates": [
            enrich(tid, "context_only") for tid in batch.context_only_candidate_ids
        ],
        # Back-compat keys for validators that still read candidate_transition_ids
        "candidate_transition_ids": list(batch.target_candidate_ids),
        "candidates": [enrich(tid, "target") for tid in batch.target_candidate_ids],
        "paragraphs": [
            {"id": item, "text": paragraph_text[item]}
            for item in batch.context_paragraph_ids
            if item in paragraph_text
        ],
    }
