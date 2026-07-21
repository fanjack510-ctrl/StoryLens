"""Phase 1C-A.4 staged cloud budget estimates (no provider calls)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Paragraph, Scene
from app.services.cloud_pricing import estimate_cost, pricing_status
from app.services.scene_boundary_adjudicator import plan_adjudication_batches
from app.services.scene_transitions import build_adjacent_transitions
from app.services.transition_batch_planner import (
    conservative_token_estimate,
    plan_transition_batches,
)

STAGE_BOUNDARY = "boundary_review_generation"
STAGE_ANALYSIS = "scene_analysis"
STAGE_READER_JOURNEY_SCENE = "reader_journey_scene_profiles"
STAGE_READER_JOURNEY_CHAPTER = "reader_journey_chapter_synthesis"


@dataclass(frozen=True)
class BudgetAmounts:
    requests: int
    tokens: int
    estimated_cost: float


@dataclass(frozen=True)
class StageEstimate:
    stage: str
    paragraph_count: int
    transition_count: int
    detection_batch_count: int
    adjudication_batch_count_estimated: int
    scene_count: int
    expected_request_count: int
    worst_case_request_count: int
    estimated_input_tokens: int
    worst_case_input_tokens: int
    estimated_output_tokens: int
    worst_case_output_tokens: int
    estimated_total_tokens: int
    worst_case_total_tokens: int
    estimated_cost: float
    worst_case_cost: float
    currency: str
    pricing_version: str | None
    estimated: bool = True

    @property
    def required(self) -> BudgetAmounts:
        """Hard-gate amounts: normal-path estimated usage (not worst-case)."""
        return BudgetAmounts(
            self.expected_request_count,
            self.estimated_total_tokens,
            self.estimated_cost,
        )

    @property
    def worst_case(self) -> BudgetAmounts:
        """Risk / advisory envelope only - never the default start gate."""
        return BudgetAmounts(
            self.worst_case_request_count,
            self.worst_case_total_tokens,
            self.worst_case_cost,
        )

    @property
    def retry_reserve(self) -> BudgetAmounts:
        """Spare headroom for retry / repair; advisory only, not a hard gate."""
        return BudgetAmounts(
            max(0, self.worst_case_request_count - self.expected_request_count),
            max(0, self.worst_case_total_tokens - self.estimated_total_tokens),
            round(max(0.0, self.worst_case_cost - self.estimated_cost), 6),
        )


def exceeded_dimensions(required: BudgetAmounts, remaining: BudgetAmounts) -> list[str]:
    dims: list[str] = []
    if required.requests > remaining.requests:
        dims.append("requests")
    if required.tokens > remaining.tokens:
        dims.append("tokens")
    if required.estimated_cost > remaining.estimated_cost:
        dims.append("estimated_cost")
    return dims


def _plus_model_name() -> str:
    return get_settings().aliyun_plus_model


def _cost(input_tokens: int, output_tokens: int, pricing_path: Path) -> float:
    cost, _, _ = estimate_cost(_plus_model_name(), input_tokens, output_tokens, pricing_path)
    return round(float(cost or 0.0), 6)


def estimate_stage1_boundary(
    paragraphs: list[Paragraph],
    *,
    pricing_path: Path = Path("config/cloud_pricing.json"),
) -> StageEstimate:
    """Estimate Stage 1 only: detection + adjudication. Never includes Scene Analysis."""
    settings = get_settings()
    pricing = pricing_status(pricing_path)
    paragraph_count = len(paragraphs)
    if paragraph_count < 2:
        currency = str(pricing.get("currency") or "CNY")
        return StageEstimate(
            stage=STAGE_BOUNDARY,
            paragraph_count=paragraph_count,
            transition_count=0,
            detection_batch_count=0,
            adjudication_batch_count_estimated=0,
            scene_count=0,
            expected_request_count=0,
            worst_case_request_count=0,
            estimated_input_tokens=0,
            worst_case_input_tokens=0,
            estimated_output_tokens=0,
            worst_case_output_tokens=0,
            estimated_total_tokens=0,
            worst_case_total_tokens=0,
            estimated_cost=0.0,
            worst_case_cost=0.0,
            currency=currency,
            pricing_version=pricing.get("pricing_version")  # type: ignore[arg-type]
            if isinstance(pricing.get("pricing_version"), str) or pricing.get("pricing_version") is None
            else str(pricing.get("pricing_version")),
        )
    transitions = build_adjacent_transitions([item.id for item in paragraphs])
    detection_batches = plan_transition_batches(transitions, contract_version="3.5")
    paragraph_text = {item.id: item.normalized_text for item in paragraphs}
    # Worst-case adjudication: every transition is a candidate.
    adjudication_batches = plan_adjudication_batches(
        [item.transition_id for item in transitions], transitions, paragraph_text
    )
    detection_output = settings.cloud_output_scene_boundary
    adjudication_output = settings.cloud_output_scene_boundary
    repair_output = max(
        settings.cloud_output_json_schema_repair,
        settings.cloud_output_business_repair,
    )

    det_input_est = 0
    det_input_worst = 0
    for batch in detection_batches:
        context_ids = list(batch.context_paragraph_ids)
        payload = {
            "paragraphs": [
                {"id": item, "text": paragraph_text[item]} for item in context_ids
            ],
            "transitions": [
                {"transition_id": item} for item in batch.owned_transition_ids
            ],
        }
        tokens = conservative_token_estimate(payload)
        det_input_est += tokens
        det_input_worst += tokens

    adj_input_est = sum(batch.input_token_estimate for batch in adjudication_batches)
    # Expected adjudication assumes ~half of transitions become candidates.
    expected_adj_ids = [
        item.transition_id for item in transitions[: max(1, math.ceil(len(transitions) / 2))]
    ]
    expected_adj_batches = (
        plan_adjudication_batches(expected_adj_ids, transitions, paragraph_text)
        if expected_adj_ids
        else []
    )
    expected_adj_input = sum(batch.input_token_estimate for batch in expected_adj_batches)

    detection_batch_count = len(detection_batches)
    adjudication_batch_count = len(adjudication_batches)
    expected_adj_batch_count = len(expected_adj_batches)

    expected_requests = detection_batch_count + expected_adj_batch_count
    worst_requests = 2 * (detection_batch_count + adjudication_batch_count)

    estimated_output = (
        detection_batch_count * detection_output
        + expected_adj_batch_count * adjudication_output
    )
    worst_output = (
        detection_batch_count * (detection_output + repair_output)
        + adjudication_batch_count * (adjudication_output + repair_output)
    )
    estimated_input = det_input_est + expected_adj_input
    worst_input = det_input_worst + adj_input_est
    estimated_total = estimated_input + estimated_output
    worst_total = worst_input + worst_output
    estimated_cost = _cost(estimated_input, estimated_output, pricing_path)
    worst_cost = _cost(worst_input, worst_output, pricing_path)
    currency = str(pricing.get("currency") or "CNY")
    version = pricing.get("pricing_version")
    return StageEstimate(
        stage=STAGE_BOUNDARY,
        paragraph_count=paragraph_count,
        transition_count=len(transitions),
        detection_batch_count=detection_batch_count,
        adjudication_batch_count_estimated=adjudication_batch_count,
        scene_count=0,
        expected_request_count=expected_requests,
        worst_case_request_count=worst_requests,
        estimated_input_tokens=estimated_input,
        worst_case_input_tokens=worst_input,
        estimated_output_tokens=estimated_output,
        worst_case_output_tokens=worst_output,
        estimated_total_tokens=estimated_total,
        worst_case_total_tokens=worst_total,
        estimated_cost=estimated_cost,
        worst_case_cost=worst_cost,
        currency=currency,
        pricing_version=version if isinstance(version, str) else None,
    )


def estimate_stage1_boundary_remaining(
    paragraphs: list[Paragraph],
    completed_batch_indices: set[int],
    *,
    pricing_path: Path = Path("config/cloud_pricing.json"),
) -> StageEstimate:
    """Subtract completed detection batches; keep adjudication estimate conservative."""
    full = estimate_stage1_boundary(paragraphs, pricing_path=pricing_path)
    if not completed_batch_indices or full.detection_batch_count == 0:
        return full
    settings = get_settings()
    transitions = build_adjacent_transitions([item.id for item in paragraphs])
    batches = plan_transition_batches(transitions, contract_version="3.5")
    paragraph_text = {item.id: item.normalized_text for item in paragraphs}
    completed_input = 0
    completed_count = 0
    for index, batch in enumerate(batches, 1):
        if index not in completed_batch_indices:
            continue
        completed_count += 1
        completed_input += conservative_token_estimate(
            {
                "paragraphs": [
                    {"id": item, "text": paragraph_text[item]}
                    for item in batch.context_paragraph_ids
                ],
                "transitions": [
                    {"transition_id": item} for item in batch.owned_transition_ids
                ],
            }
        )
    completed_count = min(completed_count, full.detection_batch_count)
    expected_requests = max(0, full.expected_request_count - completed_count)
    worst_requests = max(0, full.worst_case_request_count - 2 * completed_count)
    estimated_input = max(0, full.estimated_input_tokens - completed_input)
    worst_input = max(0, full.worst_case_input_tokens - completed_input)
    estimated_output = max(
        0,
        full.estimated_output_tokens
        - completed_count * settings.cloud_output_scene_boundary,
    )
    worst_output = max(
        0,
        full.worst_case_output_tokens
        - completed_count
        * (
            settings.cloud_output_scene_boundary
            + settings.cloud_output_json_schema_repair
        ),
    )
    estimated_total = estimated_input + estimated_output
    worst_total = worst_input + worst_output
    return StageEstimate(
        stage=full.stage,
        paragraph_count=full.paragraph_count,
        transition_count=full.transition_count,
        detection_batch_count=max(0, full.detection_batch_count - completed_count),
        adjudication_batch_count_estimated=full.adjudication_batch_count_estimated,
        scene_count=0,
        expected_request_count=expected_requests,
        worst_case_request_count=worst_requests,
        estimated_input_tokens=estimated_input,
        worst_case_input_tokens=worst_input,
        estimated_output_tokens=estimated_output,
        worst_case_output_tokens=worst_output,
        estimated_total_tokens=estimated_total,
        worst_case_total_tokens=worst_total,
        estimated_cost=_cost(estimated_input, estimated_output, pricing_path),
        worst_case_cost=_cost(worst_input, worst_output, pricing_path),
        currency=full.currency,
        pricing_version=full.pricing_version,
    )


def estimate_stage2_scene_analysis(
    session: Session,
    scenes: list[Scene],
    paragraphs: list[Paragraph],
    *,
    pricing_path: Path = Path("config/cloud_pricing.json"),
) -> StageEstimate:
    settings = get_settings()
    pricing = pricing_status(pricing_path)
    by_id = {item.id: item for item in paragraphs}
    position = {item.id: index for index, item in enumerate(paragraphs)}
    analysis_output = settings.cloud_output_scene_analysis
    repair_output = settings.cloud_output_business_repair
    estimated_input = 0
    for scene in scenes:
        start = position[scene.start_paragraph_id]
        end = position[scene.end_paragraph_id]
        included = paragraphs[start : end + 1]
        payload = {
            "scene_id": scene.scene_key,
            "paragraphs": [
                {"id": item.id, "text": by_id[item.id].normalized_text} for item in included
            ],
        }
        estimated_input += conservative_token_estimate(payload)
    scene_count = len(scenes)
    expected_requests = max(1, scene_count)
    worst_requests = 2 * max(1, scene_count)
    estimated_output = expected_requests * analysis_output
    worst_output = scene_count * (analysis_output + repair_output) if scene_count else 0
    estimated_total = estimated_input + estimated_output
    worst_total = estimated_input + worst_output
    estimated_cost = _cost(estimated_input, estimated_output, pricing_path)
    worst_cost = _cost(estimated_input, worst_output, pricing_path)
    currency = str(pricing.get("currency") or "CNY")
    version = pricing.get("pricing_version")
    return StageEstimate(
        stage=STAGE_ANALYSIS,
        paragraph_count=len(paragraphs),
        transition_count=0,
        detection_batch_count=0,
        adjudication_batch_count_estimated=0,
        scene_count=scene_count,
        expected_request_count=expected_requests,
        worst_case_request_count=worst_requests,
        estimated_input_tokens=estimated_input,
        worst_case_input_tokens=estimated_input,
        estimated_output_tokens=estimated_output,
        worst_case_output_tokens=worst_output,
        estimated_total_tokens=estimated_total,
        worst_case_total_tokens=worst_total,
        estimated_cost=estimated_cost,
        worst_case_cost=worst_cost,
        currency=currency,
        pricing_version=version if isinstance(version, str) else None,
    )


def estimate_to_dict(estimate: StageEstimate) -> dict[str, object]:
    return {
        "stage": estimate.stage,
        "paragraph_count": estimate.paragraph_count,
        "transition_count": estimate.transition_count,
        "detection_batch_count": estimate.detection_batch_count,
        "adjudication_batch_count_estimated": estimate.adjudication_batch_count_estimated,
        "scene_count": estimate.scene_count,
        "expected_request_count": estimate.expected_request_count,
        "worst_case_request_count": estimate.worst_case_request_count,
        "estimated_input_tokens": estimate.estimated_input_tokens,
        "worst_case_input_tokens": estimate.worst_case_input_tokens,
        "estimated_output_tokens": estimate.estimated_output_tokens,
        "worst_case_output_tokens": estimate.worst_case_output_tokens,
        "estimated_total_tokens": estimate.estimated_total_tokens,
        "worst_case_total_tokens": estimate.worst_case_total_tokens,
        "estimated_cost": estimate.estimated_cost,
        "worst_case_cost": estimate.worst_case_cost,
        "currency": estimate.currency,
        "pricing_version": estimate.pricing_version,
        "estimated": True,
    }


def estimate_reader_journey_scene_profiles(
    scenes: list[Scene],
    paragraphs: list[Paragraph],
    *,
    remaining_scene_ids: set[int] | None = None,
    pricing_path: Path = Path("config/cloud_pricing.json"),
) -> StageEstimate:
    """Stage 1: output-aware scene profile batches (default ≤2 scenes)."""
    from app.services.reader_journey_batch_planner import (
        plan_scene_batches,
        worst_case_requests_for_batches,
    )

    settings = get_settings()
    pricing = pricing_status(pricing_path)
    pending = [s for s in scenes if remaining_scene_ids is None or s.id in remaining_scene_ids]
    batches = plan_scene_batches(pending, paragraphs=paragraphs)
    batch_count = len(batches) or (1 if pending else 0)
    by_id = {item.id: item for item in paragraphs}
    position = {item.id: index for index, item in enumerate(paragraphs)}
    estimated_input = 0
    for scene in pending:
        start = position[scene.start_paragraph_id]
        end = position[scene.end_paragraph_id]
        included = paragraphs[start : end + 1]
        payload = {
            "scenes": [
                {
                    "id": scene.id,
                    "paragraphs": [
                        {"id": p.id, "text": by_id[p.id].normalized_text} for p in included
                    ],
                }
            ]
        }
        estimated_input += conservative_token_estimate(payload)
    scene_output = settings.cloud_output_reader_journey_scene
    repair_output = settings.cloud_output_reader_journey_business_repair
    expected_requests = max(1, batch_count) if pending else 0
    worst_requests = worst_case_requests_for_batches(batches) if batches else 0
    estimated_output = expected_requests * scene_output
    # Worst output: every leaf attempt + one repair per final unit.
    leaf_units = sum(max(1, len(batch.scenes)) for batch in batches) if batches else 0
    split_internals = sum(max(0, len(batch.scenes) - 1) for batch in batches) if batches else 0
    worst_output = (leaf_units + split_internals) * scene_output + leaf_units * repair_output
    estimated_total = estimated_input + estimated_output
    worst_total = estimated_input + worst_output
    currency = str(pricing.get("currency") or "CNY")
    version = pricing.get("pricing_version")
    return StageEstimate(
        stage=STAGE_READER_JOURNEY_SCENE,
        paragraph_count=len(paragraphs),
        transition_count=0,
        detection_batch_count=0,
        adjudication_batch_count_estimated=0,
        scene_count=len(pending),
        expected_request_count=expected_requests,
        worst_case_request_count=worst_requests,
        estimated_input_tokens=estimated_input,
        worst_case_input_tokens=estimated_input,
        estimated_output_tokens=estimated_output,
        worst_case_output_tokens=worst_output,
        estimated_total_tokens=estimated_total,
        worst_case_total_tokens=worst_total,
        estimated_cost=_cost(estimated_input, estimated_output, pricing_path),
        worst_case_cost=_cost(estimated_input, worst_output, pricing_path),
        currency=currency,
        pricing_version=version if isinstance(version, str) else None,
    )


def estimate_reader_journey_chapter_synthesis(
    scenes: list[Scene],
    *,
    pricing_path: Path = Path("config/cloud_pricing.json"),
) -> StageEstimate:
    settings = get_settings()
    pricing = pricing_status(pricing_path)
    scene_count = len(scenes)
    payload = {"scene_summaries": [{"ordinal": s.ordinal} for s in scenes]}
    estimated_input = conservative_token_estimate(payload)
    chapter_output = settings.cloud_output_reader_journey_chapter
    repair_output = settings.cloud_output_reader_journey_business_repair
    expected_requests = 1
    worst_requests = 2
    estimated_output = chapter_output
    worst_output = chapter_output + repair_output
    estimated_total = estimated_input + estimated_output
    worst_total = estimated_input + worst_output
    currency = str(pricing.get("currency") or "CNY")
    version = pricing.get("pricing_version")
    return StageEstimate(
        stage=STAGE_READER_JOURNEY_CHAPTER,
        paragraph_count=0,
        transition_count=0,
        detection_batch_count=0,
        adjudication_batch_count_estimated=0,
        scene_count=scene_count,
        expected_request_count=expected_requests,
        worst_case_request_count=worst_requests,
        estimated_input_tokens=estimated_input,
        worst_case_input_tokens=estimated_input,
        estimated_output_tokens=estimated_output,
        worst_case_output_tokens=worst_output,
        estimated_total_tokens=estimated_total,
        worst_case_total_tokens=worst_total,
        estimated_cost=_cost(estimated_input, estimated_output, pricing_path),
        worst_case_cost=_cost(estimated_input, worst_output, pricing_path),
        currency=currency,
        pricing_version=version if isinstance(version, str) else None,
    )
