import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    BoundaryDetectionBatchCheckpoint,
    Chapter,
    ModelInvocation,
    Paragraph,
    Scene,
)
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.base import ProviderRequestError
from app.services.structured_output import StructuredOutputError
from app.schemas.scene import (
    EvidenceField,
    SceneAnalysisResult,
    SceneBoundaryResult,
    SceneTransitionResult,
    CompactTransitionClassificationResult,
    CompactTransitionClassificationResultV34,
    CompactTransitionClassificationResultV35,
    BoundaryCandidateAdjudicationResult,
)
from app.services.prompt_service import load_prompt
from app.services.structured_output import generate_validated
from app.services.budget_reservation import release_run_reservation
from app.services.scene_transitions import build_adjacent_transitions, validate_and_map_transitions
from app.services.compact_transition_adapter import compact_to_canonical
from app.services.compact_transition_adapter_v34 import compact_v34_to_canonical
from app.services.transition_batch_planner import plan_transition_batches
from app.services.scene_boundary_adjudicator import (
    adjudicated_to_canonical,
    adjudication_snapshot,
    plan_adjudication_batches,
    validate_adjudication,
    validate_candidate_detection,
    validate_candidate_detection_for_review,
    validate_candidate_detection_structure,
)
from app.services.boundary_detection_checkpoints import (
    PlannedDetectionBatch,
    checkpoint_validation,
    completed_checkpoint,
    ordered_checkpoint_decisions,
    upsert_detection_checkpoint,
)


def aggregate_boundary_candidates(
    paragraphs: list[Paragraph],
    windows: list[list[Paragraph]],
    results: list[SceneBoundaryResult],
    min_confidence: float,
    min_vote_ratio: float,
) -> tuple[list[str], list[dict[str, object]], list[dict[str, object]]]:
    last_id = paragraphs[-1].id
    eligible: dict[str, int] = {}
    for window in windows:
        for paragraph in window[:-1]:
            if paragraph.id != last_id:
                eligible[paragraph.id] = eligible.get(paragraph.id, 0) + 1
    selected: dict[str, list[object]] = {}
    for result in results:
        for boundary in result.boundaries:
            selected.setdefault(boundary.after_paragraph_id, []).append(boundary)
    stats: list[dict[str, object]] = []
    adopted: list[str] = []
    positions = {item.id: item.paragraph_index for item in paragraphs}
    for paragraph_id, count in eligible.items():
        votes = selected.get(paragraph_id, [])
        confidences = [item.confidence for item in votes]
        reasons = sorted({reason for item in votes for reason in item.reasons})
        selected_count = len(votes)
        average = sum(confidences) / selected_count if selected_count else 0.0
        vote_ratio = selected_count / count
        item = {
            "after_paragraph_id": paragraph_id,
            "eligible_window_count": count,
            "selected_count": selected_count,
            "vote_ratio": vote_ratio,
            "confidence_max": max(confidences, default=0.0),
            "confidence_average": average,
            "reasons": reasons,
        }
        stats.append(item)
        if selected_count and average >= min_confidence and vote_ratio >= min_vote_ratio:
            adopted.append(paragraph_id)
    stats.sort(key=lambda item: positions[str(item["after_paragraph_id"])])
    adopted.sort(key=lambda item: positions[item])
    rejected = [
        item
        for item in stats
        if item["selected_count"] and item["after_paragraph_id"] not in adopted
    ]
    return adopted, stats, rejected


def chapter_key(chapter: Chapter) -> str:
    return f"B{chapter.book_id:04d}-C{chapter.chapter_index:04d}"


def build_windows(paragraphs: list[Paragraph]) -> list[list[Paragraph]]:
    settings = get_settings()
    maximum = settings.scene_window_max_chars
    overlap = settings.scene_window_overlap_paragraphs
    windows: list[list[Paragraph]] = []
    start = 0
    while start < len(paragraphs):
        end = start
        size = 0
        while end < len(paragraphs) and (
            size + len(paragraphs[end].normalized_text) <= maximum or end == start
        ):
            size += len(paragraphs[end].normalized_text)
            end += 1
        windows.append(paragraphs[start:end])
        if end == len(paragraphs):
            break
        start = max(start + 1, end - overlap)
    return windows


def validate_boundaries(
    result: SceneBoundaryResult,
    expected_chapter_key: str,
    paragraphs: list[Paragraph],
    allowed_ids: set[str] | None = None,
    strict_contract: bool = False,
) -> None:
    if result.chapter_id != expected_chapter_key:
        raise ValueError("边界结果章节 ID 不匹配")
    positions = {item.id: item.paragraph_index for item in paragraphs}
    boundary_ids = [item.after_paragraph_id for item in result.boundaries]
    permitted = allowed_ids if allowed_ids is not None else set(positions)
    if any(item not in positions or item not in permitted for item in boundary_ids):
        raise ValueError("边界引用了不存在或跨章节的段落")
    if paragraphs and paragraphs[-1].id in boundary_ids:
        raise ValueError("章节最后一段不能作为内部边界")
    indices = [positions[item] for item in boundary_ids]
    if indices != sorted(set(indices)):
        raise ValueError("边界必须有序且不重复")
    for boundary in result.boundaries if strict_contract else []:
        if boundary.reason_code is None or not boundary.reason_summary.strip():
            raise ValueError("boundary reason_code and reason_summary are required")
        if (
            not boundary.previous_scene_end_state.strip()
            or not boundary.next_scene_start_state.strip()
        ):
            raise ValueError("boundary state transition is required")
        if boundary.previous_scene_end_state.strip() == boundary.next_scene_start_state.strip():
            raise ValueError("boundary states must describe a real change")


def scene_ranges(
    paragraphs: list[Paragraph], boundary_ids: list[str]
) -> list[tuple[Paragraph, Paragraph]]:
    positions = {paragraph.id: index for index, paragraph in enumerate(paragraphs)}
    ends = [positions[item] for item in boundary_ids] + [len(paragraphs) - 1]
    ranges: list[tuple[Paragraph, Paragraph]] = []
    start = 0
    for end in ends:
        if end < start:
            raise ValueError("场景范围重叠")
        ranges.append((paragraphs[start], paragraphs[end]))
        start = end + 1
    if start != len(paragraphs):
        raise ValueError("场景未连续覆盖整章")
    return ranges


def _normalize_evidence_ids(ids: list[str], allowed_ids: set[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in ids:
        if item not in allowed_ids or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return sorted(ordered)


def _normalize_evidence_field(field: EvidenceField, allowed_ids: set[str]) -> EvidenceField:
    return field.model_copy(
        update={
            "evidence_paragraph_ids": _normalize_evidence_ids(
                field.evidence_paragraph_ids, allowed_ids
            )
        }
    )


def normalize_scene_analysis_result(
    result: SceneAnalysisResult,
    allowed_ids: set[str],
) -> SceneAnalysisResult:
    """Deterministic evidence ID cleanup only; never fabricate key_actions."""
    return result.model_copy(
        update={
            "entry_state": _normalize_evidence_field(result.entry_state, allowed_ids),
            "goal": _normalize_evidence_field(result.goal, allowed_ids),
            "obstacle": _normalize_evidence_field(result.obstacle, allowed_ids),
            "turning_point": _normalize_evidence_field(result.turning_point, allowed_ids),
            "outcome": _normalize_evidence_field(result.outcome, allowed_ids),
            "unresolved_question": _normalize_evidence_field(
                result.unresolved_question, allowed_ids
            ),
            "key_actions": [
                _normalize_evidence_field(item, allowed_ids) for item in result.key_actions
            ],
        }
    )


def apply_scene_analysis_normalization(
    value: SceneAnalysisResult,
    allowed_ids: set[str],
) -> SceneAnalysisResult:
    """Normalize evidence IDs and copy results onto the live model instance."""
    normalized = normalize_scene_analysis_result(value, allowed_ids)
    value.entry_state = normalized.entry_state
    value.goal = normalized.goal
    value.obstacle = normalized.obstacle
    value.key_actions = normalized.key_actions
    value.turning_point = normalized.turning_point
    value.outcome = normalized.outcome
    value.unresolved_question = normalized.unresolved_question
    return value


def _validate_scene_analysis_normalized(
    value: SceneAnalysisResult,
    scene_key: str,
    allowed_ids: set[str],
    strict_contract: bool,
) -> None:
    apply_scene_analysis_normalization(value, allowed_ids)
    validate_scene_analysis(value, scene_key, allowed_ids, strict_contract)


def is_evidence_paragraph_validation_error(message: str) -> bool:
    """True when failure is about paragraph evidence scope, not empty key_actions."""
    if "key_actions requires at least one evidenced action" in message:
        return False
    if "key_actions 每项必须包含" in message:
        return True
    lower = message.lower()
    if "必须包含证据" in message:
        return True
    if "证据段落" in message or "位于当前场景之外" in message:
        return True
    if "evidence_paragraph" in lower:
        return True
    if "paragraph" in lower and ("outside" in lower or "不存在" in message):
        return True
    return "evidence" in lower and "evidenced action" not in lower


def describe_scene_validation_failure(
    result: SceneAnalysisResult,
    allowed_ids: set[str],
    error_message: str,
) -> dict[str, object]:
    categories: list[str] = []
    illegal_evidence_ids: list[dict[str, str]] = []
    for path, paragraph_id in evidence_fields(result):
        if paragraph_id not in allowed_ids:
            illegal_evidence_ids.append(
                {"field_path": path, "paragraph_id": paragraph_id}
            )
    if illegal_evidence_ids:
        categories.append("out_of_scene_or_missing_paragraph")
    if "必须包含证据" in error_message:
        categories.append("required_field_missing_evidence")
    if (
        "key_actions requires" in error_message
        or "key_actions 每项必须包含" in error_message
    ):
        categories.append("key_actions_missing_evidence")
    # Empty key_actions is a legal shape for dialogue/emotion/info scenes; only note it.
    if not result.key_actions and "key_actions" in error_message:
        categories.append("key_actions_empty")
    if "must not cite the whole scene" in error_message:
        categories.append("indiscriminate_scene_citation")
    if "must not reuse one generic summary" in error_message:
        categories.append("duplicate_summaries")
    if not categories:
        categories.append("other")
    return {
        "validation_error_message": error_message,
        "categories": categories,
        "allowed_paragraph_ids": sorted(allowed_ids),
        "illegal_evidence_ids": illegal_evidence_ids,
        "key_actions_count": len(result.key_actions),
    }


def validate_scene_analysis(
    result: SceneAnalysisResult,
    expected_scene_key: str,
    allowed_ids: set[str],
    strict_contract: bool = False,
) -> None:
    if result.scene_id != expected_scene_key:
        raise ValueError("场景分析的 Scene ID 不匹配")
    required = (result.entry_state, result.goal, result.outcome)
    if any(not item.evidence_paragraph_ids for item in required):
        raise ValueError("entry_state、goal、outcome 必须包含证据")
    fields: list[EvidenceField] = [
        result.entry_state,
        result.goal,
        result.obstacle,
        *result.key_actions,
        result.turning_point,
        result.outcome,
        result.unresolved_question,
    ]
    evidence = [paragraph_id for field in fields for paragraph_id in field.evidence_paragraph_ids]
    if any(item not in allowed_ids for item in evidence):
        raise ValueError("证据段落不存在或位于当前场景之外")
    if not strict_contract:
        return
    if not result.entry_state.summary.strip() or not result.goal.summary.strip():
        raise ValueError("entry_state and goal must be complete")
    # Empty key_actions is legal when the scene has no clear physical/plot action.
    # Non-empty items must each carry a summary and in-scene evidence (never fabricate).
    if any(
        not item.summary.strip() or not item.evidence_paragraph_ids for item in result.key_actions
    ):
        raise ValueError("key_actions 每项必须包含非空 summary 与当前场景内证据")
    if not result.outcome.summary.strip() or not result.function_tags:
        raise ValueError("outcome and scene function must be complete")
    # Single-paragraph scenes can only cite one id; identical evidence sets are expected.
    if len(allowed_ids) <= 1:
        return
    summaries = [item.summary.strip() for item in fields if item.summary.strip()]
    if len(summaries) != len(set(summaries)):
        raise ValueError("analysis fields must not reuse one generic summary")
    nonempty_evidence = [
        set(item.evidence_paragraph_ids) for item in fields if item.summary.strip()
    ]
    if (
        len(nonempty_evidence) >= 4
        and len({tuple(sorted(item)) for item in nonempty_evidence}) == 1
    ):
        raise ValueError("all analysis fields must not cite the whole scene indiscriminately")


def evidence_fields(result: SceneAnalysisResult) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    named = {
        "entry_state.evidence": result.entry_state,
        "goal.evidence": result.goal,
        "obstacle.evidence": result.obstacle,
        "turning_point.evidence": result.turning_point,
        "outcome.evidence": result.outcome,
        "unresolved_question.evidence": result.unresolved_question,
    }
    for path, field in named.items():
        pairs.extend((path, item) for item in field.evidence_paragraph_ids)
    for index, field in enumerate(result.key_actions):
        pairs.extend(
            (f"key_actions.{index}.evidence", item) for item in field.evidence_paragraph_ids
        )
    return pairs


async def execute_scene_pipeline(
    session_factory: sessionmaker[Session], gateway: ModelGateway, run_id: int
) -> None:
    with session_factory() as session:
        from app.services.credentials.service import get_credential_store
        from app.services.provider_runtime_service import ProviderRuntimeService

        try:
            ProviderRuntimeService.bind_gateway(gateway, session, get_credential_store())
        except Exception:
            ProviderRuntimeService.bind_gateway(gateway, session, None)
        run = session.get(AnalysisRun, run_id)
        if run is None:
            return
        if run.status not in {"boundary_candidates_running"}:
            run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        session.commit()
        try:
            awaiting_review = await _execute(session, gateway, run)
            if not awaiting_review:
                run.status = "succeeded"
                run.completed_at = datetime.now(timezone.utc)
            session.commit()
        except Exception as exc:
            session.rollback()
            run = session.get(AnalysisRun, run_id)
            if run is not None:
                run.error_code = "SCENE_PIPELINE_FAILED"
                root_code, stage, retryable, hint = classify_pipeline_error(exc)
                checkpoint_count = len(
                    list(
                        session.scalars(
                            select(BoundaryDetectionBatchCheckpoint.id).where(
                                BoundaryDetectionBatchCheckpoint.run_id == run.id,
                                BoundaryDetectionBatchCheckpoint.status.in_(
                                    ["completed", "conflicted_completed"]
                                ),
                            )
                        )
                    )
                )
                if run.analysis_mode == "assisted_boundary_review":
                    if stage == "provider_request":
                        run.status = (
                            "boundary_candidates_partial"
                            if checkpoint_count
                            else "failed_provider"
                        )
                    elif stage in {
                        "json_validation",
                        "schema_validation",
                        "structured_output",
                        "structural_validation",
                        "business_validation",
                    }:
                        run.status = "failed_structural"
                    else:
                        run.status = "failed"
                else:
                    run.status = "failed"
                run.error_message = "场景分析失败"
                run.root_error_code = root_code
                detail_message = str(exc).strip() or root_code
                run.root_error_message = detail_message[:2000]
                run.failed_stage = stage
                run.retryable = retryable
                run.user_action_hint = hint
                from app.services.provider_runtime import apply_provider_runtime
                from app.services.credentials.service import get_credential_store

                provider = gateway.get(run.provider)
                try:
                    store = get_credential_store()
                except Exception:
                    store = None
                apply_provider_runtime(provider, session, store)
                health = await provider.health()
                failure_payload = {
                    "health": health.model_dump(),
                    "failure": {
                        "error_code": root_code,
                        "failed_stage": stage,
                        "retryable": retryable,
                        "exception_type": type(exc).__name__,
                    },
                }
                if isinstance(exc, StructuredOutputError):
                    failure_payload["failure"].update(exc.as_safe_dict())
                    if exc.failed_invocation_id:
                        run.failed_invocation_id = exc.failed_invocation_id
                    if exc.provider_error is not None:
                        failure_payload["failure"]["transport_kind"] = (
                            exc.provider_error.transport_kind
                        )
                        failure_payload["failure"]["http_status"] = (
                            exc.provider_error.http_status_code
                        )
                        failure_payload["failure"]["request_id"] = exc.provider_error.request_id
                elif isinstance(exc, ProviderRequestError):
                    failure_payload["failure"].update(exc.as_safe_dict())
                else:
                    from app.services.cloud_budget import RequestBlockedError

                    if isinstance(exc, RequestBlockedError):
                        failure_payload["failure"].update(exc.as_safe_dict())
                run.provider_health_at_failure = json.dumps(
                    failure_payload, ensure_ascii=False
                )
                if not run.failed_invocation_id:
                    invocation = session.scalar(
                        select(ModelInvocation)
                        .where(ModelInvocation.run_id == run.id)
                        .order_by(ModelInvocation.id.desc())
                    )
                    run.failed_invocation_id = invocation.id if invocation else None
                run.completed_at = datetime.now(timezone.utc)
                session.commit()
        finally:
            release_run_reservation(session, run_id, stage="boundary_review_generation")
            release_run_reservation(session, run_id)


def classify_pipeline_error(exc: Exception) -> tuple[str, str, bool, str]:
    """Classify pipeline failures without defaulting transport errors to business validation."""
    from app.services.cloud_budget import RequestBlockedError
    from app.services.validation_errors import StructuralValidationError

    if isinstance(exc, RequestBlockedError):
        code = exc.reason_code or "CLOUD_BUDGET_EXCEEDED"
        if code not in {
            "CLOUD_BUDGET_EXCEEDED",
            "CLOUD_REQUEST_LIMIT_EXCEEDED",
            "CLOUD_TOKEN_LIMIT_EXCEEDED",
            "CLOUD_COST_LIMIT_EXCEEDED",
            "CLOUD_MASTER_SWITCH_OFF",
        }:
            code = "CLOUD_BUDGET_EXCEEDED"
        hint = "今日云端分析额度不足，请调整预算后重新开始分析。"
        if code == "CLOUD_MASTER_SWITCH_OFF":
            hint = "云端总开关已关闭，请在设置中启用以继续分析。"
        return (code, "budget_gate", True, hint)
    if isinstance(exc, StructuralValidationError):
        code = exc.error_code or "STRUCTURAL_VALIDATION_FAILED"
        if code.startswith("JOURNEY_"):
            return (
                code,
                "business_validation",
                not bool(exc.no_model_repair),
                "查看业务校验详情",
            )
        return (
            code,
            "structural_validation",
            not bool(exc.no_model_repair),
            "可从已完成批次继续；请检查覆盖、顺序和ID",
        )
    if isinstance(exc, ProviderRequestError):
        return (
            exc.error_code,
            "provider_request",
            bool(exc.retryable),
            exc.user_action_hint or "前往“模型与API”运行传输诊断后重试",
        )
    if isinstance(exc, StructuredOutputError):
        from app.services.model_invocation_broker import POLICY_ERROR_CODES

        if exc.error_code in POLICY_ERROR_CODES or exc.category == "model_invocation_policy":
            return (
                exc.error_code,
                "model_invocation_policy",
                False,
                "检查 AnalysisRun 冻结的 Provider/Model 策略；禁止未授权 Fallback",
            )
        if exc.provider_error is not None:
            provider_exc = exc.provider_error
            if provider_exc.error_code in POLICY_ERROR_CODES:
                return (
                    provider_exc.error_code,
                    "model_invocation_policy",
                    False,
                    provider_exc.user_action_hint
                    or "检查 AnalysisRun 冻结的 Provider/Model 策略；禁止未授权 Fallback",
                )
            return (
                provider_exc.error_code or exc.error_code,
                "provider_request",
                bool(provider_exc.retryable if provider_exc.retryable is not None else exc.retryable),
                provider_exc.user_action_hint
                or "前往“模型与API”运行传输诊断后重试",
            )
        if exc.category == "provider_request" or exc.error_code.startswith("PROVIDER_"):
            return (
                exc.error_code,
                "provider_request",
                bool(exc.retryable),
                "前往“模型与API”运行传输诊断后重试",
            )
        if exc.category == "json_validation" or exc.error_code in {
            "JSON_PARSE_FAILED",
            "VALIDATION_ERROR",
            "STRUCTURED_OUTPUT_ERROR",
        }:
            if "json" in str(exc).lower() or exc.error_code in {
                "JSON_PARSE_FAILED",
                "VALIDATION_ERROR",
            }:
                return (
                    "JSON_PARSE_FAILED",
                    "json_validation",
                    True,
                    "可重试；若持续失败请检查模型输出长度",
                )
        if exc.category == "schema_validation" or exc.error_code == "SCHEMA_VALIDATION_FAILED":
            return (
                "SCHEMA_VALIDATION_FAILED",
                "schema_validation",
                True,
                "重试或检查模型结构化输出能力",
            )
        if (
            exc.category == "structural_validation"
            or exc.error_code == "STRUCTURAL_VALIDATION_FAILED"
        ):
            return (
                "STRUCTURAL_VALIDATION_FAILED",
                "structural_validation",
                True,
                "可从已完成批次继续；请检查transition覆盖、顺序和ID",
            )
        if exc.category == "evidence_validation" or exc.error_code == "EVIDENCE_VALIDATION_FAILED":
            return (
                "EVIDENCE_VALIDATION_FAILED",
                "evidence_validation",
                True,
                "重试并检查段落证据范围",
            )
        if exc.category == "business_validation" or exc.error_code == "BUSINESS_VALIDATION_FAILED":
            return (
                "BUSINESS_VALIDATION_FAILED",
                "business_validation",
                False,
                "查看脱敏技术详情",
            )
        if exc.error_code == "OUTPUT_TRUNCATED":
            return (
                "OUTPUT_TRUNCATED",
                "structured_output",
                True,
                "可重试；输出曾被截断",
            )
        # Structured output without provider cause and without business category:
        # treat as structured failure, never silent business validation.
        return (
            exc.error_code or "STRUCTURED_OUTPUT_ERROR",
            "structured_output",
            bool(exc.retryable),
            "可重试；查看脱敏技术详情",
        )
    message = str(exc).lower()
    from app.services.scene_pipeline import is_evidence_paragraph_validation_error

    if is_evidence_paragraph_validation_error(str(exc)):
        return "EVIDENCE_VALIDATION_FAILED", "evidence_validation", True, "重试并检查段落证据范围"
    if "边界" in message and "provider" not in message:
        return (
            "SCENE_BOUNDARY_QUALITY_FAILED",
            "scene_boundary",
            True,
            "更换通过质量门槛的Provider后重试",
        )
    # Unknown non-provider exceptions: keep diagnosable, do not claim business validation.
    return (
        "PIPELINE_UNEXPECTED_ERROR",
        "pipeline",
        True,
        "查看脱敏技术详情；必要时重试或联系维护者",
    )


async def _execute(session: Session, gateway: ModelGateway, run: AnalysisRun) -> bool:
    chapter = session.get(Chapter, int(run.subject_id))
    if chapter is None:
        raise ValueError("章节不存在")
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter.id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    if not paragraphs:
        raise ValueError("章节没有段落")
    key = chapter_key(chapter)
    boundary_prompt = load_prompt("scene_boundary", run.prompt_version)
    windows = build_windows(paragraphs)
    window_results: list[SceneBoundaryResult] = []
    run.progress_total = len(windows)
    session.commit()
    detection_batch_index = 0
    for window_index, window in enumerate(windows, 1):
        transition_candidates = build_adjacent_transitions([item.id for item in window])
        snapshot = {
            "chapter_id": key,
            "title": chapter.title,
            "paragraphs": [{"id": item.id, "text": item.normalized_text} for item in window],
        }
        allowed = {item.id for item in window}
        if run.prompt_version == "v3.5":
            batches = plan_transition_batches(transition_candidates, contract_version="3.5")
            paragraph_payload = {
                item.id: {"id": item.id, "text": item.normalized_text} for item in window
            }
            paragraph_text = {item.id: item.normalized_text for item in window}
            decisions = []
            valid_decisions = []
            for batch in batches:
                detection_batch_index += 1
                planned = PlannedDetectionBatch(
                    batch_index=detection_batch_index,
                    window_index=window_index,
                    batch=batch,
                    transitions=transition_candidates,
                )
                owned = [
                    item
                    for item in transition_candidates
                    if item.transition_id in batch.owned_transition_ids
                ]
                batch_snapshot = {
                    "chapter_id": key,
                    "title": chapter.title,
                    "paragraphs": [
                        paragraph_payload[item]
                        for item in batch.context_paragraph_ids
                        if item in paragraph_payload
                    ],
                    "transitions": [item.as_dict() for item in owned],
                    "owned_transition_ids": list(batch.owned_transition_ids),
                }
                checkpoint = completed_checkpoint(
                    session, run.id, detection_batch_index, run.prompt_version
                )
                if checkpoint is not None:
                    recovered = ordered_checkpoint_decisions(checkpoint)
                    validation = checkpoint_validation(checkpoint)
                    decisions.extend(recovered)
                    valid_decisions.extend(validation.valid_decisions)
                    continue
                assisted = run.analysis_mode == "assisted_boundary_review"
                try:
                    compact = await generate_validated(
                        session=session,
                        gateway=gateway,
                        run_id=run.id,
                        provider_name=run.provider,
                        task_type="scene_boundary",
                        prompt=boundary_prompt,
                        schema=CompactTransitionClassificationResultV35,
                        input_snapshot=batch_snapshot,
                        user_content=boundary_prompt.user_template.format(
                            input_json=json.dumps(batch_snapshot, ensure_ascii=False)
                        ),
                        business_validator=(
                            (
                                lambda value, batch=batch:
                                validate_candidate_detection_structure(
                                    value.decisions, list(batch.owned_transition_ids)
                                )
                            )
                            if assisted
                            else (
                                lambda value, batch=batch: validate_candidate_detection(
                                    value.decisions, list(batch.owned_transition_ids)
                                )
                            )
                        ),
                        initial_invocation_kind="boundary_candidate_detection",
                    )
                except StructuredOutputError as exc:
                    if assisted and exc.category in {
                        "json_validation",
                        "schema_validation",
                        "structured_output",
                        "structural_validation",
                        "business_validation",
                    }:
                        upsert_detection_checkpoint(
                            session,
                            run=run,
                            chapter_id=chapter.id,
                            planned=planned,
                            invocation_id=exc.failed_invocation_id,
                            validation=None,
                            status="failed_structural",
                        )
                    raise
                validation = validate_candidate_detection_for_review(
                    compact.decisions, list(batch.owned_transition_ids)
                )
                latest = session.scalar(
                    select(ModelInvocation)
                    .where(ModelInvocation.run_id == run.id)
                    .order_by(ModelInvocation.id.desc())
                )
                upsert_detection_checkpoint(
                    session,
                    run=run,
                    chapter_id=chapter.id,
                    planned=planned,
                    invocation_id=latest.id if latest else None,
                    validation=validation,
                    status=(
                        "conflicted_completed" if validation.issues else "completed"
                    ),
                )
                decisions.extend(compact.decisions)
                valid_decisions.extend(validation.valid_decisions)
            candidate_ids = [
                item.transition_id for item in valid_decisions if item.boundary_candidate
            ]
            adjudication_batches = plan_adjudication_batches(
                candidate_ids, transition_candidates, paragraph_text
            )
            verdicts = []
            adjudication_prompt = load_prompt("scene_boundary_adjudication", "v1")
            for batch in adjudication_batches:
                adjudication_input = adjudication_snapshot(
                    chapter_id=key,
                    title=chapter.title,
                    batch=batch,
                    candidates=transition_candidates,
                    decisions=valid_decisions,
                    paragraph_text=paragraph_text,
                )
                adjudicated = await generate_validated(
                    session=session,
                    gateway=gateway,
                    run_id=run.id,
                    provider_name=run.provider,
                    task_type="scene_boundary_adjudication",
                    prompt=adjudication_prompt,
                    schema=BoundaryCandidateAdjudicationResult,
                    input_snapshot=adjudication_input,
                    user_content=adjudication_prompt.user_template.format(
                        input_json=json.dumps(adjudication_input, ensure_ascii=False)
                    ),
                    business_validator=lambda value, batch=batch: validate_adjudication(
                        value, list(batch.candidate_transition_ids)
                    ),
                    initial_invocation_kind="boundary_candidate_adjudication",
                )
                verdicts.extend(adjudicated.verdicts)
            result = adjudicated_to_canonical(
                chapter_id=key,
                decisions=valid_decisions,
                verdicts=BoundaryCandidateAdjudicationResult(
                    contract_version="1.0", verdicts=verdicts
                ),
                candidates=transition_candidates,
                allowed_paragraph_ids=allowed,
            )
        elif run.prompt_version in {"v3.3", "v3.4"}:
            batches = plan_transition_batches(transition_candidates)
            mapped_results = []
            paragraph_payload = {
                item.id: {"id": item.id, "text": item.normalized_text} for item in window
            }
            for batch in batches:
                owned = [
                    item
                    for item in transition_candidates
                    if item.transition_id in batch.owned_transition_ids
                ]
                batch_snapshot = {
                    "chapter_id": key,
                    "paragraphs": [
                        paragraph_payload[item]
                        for item in batch.context_paragraph_ids
                        if item in paragraph_payload
                    ],
                    "transitions": [item.as_dict() for item in owned],
                    "owned_transition_ids": list(batch.owned_transition_ids),
                }
                adapter = (
                    compact_v34_to_canonical
                    if run.prompt_version == "v3.4"
                    else compact_to_canonical
                )
                compact_schema = (
                    CompactTransitionClassificationResultV34
                    if run.prompt_version == "v3.4"
                    else CompactTransitionClassificationResult
                )
                compact = await generate_validated(
                    session=session,
                    gateway=gateway,
                    run_id=run.id,
                    provider_name=run.provider,
                    task_type="scene_boundary",
                    prompt=boundary_prompt,
                    schema=compact_schema,
                    input_snapshot=batch_snapshot,
                    user_content=boundary_prompt.user_template.format(
                        input_json=json.dumps(batch_snapshot, ensure_ascii=False)
                    ),
                    business_validator=lambda value, owned=owned, batch=batch, adapter=adapter: adapter(
                        value,
                        expected_transition_ids=list(batch.owned_transition_ids),
                        candidates=owned,
                        allowed_paragraph_ids=set(batch.context_paragraph_ids),
                        chapter_id=key,
                    ),
                )
                mapped_results.append(
                    adapter(
                        compact,
                        expected_transition_ids=list(batch.owned_transition_ids),
                        candidates=owned,
                        allowed_paragraph_ids=set(batch.context_paragraph_ids),
                        chapter_id=key,
                    )
                )
            result = SceneBoundaryResult(
                chapter_id=key,
                boundaries=[item for mapped in mapped_results for item in mapped.boundaries],
                overall_confidence=(
                    sum(item.overall_confidence for item in mapped_results) / len(mapped_results)
                    if mapped_results
                    else 1.0
                ),
            )
        elif run.prompt_version == "v3.2":
            snapshot["transitions"] = [item.as_dict() for item in transition_candidates]
            transition_result = await generate_validated(
                session=session,
                gateway=gateway,
                run_id=run.id,
                provider_name=run.provider,
                task_type="scene_boundary",
                prompt=boundary_prompt,
                schema=SceneTransitionResult,
                input_snapshot=snapshot,
                user_content=boundary_prompt.user_template.format(
                    input_json=json.dumps(snapshot, ensure_ascii=False)
                ),
                business_validator=lambda value, candidates=transition_candidates: (
                    validate_and_map_transitions(
                        value,
                        expected_chapter_id=key,
                        candidates=candidates,
                        allowed_paragraph_ids=allowed,
                    )
                ),
            )
            result = validate_and_map_transitions(
                transition_result,
                expected_chapter_id=key,
                candidates=transition_candidates,
                allowed_paragraph_ids=allowed,
            )
        else:
            result = await generate_validated(
                session=session,
                gateway=gateway,
                run_id=run.id,
                provider_name=run.provider,
                task_type="scene_boundary",
                prompt=boundary_prompt,
                schema=SceneBoundaryResult,
                input_snapshot=snapshot,
                user_content=boundary_prompt.user_template.format(
                    input_json=json.dumps(snapshot, ensure_ascii=False)
                ),
                business_validator=lambda value, items=paragraphs: validate_boundaries(
                    value, key, items, allowed, run.prompt_version == "v3"
                ),
            )
        window_results.append(result)
        run.progress_current += 1
        session.commit()
    settings = get_settings()
    ordered_ids, candidate_stats, rejected = aggregate_boundary_candidates(
        paragraphs,
        windows,
        window_results,
        settings.scene_boundary_min_confidence,
        settings.scene_boundary_min_vote_ratio,
    )
    stats_by_id = {str(item["after_paragraph_id"]): item for item in candidate_stats}
    window_confidences = [item.overall_confidence for item in window_results]
    overall_confidence = sum(window_confidences) / len(window_confidences)
    boundary_payload = {
        "chapter_id": key,
        "adopted_boundaries": [stats_by_id[item] for item in ordered_ids],
        "rejected_candidates": rejected,
        "candidate_statistics": candidate_stats,
        "window_overall_confidences": window_confidences,
        "overall_confidence": overall_confidence,
    }
    if run.prompt_version == "v3.5":
        position = {item.id: index for index, item in enumerate(paragraphs)}
        boundary_payload["boundary_evidence"] = [
            {
                "after_paragraph_id": item,
                "evidence_paragraph_ids": [item, paragraphs[position[item] + 1].id],
            }
            for item in ordered_ids
        ]
    session.add(
        AnalysisArtifact(
            run_id=run.id,
            artifact_type="scene_boundary",
            subject_type="chapter",
            subject_id=str(chapter.id),
            schema_version="v1",
            prompt_version=run.prompt_version,
            payload_json=json.dumps(boundary_payload, ensure_ascii=False),
            confidence=overall_confidence,
            validation_status="valid",
        )
    )
    session.commit()
    if run.prompt_version == "v3.5":
        from app.services.boundary_review_service import create_review_session

        create_review_session(session, run)
        return True
    ranges = scene_ranges(paragraphs, ordered_ids)
    run.progress_total += len(ranges)
    analysis_prompt = load_prompt(
        "scene_analysis",
        "v3.2"
        if run.prompt_version in {"v3.2", "v3.3", "v3.4", "v3.5"}
        else run.prompt_version,
    )
    paragraph_by_id = {item.id: item for item in paragraphs}
    for ordinal, (start, end) in enumerate(ranges, start=1):
        scene_key = f"{key}-S{ordinal:04d}"
        included = [
            item
            for item in paragraphs
            if start.paragraph_index <= item.paragraph_index <= end.paragraph_index
        ]
        boundary_stat = stats_by_id.get(end.id)
        detected = boundary_stat is not None and end.id in ordered_ids
        scene = Scene(
            scene_key=scene_key,
            book_id=chapter.book_id,
            chapter_id=chapter.id,
            ordinal=ordinal,
            start_paragraph_id=start.id,
            end_paragraph_id=end.id,
            content_hash=hashlib.sha256(
                "\n".join(item.normalized_text for item in included).encode()
            ).hexdigest(),
            created_by_run_id=run.id,
            boundary_detected=detected,
            boundary_confidence=float(boundary_stat["confidence_average"]) if detected else 0.0,
            boundary_reason_json=json.dumps(
                boundary_stat["reasons"] if detected else [], ensure_ascii=False
            ),
        )
        session.add(scene)
        session.flush()
        snapshot = {
            "scene_id": scene_key,
            "paragraphs": [{"id": item.id, "text": item.normalized_text} for item in included],
        }
        result = await generate_validated(
            session=session,
            gateway=gateway,
            run_id=run.id,
            provider_name=run.provider,
            task_type="scene_analysis",
            prompt=analysis_prompt,
            schema=SceneAnalysisResult,
            input_snapshot=snapshot,
            user_content=analysis_prompt.user_template.format(
                input_json=json.dumps(snapshot, ensure_ascii=False)
            ),
            business_validator=lambda value, allowed={item.id for item in included}: (
                _validate_scene_analysis_normalized(value, scene_key, allowed, run.prompt_version == "v3")
            ),
        )
        artifact = AnalysisArtifact(
            run_id=run.id,
            artifact_type="scene_analysis",
            subject_type="scene",
            subject_id=str(scene.id),
            schema_version="v1",
            prompt_version=run.prompt_version,
            payload_json=result.model_dump_json(),
            confidence=result.confidence,
            validation_status="valid",
        )
        session.add(artifact)
        session.flush()
        for field_path, paragraph_id in evidence_fields(result):
            paragraph = paragraph_by_id[paragraph_id]
            session.add(
                AnalysisEvidence(
                    artifact_id=artifact.id,
                    field_path=field_path,
                    paragraph_id=paragraph_id,
                    paragraph_hash=hashlib.sha256(paragraph.raw_text.encode()).hexdigest(),
                )
            )
        run.progress_current += 1
        session.commit()
    return False


def mark_interrupted_runs_failed(session: Session) -> None:
    now = datetime.now(timezone.utc)
    session.execute(
        update(AnalysisRun)
        .where(AnalysisRun.status.in_(["running", "boundary_candidates_running", "scene_analysis_running"]))
        .values(
            status="failed",
            error_code="PROCESS_INTERRUPTED",
            error_message="应用重启时任务仍在运行",
            completed_at=now,
        )
    )
    session.execute(
        update(AnalysisRun)
        .where(AnalysisRun.status == "queued")
        .values(
            status="failed",
            error_code="PROCESS_INTERRUPTED_BEFORE_START",
            error_message="应用重启前任务仍在队列中，无法自动恢复",
            completed_at=now,
        )
    )
    session.commit()
    from app.services.budget_reservation import release_run_reservation

    for run in session.scalars(
        select(AnalysisRun).where(AnalysisRun.error_code == "PROCESS_INTERRUPTED")
    ):
        release_run_reservation(session, run.id)
