import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ApplicationSetting, ModelInvocation, ProviderConfiguration
from app.core.config import get_settings
from app.model_gateway.base import ModelRequest, ProviderRequestError
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.structured_constraints import grammar_hash, schema_hash, schema_to_gbnf
from app.model_gateway.transport_retry import (
    compute_provider_retry_delay_seconds,
    should_retry_provider_error,
    transport_retry_policy_from_settings,
)
from app.services.prompt_service import PromptBundle
from app.services.prompt_service import with_response_contract
from app.services.budget_reservation import (
    CloudAttemptClaim,
    claim_cloud_request_slot,
    settle_cloud_attempt_usage,
)
from app.services.cloud_budget import RequestBlockedError, daily_usage
from app.services.cloud_pricing import estimate_cost, pricing_status
from app.services.validation_errors import StructuralValidationError
from app.services.cloud_output_policy import resolve_output_limit
from app.services.model_invocation_broker import (
    POLICY_ERROR_CODES,
    ModelInvocationPolicyError,
    broker as model_invocation_broker,
    load_run_model_policy,
    map_invocation_type,
)
from app.schemas.scene import SceneBoundaryResult
from app.schemas.settings import CloudBudgetUpdate

T = TypeVar("T", bound=BaseModel)


# Invocation kinds that render repair.md (must differ from normal request_hash).
REPAIR_MESSAGE_KINDS = frozenset(
    {
        "json_repair",
        "schema_repair",
        "evidence_repair",
        "business_repair",
        "structural_repair",
    }
)
# Structural / business / evidence repair: one round, independent transport budget.
STRUCTURAL_REPAIR_KINDS = frozenset(
    {"structural_repair", "business_repair", "evidence_repair"}
)
# Transport retries that belong to the structural-repair budget (DEFECT-010).
STRUCTURAL_REPAIR_TRANSPORT_KINDS = STRUCTURAL_REPAIR_KINDS | frozenset(
    {"repair_provider_retry"}
)


class StructuredOutputError(ValueError):
    def __init__(
        self,
        message: str | None,
        error_code: str = "STRUCTURED_OUTPUT_ERROR",
        *,
        category: str = "structured_output",
        retryable: bool = True,
        provider_error: ProviderRequestError | None = None,
        failed_invocation_id: int | None = None,
        primary_error: str | None = None,
        transport_error: str | None = None,
    ) -> None:
        text = (message or "").strip()
        if not text and provider_error is not None:
            text = str(provider_error)
        if not text:
            text = f"结构化输出失败 ({error_code})"
        super().__init__(text)
        self.error_code = error_code
        self.category = category
        self.retryable = retryable
        self.provider_error = provider_error
        self.failed_invocation_id = failed_invocation_id
        self.primary_error = primary_error
        self.transport_error = transport_error

    def as_safe_dict(self) -> dict:
        payload = {
            "error_code": self.error_code,
            "message": str(self),
            "category": self.category,
            "retryable": self.retryable,
            "failed_invocation_id": self.failed_invocation_id,
        }
        if self.primary_error is not None:
            payload["primary_error"] = self.primary_error
        if self.transport_error is not None:
            payload["transport_error"] = self.transport_error
        if self.provider_error is not None:
            payload["provider_error"] = self.provider_error.as_safe_dict()
        for key in (
            "invocation_type",
            "requested_provider",
            "requested_model",
            "resolved_provider",
            "resolved_model",
            "route_source",
            "auto_route",
            "fallback_used",
        ):
            value = getattr(self, key, None)
            if value is not None:
                payload[key] = value
        return payload


class OutputTruncatedError(StructuredOutputError):
    def __init__(self, message: str = "模型输出被输出上限截断") -> None:
        super().__init__(message, "OUTPUT_TRUNCATED", category="structured_output", retryable=True)


def _render_repair(template: str, values: dict[str, str]) -> str:
    """Render repair.md placeholders; keep legacy aliases for older prompt versions."""
    aliases = {
        "error_message": values.get("validation_error", ""),
        "invalid_json": values.get("raw_response", ""),
        "error": values.get("validation_error", ""),
    }
    merged = {**aliases, **values}
    rendered = template
    for name, value in merged.items():
        rendered = rendered.replace("{" + name + "}", value)
    return rendered


def _looks_truncated(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    start = stripped.find("{")
    if start < 0:
        return False
    depth = 0
    in_string = False
    escaped = False
    for char in stripped[start:]:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
    return in_string or depth > 0


def _claim_cloud_budget_attempt(
    session: Session, *, cloud: bool, run_id: int
) -> CloudAttemptClaim | None:
    """Per-attempt cloud budget gate + atomic reservation claim (no-op for local)."""
    if not cloud:
        return None
    cloud_row = session.get(ApplicationSetting, "cloud_enabled")
    budget_row = session.get(ApplicationSetting, "cloud_budget_settings")
    if cloud_row is None or budget_row is None:
        return None
    try:
        cloud_enabled = bool(json.loads(cloud_row.value_json))
    except (TypeError, json.JSONDecodeError):
        cloud_enabled = False
    if not cloud_enabled:
        raise RequestBlockedError(
            "CLOUD_MASTER_SWITCH_OFF",
            details={"run_id": run_id, "error_code": "CLOUD_MASTER_SWITCH_OFF"},
        )
    try:
        budget = CloudBudgetUpdate.model_validate_json(budget_row.value_json).model_dump()
    except Exception:
        return None
    pricing = pricing_status(Path("config/cloud_pricing.json"))
    usage = daily_usage(session, budget, cloud_enabled, pricing)
    from app.db.models import AnalysisRun
    from app.services.run_scoped_budget_auth import (
        apply_run_auth_to_usage,
        inflate_daily_limit_for_run,
    )

    run = session.get(AnalysisRun, run_id)
    usage = apply_run_auth_to_usage(run, usage, budget)
    if not usage.get("within_budget"):
        reasons = usage.get("blocked_reasons") or []
        code = "CLOUD_BUDGET_EXCEEDED"
        if any("请求" in str(r) for r in reasons):
            code = "CLOUD_REQUEST_LIMIT_EXCEEDED"
        elif any("Token" in str(r) for r in reasons):
            code = "CLOUD_TOKEN_LIMIT_EXCEEDED"
        elif any("费用" in str(r) for r in reasons):
            code = "CLOUD_COST_LIMIT_EXCEEDED"
        raise RequestBlockedError(
            code,
            details={
                "used": usage.get("request_count"),
                "used_requests": usage.get("request_count"),
                "used_tokens": usage.get("total_tokens"),
                "used_cost": usage.get("estimated_cost"),
                "reserved_remaining": usage.get("reserved_requests"),
                "daily_limit": usage.get("effective_daily_request_limit")
                or budget.get("cloud_daily_request_limit"),
                "requested_amount": 1,
                "run_id": run_id,
                "dimension": "budget",
            },
        )
    return claim_cloud_request_slot(
        session,
        run_id=run_id,
        available_requests=int(usage.get("available_requests") or 0),
        used_requests=int(usage.get("request_count") or 0),
        daily_limit=int(
            usage.get("effective_daily_request_limit")
            or inflate_daily_limit_for_run(run, int(budget.get("cloud_daily_request_limit") or 0))
        ),
    )


def extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        stripped = stripped[first_newline + 1 :] if first_newline >= 0 else stripped
        if stripped.endswith("```"):
            stripped = stripped[:-3].rstrip()
    start = stripped.find("{")
    if start < 0:
        raise StructuredOutputError("响应中没有 JSON 对象")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(stripped)):
        char = stripped[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]
    raise StructuredOutputError("JSON 对象不完整")


def _transport_max_attempts(*, cloud: bool, settings) -> int:
    if cloud:
        transport_policy = transport_retry_policy_from_settings(settings)
        return max(
            1,
            min(int(settings.aliyun_max_retries), int(transport_policy.max_attempts)),
        )
    return max(1, int(settings.model_max_attempts))


async def generate_validated(
    *,
    session: Session,
    gateway: ModelGateway,
    run_id: int,
    provider_name: str,
    task_type: str,
    prompt: PromptBundle,
    schema: type[T],
    input_snapshot: dict[str, object],
    user_content: str,
    business_validator: Callable[[T], None],
    initial_invocation_kind: str = "initial",
    allow_truncation_retry: bool = True,
    policy_invocation_type: str | None = None,
) -> T:
    """Generate + validate with independent normal vs repair transport budgets.

    DEFECT-CANARY-010 / journey-repair-resilience-change-v1.0.5:
    - normal generation: up to N transport attempts (provider_retry)
    - structural/business/evidence repair: at most 1 round
    - repair request: up to N independent transport attempts (repair_provider_retry)
    - normal and repair use different request bodies/hashes; repair retries share hash
    """
    prompt = with_response_contract(prompt, schema)
    original_messages = [
        {"role": "system", "content": prompt.system},
        {"role": "user", "content": user_content},
    ]
    messages = original_messages
    # Freeze provider/model for this generate_validated envelope (DEFECT-015).
    # Production callers pass AnalysisRun.provider / journey_run.provider_name.
    # Nested json/schema/structural repair and transport retry must inherit it.
    run_policy = load_run_model_policy(
        session,
        run_id,
        fallback_provider=provider_name,
        fallback_model=None,
    )
    authorized_provider = provider_name
    if (
        run_policy.source == "analysis_run"
        and run_policy.authorized_provider == provider_name
        and run_policy.authorized_model
    ):
        authorized_model = run_policy.authorized_model
    else:
        authorized_model = gateway.get(authorized_provider).default_model
    _cfg = session.scalar(
        select(ProviderConfiguration).where(
            ProviderConfiguration.provider_name == authorized_provider
        )
    )
    auto_route = bool(_cfg.allow_auto_route) if _cfg is not None else False
    last_error = ""
    last_provider_error: ProviderRequestError | None = None
    last_error_code = "STRUCTURED_OUTPUT_ERROR"
    last_category = "structured_output"
    last_retryable = True
    last_invocation_id: int | None = None
    previous_validation_error_code: str | None = None
    previous_raw = ""
    next_kind = initial_invocation_kind
    # DEFECT-015: never silently switch providers (e.g. Plus → Flash) for repair.
    next_provider_name = authorized_provider
    original_capabilities = gateway.get(authorized_provider).capabilities()
    settings = get_settings()
    transport_policy = transport_retry_policy_from_settings(settings)
    max_normal_transport = _transport_max_attempts(
        cloud=original_capabilities.cloud, settings=settings
    )
    max_repair_transport = max_normal_transport
    max_repair_rounds = 1
    # Hard ceiling: normal transport + one repair round of transport (+ a few
    # json/schema repairs still share the normal counter historically via kinds).
    max_total_requests = max_normal_transport + max_repair_rounds * max_repair_transport

    normal_transport_used = 0
    repair_transport_used = 0
    repair_rounds_used = 0
    total_requests = 0
    in_repair_phase = False
    primary_error: str | None = None
    primary_error_message: str | None = None
    repair_messages: list[dict[str, str]] | None = None
    last_repair_context: dict | None = None
    pre_repair_batch: object | None = None
    pre_repair_payload: dict | None = None
    targeted_evidence_repair = False
    targeted_evidence_compaction = False
    paragraph_ids_by_scene_cached: dict[int, set[str]] = {}

    while True:
        if total_requests >= max_total_requests:
            break
        if next_kind == "provider_retry":
            if not should_retry_provider_error(last_provider_error):
                break
            if normal_transport_used >= max_normal_transport:
                break
            if original_capabilities.cloud:
                delay = compute_provider_retry_delay_seconds(
                    normal_transport_used,
                    transport_policy,
                    retry_after=getattr(last_provider_error, "retry_after", None),
                )
                if delay > 0:
                    await asyncio.sleep(delay)
        elif next_kind == "repair_provider_retry":
            if not should_retry_provider_error(last_provider_error):
                break
            if repair_transport_used >= max_repair_transport:
                break
            if original_capabilities.cloud:
                delay = compute_provider_retry_delay_seconds(
                    repair_transport_used,
                    transport_policy,
                    retry_after=getattr(last_provider_error, "retry_after", None),
                )
                if delay > 0:
                    await asyncio.sleep(delay)
        elif next_kind in STRUCTURAL_REPAIR_KINDS:
            if repair_rounds_used >= max_repair_rounds and in_repair_phase:
                break
        elif next_kind in {"json_repair", "schema_repair", "truncation_retry"}:
            # JSON/schema/truncation still share the normal attempt envelope.
            if normal_transport_used >= max_normal_transport:
                break
        elif next_kind in {"truncation_abort", "validation_abort", "provider_abort"}:
            break

        invocation_provider_name = authorized_provider
        invocation_provider = gateway.get(invocation_provider_name)
        invocation_capabilities = invocation_provider.capabilities()
        budget_claim: CloudAttemptClaim | None = None

        entering_structural_repair = (
            next_kind in STRUCTURAL_REPAIR_KINDS and not in_repair_phase
        )
        if entering_structural_repair:
            in_repair_phase = True
            repair_rounds_used += 1
            repair_transport_used = 0
            if repair_rounds_used > max_repair_rounds:
                break

        if next_kind in REPAIR_MESSAGE_KINDS:
            use_compaction = (
                next_kind == "structural_repair"
                and primary_error == "JOURNEY_EVIDENCE_COUNT_INVALID"
                and str(task_type).startswith("reader_journey")
                and schema.__name__ == "SceneReaderJourneyBatchResult"
                and last_repair_context is not None
            )
            use_targeted = (
                next_kind == "structural_repair"
                and primary_error == "JOURNEY_EVIDENCE_OUT_OF_SCOPE"
                and str(task_type).startswith("reader_journey")
                and schema.__name__ == "SceneReaderJourneyBatchResult"
                and last_repair_context is not None
            )
            targeted_evidence_compaction = use_compaction
            # Broker maps both directed Evidence repairs to targeted_evidence_patch.
            targeted_evidence_repair = use_targeted or use_compaction
            if use_compaction:
                from app.services.reader_journey_evidence_compaction import (
                    render_compaction_repair_user_content,
                )

                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You compact Reader Journey top-level Evidence lists via a directed "
                            "compaction patch only. Never regenerate the full Profile or Journey. "
                            "replacement_evidence_paragraph_ids must be a subset of "
                            "current_evidence_ids, unique, and at most 16. Never forge IDs. "
                            "Never modify protected Profile fields."
                        ),
                    },
                    {
                        "role": "user",
                        "content": render_compaction_repair_user_content(
                            last_repair_context, previous_raw
                        ),
                    },
                ]
            elif use_targeted:
                from app.services.reader_journey_targeted_repair import (
                    render_targeted_repair_user_content,
                )

                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You repair Reader Journey Evidence scope errors via directed patches only. "
                            "Never regenerate the full Journey. Never forge Evidence. "
                            "Never borrow Evidence from other Scenes. Never mutate legal Profiles."
                        ),
                    },
                    {
                        "role": "user",
                        "content": render_targeted_repair_user_content(
                            last_repair_context, previous_raw
                        ),
                    },
                ]
            else:
                messages = [
                    {"role": "system", "content": prompt.system},
                    {
                        "role": "user",
                        "content": _render_repair(
                            prompt.repair_template,
                            {
                                "input_snapshot": json.dumps(
                                    input_snapshot, ensure_ascii=False
                                ),
                                "original_user_content": user_content,
                                "raw_response": previous_raw,
                                "validation_error": last_error,
                                "schema_json": json.dumps(
                                    schema.model_json_schema(), ensure_ascii=False
                                ),
                                "repair_reason": next_kind,
                            },
                        ),
                    },
                ]
            repair_messages = messages
        elif next_kind == "repair_provider_retry":
            messages = repair_messages or messages
            # Keep targeted mode sticky for repair transport retries.
        elif next_kind == "truncation_retry":
            messages = [
                {"role": "system", "content": prompt.system},
                {
                    "role": "user",
                    "content": (
                        user_content
                        + "\n上次输出因长度上限被截断。请从头重新生成完整JSON对象；"
                        "不要续写或拼接上次片段，只返回完整契约JSON。"
                    ),
                },
            ]
        elif next_kind == "provider_retry":
            messages = messages
        elif next_kind in {
            "initial",
            "boundary_candidate_detection",
            "boundary_candidate_adjudication",
            "normal_batch_request",
            "split_batch_request",
        }:
            messages = original_messages
        else:
            messages = original_messages

        invocation_kind = next_kind
        # Output-limit kind: repair transport retries reuse structural/business limit.
        limit_kind = invocation_kind
        if invocation_kind == "repair_provider_retry":
            limit_kind = (
                "evidence_repair" if targeted_evidence_compaction else "structural_repair"
            )
        if (
            targeted_evidence_compaction
            and invocation_kind in STRUCTURAL_REPAIR_TRANSPORT_KINDS
        ):
            # Compaction patches are small; use evidence_repair budget, not schema_repair.
            limit_kind = "evidence_repair"
        output_limit = resolve_output_limit(
            session,
            task_type=task_type,
            invocation_kind=limit_kind,
            cloud=invocation_capabilities.cloud,
        )
        active_schema: type[BaseModel] = schema
        if (
            targeted_evidence_compaction
            and invocation_kind in STRUCTURAL_REPAIR_TRANSPORT_KINDS
        ):
            from app.services.reader_journey_evidence_compaction import (
                JourneyEvidenceCompactionPatchResult,
            )

            active_schema = JourneyEvidenceCompactionPatchResult
        elif targeted_evidence_repair and invocation_kind in STRUCTURAL_REPAIR_TRANSPORT_KINDS:
            from app.services.reader_journey_targeted_repair import (
                JourneyEvidenceRepairPatchResult,
            )

            active_schema = JourneyEvidenceRepairPatchResult
        request = ModelRequest(
            messages=messages,
            model=authorized_model,
            max_output_tokens=output_limit.effective_limit,
            response_schema=active_schema.model_json_schema(),
            response_format_mode=invocation_capabilities.structured_output_mode,
            enable_thinking=False,
        )
        mapped_policy_type = map_invocation_type(
            task_type,
            invocation_kind,
            targeted_evidence_repair=targeted_evidence_repair,
        )
        # Optional override used by provider-recovery / qualification envelopes.
        effective_policy_type = policy_invocation_type or mapped_policy_type

        if invocation_kind in STRUCTURAL_REPAIR_TRANSPORT_KINDS or (
            in_repair_phase and invocation_kind in STRUCTURAL_REPAIR_KINDS
        ):
            if invocation_kind in STRUCTURAL_REPAIR_TRANSPORT_KINDS:
                repair_transport_used += 1
            attempt_no = max(1, repair_transport_used)
        else:
            normal_transport_used += 1
            attempt_no = normal_transport_used
        total_requests += 1

        started = time.perf_counter()
        raw = ""
        parsed_json: str | None = None
        status = "failed"
        error_code: str | None = None
        http_status_code: int | None = None
        response_model: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        total_tokens: int | None = None
        cached_tokens: int | None = None
        request_id: str | None = None
        finish_reason: str | None = None
        http_request_sent = False
        transition_audit: dict[str, object] = {}
        validation_audit: dict[str, object] = {}
        contract_version: str | None = getattr(schema, "CONTRACT_VERSION", None)
        resolved_invocation = None
        try:
            resolved_invocation = model_invocation_broker.resolve(
                run_id=run_id,
                invocation_type=effective_policy_type,
                authorized_provider=authorized_provider,
                authorized_model=authorized_model,
                auto_route=auto_route,
                requested_provider=next_provider_name or authorized_provider,
                requested_model=authorized_model,
                gateway=gateway,
                fallback_policy="none" if not auto_route else run_policy.fallback_policy,
                caller="structured_output.generate_validated",
                repair_context=last_repair_context,
            )
            invocation_provider_name = resolved_invocation.resolved_provider
            invocation_provider = gateway.get(invocation_provider_name)
            invocation_capabilities = invocation_provider.capabilities()
            request = request.model_copy(
                update={"model": resolved_invocation.resolved_model}
            )
            validation_audit.update(
                {
                    "invocation_type": resolved_invocation.invocation_type,
                    "requested_provider": resolved_invocation.requested_provider,
                    "requested_model": resolved_invocation.requested_model,
                    "resolved_provider": resolved_invocation.resolved_provider,
                    "resolved_model": resolved_invocation.resolved_model,
                    "route_source": resolved_invocation.route_source,
                    "auto_route": resolved_invocation.auto_route,
                    "fallback_used": resolved_invocation.fallback_used,
                    "provider_enabled": resolved_invocation.provider_enabled,
                    "policy_match": resolved_invocation.policy_match,
                    "request_hash_policy": resolved_invocation.request_hash_policy,
                }
            )
            # Claim after policy resolve, immediately before HTTP send.
            budget_claim = _claim_cloud_budget_attempt(
                session, cloud=invocation_capabilities.cloud, run_id=run_id
            )
            response = await model_invocation_broker.invoke(
                gateway=gateway,
                resolved=resolved_invocation,
                request=request,
            )
            http_request_sent = True
            raw = response.text
            response_model = response.model
            http_status_code = response.http_status_code
            input_tokens = response.input_tokens
            output_tokens = response.output_tokens
            total_tokens = response.total_tokens
            cached_tokens = response.cached_tokens
            request_id = response.request_id
            finish_reason = response.finish_reason
            if finish_reason in {"length", "max_tokens"} or _looks_truncated(raw):
                if targeted_evidence_compaction or (
                    primary_error == "JOURNEY_EVIDENCE_COUNT_INVALID" and in_repair_phase
                ):
                    raise StructuralValidationError(
                        "Evidence compaction patch output was truncated",
                        "JOURNEY_EVIDENCE_COMPACTION_OUTPUT_TRUNCATED",
                        failed_field="replacement_evidence_paragraph_ids",
                        repair_context=last_repair_context,
                        no_model_repair=True,
                    )
                raise OutputTruncatedError()
            parsed_json = extract_json_object(raw)
            if (
                targeted_evidence_compaction
                and invocation_kind in STRUCTURAL_REPAIR_TRANSPORT_KINDS
                and pre_repair_payload is not None
            ):
                from app.services.reader_journey_evidence_compaction import (
                    JourneyEvidenceCompactionPatchResult,
                    apply_evidence_compaction,
                )

                patch_result = JourneyEvidenceCompactionPatchResult.model_validate_json(
                    parsed_json
                )
                target = (last_repair_context or {}).get("targets") or []
                target0 = target[0] if target and isinstance(target[0], dict) else {}
                scene_id = int(target0.get("scene_id") or 0)
                current_ids = list(target0.get("current_evidence_ids") or [])
                patched = apply_evidence_compaction(
                    pre_repair_payload,
                    patch_result,
                    scene_id=scene_id,
                    current_evidence_ids=current_ids,
                )
                result = schema.model_validate(patched)
                parsed_json = result.model_dump_json()
            elif (
                targeted_evidence_repair
                and not targeted_evidence_compaction
                and invocation_kind in STRUCTURAL_REPAIR_TRANSPORT_KINDS
                and pre_repair_batch is not None
            ):
                from app.services.reader_journey_targeted_repair import (
                    JourneyEvidenceRepairPatchResult,
                    apply_evidence_patches,
                    is_repair_no_progress,
                )

                patch_result = JourneyEvidenceRepairPatchResult.model_validate_json(
                    parsed_json
                )
                allowed_paths = {
                    str(t.get("target_path"))
                    for t in (last_repair_context or {}).get("targets") or []
                    if isinstance(t, dict) and t.get("target_path")
                }
                result = apply_evidence_patches(
                    pre_repair_batch,  # type: ignore[arg-type]
                    patch_result,
                    paragraph_ids_by_scene=paragraph_ids_by_scene_cached,
                    allowed_paths=allowed_paths or None,
                    require_semantic_match=True,
                    input_snapshot=input_snapshot,
                )
                parsed_json = result.model_dump_json()
                if is_repair_no_progress(
                    pre_repair_batch,  # type: ignore[arg-type]
                    result,
                    paragraph_ids_by_scene_cached,
                ):
                    raise StructuralValidationError(
                        "structural repair made no progress on out-of-scope Evidence",
                        "JOURNEY_REPAIR_NO_PROGRESS",
                        failed_field="evidence_paragraph_ids",
                        repair_context=last_repair_context,
                        no_model_repair=True,
                    )
            else:
                if schema.__name__ == "SceneReaderJourneyBatchResult":
                    from app.services.reader_journey_evidence_compaction import (
                        build_compaction_repair_context,
                        normalize_batch_payload_evidence,
                        paragraph_ids_by_scene_from_snapshot,
                    )

                    payload = json.loads(parsed_json)
                    by_scene = paragraph_ids_by_scene_from_snapshot(input_snapshot)
                    if not by_scene and paragraph_ids_by_scene_cached:
                        by_scene = paragraph_ids_by_scene_cached
                    normalized, count_violations = normalize_batch_payload_evidence(
                        payload, by_scene
                    )
                    if count_violations:
                        paragraph_ids_by_scene_cached = by_scene
                        pre_repair_payload = normalized
                        ctx = build_compaction_repair_context(
                            payload=normalized,
                            violations=count_violations,
                            input_snapshot=input_snapshot,
                        )
                        last_repair_context = ctx
                        raise StructuralValidationError(
                            (
                                "evidence_paragraph_ids exceeds contract maxItems=16 "
                                f"after dedupe/scope filter "
                                f"(count={count_violations[0].get('count')})"
                            ),
                            "JOURNEY_EVIDENCE_COUNT_INVALID",
                            failed_field="evidence_paragraph_ids",
                            repair_context=ctx,
                        )
                    parsed_json = json.dumps(normalized, ensure_ascii=False)
                result = schema.model_validate_json(parsed_json)
            candidates = input_snapshot.get("transitions", [])
            decisions = getattr(result, "transitions", None) or getattr(
                result, "decisions", None
            )
            if isinstance(candidates, list) and decisions is not None:
                left_by_id = {
                    item.get("transition_id"): item.get("left_paragraph_id")
                    for item in candidates
                    if isinstance(item, dict)
                }

                def is_selected(item) -> bool:
                    return bool(
                        getattr(
                            item,
                            "boundary_decision",
                            getattr(
                                item,
                                "boundary",
                                getattr(item, "boundary_candidate", getattr(item, "accept", False)),
                            ),
                        )
                    )

                selected = list(
                    dict.fromkeys(
                        item.transition_id
                        for item in decisions
                        if is_selected(item)
                    )
                )
                transition_audit = {
                    "candidate_count": len(candidates),
                    "selected": selected,
                    "mapped": [left_by_id[item] for item in selected if item in left_by_id],
                    "rejected": list(
                        dict.fromkeys(
                            item.transition_id
                            for item in decisions
                            if not is_selected(item)
                        )
                    ),
                    "rejected_classifications": [
                        item.model_dump(mode="json")
                        for item in decisions
                        if not is_selected(item)
                    ],
                }
            business_validator(result)
            status = "succeeded"
            last_error = ""
        except OutputTruncatedError as exc:
            last_error = str(exc) or "模型输出被输出上限截断"
            last_error_code = exc.error_code
            last_category = "structured_output"
            last_retryable = True
            last_provider_error = None
            error_code = exc.error_code
            previous_raw = ""
            if not allow_truncation_retry:
                next_kind = "truncation_abort"
            else:
                next_kind = "truncation_retry"
            next_provider_name = authorized_provider
        except (StructuredOutputError, json.JSONDecodeError) as exc:
            last_error = str(exc) or "JSON解析失败"
            last_error_code = "JSON_PARSE_FAILED"
            last_category = "json_validation"
            last_retryable = True
            last_provider_error = None
            error_code = "VALIDATION_ERROR"
            previous_raw = raw
            next_kind = "json_repair"
            next_provider_name = authorized_provider
        except ValidationError as exc:
            last_error = str(exc) or "Schema校验失败"
            last_error_code = "SCHEMA_VALIDATION_FAILED"
            last_category = "schema_validation"
            last_retryable = True
            last_provider_error = None
            error_code = "SCHEMA_VALIDATION_FAILED"
            previous_raw = raw
            next_kind = "schema_repair"
            next_provider_name = authorized_provider
            # Safety net: evidence too_long → directed compaction, not full schema_repair.
            err_text = str(exc)
            if (
                schema.__name__ == "SceneReaderJourneyBatchResult"
                and "evidence_paragraph_ids" in err_text
                and ("too_long" in err_text or "at most 16" in err_text)
                and raw
                and not in_repair_phase
            ):
                try:
                    from app.services.reader_journey_evidence_compaction import (
                        build_compaction_repair_context,
                        normalize_batch_payload_evidence,
                        paragraph_ids_by_scene_from_snapshot,
                    )

                    payload = json.loads(extract_json_object(raw))
                    by_scene = paragraph_ids_by_scene_from_snapshot(input_snapshot)
                    normalized, count_violations = normalize_batch_payload_evidence(
                        payload, by_scene
                    )
                    if count_violations:
                        paragraph_ids_by_scene_cached = by_scene
                        pre_repair_payload = normalized
                        ctx = build_compaction_repair_context(
                            payload=normalized,
                            violations=count_violations,
                            input_snapshot=input_snapshot,
                        )
                        last_repair_context = ctx
                        last_error_code = "JOURNEY_EVIDENCE_COUNT_INVALID"
                        error_code = "JOURNEY_EVIDENCE_COUNT_INVALID"
                        last_category = "structural_validation"
                        primary_error = "JOURNEY_EVIDENCE_COUNT_INVALID"
                        primary_error_message = last_error
                        next_kind = "structural_repair"
                except Exception:
                    pass
        except StructuralValidationError as exc:
            last_error = str(exc) or "结构覆盖校验失败"
            error_code = exc.error_code
            last_error_code = exc.error_code
            last_category = "structural_validation"
            last_retryable = not exc.no_model_repair
            last_provider_error = None
            previous_raw = raw
            validation_audit = {
                "validation_error_code": exc.error_code,
                "failed_field": exc.failed_field,
                "contract_version": contract_version,
            }
            if getattr(exc, "repair_context", None):
                last_repair_context = dict(exc.repair_context or {})
                validation_audit["repair_context_present"] = True
            if primary_error is None or primary_error in {
                "JOURNEY_REPAIR_NO_PROGRESS",
                "JOURNEY_EVIDENCE_COMPACTION_NO_PROGRESS",
            }:
                if exc.error_code not in {
                    "JOURNEY_REPAIR_NO_PROGRESS",
                    "JOURNEY_EVIDENCE_COMPACTION_NO_PROGRESS",
                }:
                    primary_error = exc.error_code
                    primary_error_message = last_error
                elif primary_error is None:
                    primary_error = "JOURNEY_EVIDENCE_OUT_OF_SCOPE"
                    primary_error_message = last_error
            # Capture pre-repair batch for targeted Evidence patching.
            if (
                exc.error_code == "JOURNEY_EVIDENCE_OUT_OF_SCOPE"
                and schema.__name__ == "SceneReaderJourneyBatchResult"
                and raw
                and not in_repair_phase
            ):
                try:
                    from app.services.reader_journey_targeted_repair import (
                        build_targeted_repair_context,
                    )

                    pre_repair_batch = schema.model_validate_json(extract_json_object(raw))
                    paragraph_ids_by_scene_cached = {}
                    for item in input_snapshot.get("profiles_target") or []:
                        if not isinstance(item, dict) or item.get("scene_id") is None:
                            continue
                        sid = int(item["scene_id"])
                        ids = {
                            str(p["id"])
                            for p in (item.get("paragraphs") or [])
                            if isinstance(p, dict) and p.get("id")
                        }
                        paragraph_ids_by_scene_cached[sid] = ids
                    ctx = last_repair_context or {}
                    if ctx.get("allowed_evidence_ids") and ctx.get("target_scene_id") is not None:
                        sid = int(ctx["target_scene_id"])
                        paragraph_ids_by_scene_cached.setdefault(
                            sid, set(map(str, ctx.get("allowed_evidence_ids") or []))
                        )
                    # Merge oos_nodes scene allow-lists from multi-profile validation.
                    if paragraph_ids_by_scene_cached:
                        last_repair_context = build_targeted_repair_context(
                            result=pre_repair_batch,
                            paragraph_ids_by_scene=paragraph_ids_by_scene_cached,
                            input_snapshot=input_snapshot,
                            primary_error="JOURNEY_EVIDENCE_OUT_OF_SCOPE",
                        )
                except Exception:
                    pass
            if exc.error_code in {
                "JOURNEY_REPAIR_NO_PROGRESS",
                "JOURNEY_EVIDENCE_COMPACTION_NO_PROGRESS",
                "JOURNEY_EVIDENCE_COMPACTION_INVALID",
                "JOURNEY_EVIDENCE_COMPACTION_OUTPUT_TRUNCATED",
            }:
                next_kind = "validation_abort"
                last_retryable = False
            elif exc.no_model_repair or exc.error_code == "JOURNEY_CONTRACT_VALIDATION_CONFLICT":
                next_kind = "validation_abort"
                last_retryable = False
            elif in_repair_phase and invocation_kind in STRUCTURAL_REPAIR_TRANSPORT_KINDS:
                next_kind = "validation_abort"
                validation_audit["repeated_same_error"] = (
                    previous_validation_error_code == exc.error_code
                )
                validation_audit["repair_trigger_error_code"] = primary_error
                last_retryable = False
            elif (
                previous_validation_error_code
                and previous_validation_error_code == exc.error_code
                and invocation_kind in STRUCTURAL_REPAIR_KINDS
            ):
                next_kind = "validation_abort"
                validation_audit["repeated_same_error"] = True
                validation_audit["repair_trigger_error_code"] = previous_validation_error_code
                last_retryable = False
            else:
                next_kind = "structural_repair"
            previous_validation_error_code = exc.error_code
            next_provider_name = authorized_provider
        except ValueError as exc:
            last_error = str(exc) or "业务校验失败"
            from app.services.scene_pipeline import is_evidence_paragraph_validation_error

            evidence_error = is_evidence_paragraph_validation_error(last_error)
            error_code = (
                "EVIDENCE_VALIDATION_ERROR" if evidence_error else "BUSINESS_VALIDATION_ERROR"
            )
            last_error_code = (
                "EVIDENCE_VALIDATION_FAILED" if evidence_error else "BUSINESS_VALIDATION_FAILED"
            )
            last_category = "evidence_validation" if evidence_error else "business_validation"
            last_retryable = True if evidence_error else False
            last_provider_error = None
            previous_raw = raw
            repair_kind = "evidence_repair" if evidence_error else "business_repair"
            if primary_error is None:
                primary_error = last_error_code
                primary_error_message = last_error
            if in_repair_phase and invocation_kind in STRUCTURAL_REPAIR_TRANSPORT_KINDS:
                next_kind = "validation_abort"
                validation_audit = {
                    "validation_error_code": last_error_code,
                    "repeated_same_error": previous_validation_error_code == last_error_code,
                    "repair_trigger_error_code": primary_error,
                    "contract_version": contract_version,
                }
                last_retryable = False
            elif (
                previous_validation_error_code
                and previous_validation_error_code == last_error_code
                and invocation_kind in STRUCTURAL_REPAIR_KINDS
            ):
                next_kind = "validation_abort"
                validation_audit = {
                    "validation_error_code": last_error_code,
                    "repeated_same_error": True,
                    "repair_trigger_error_code": previous_validation_error_code,
                    "contract_version": contract_version,
                }
                last_retryable = False
            else:
                next_kind = repair_kind
            previous_validation_error_code = last_error_code
            next_provider_name = authorized_provider
        except RequestBlockedError:
            settle_cloud_attempt_usage(
                session,
                budget_claim,
                http_request_sent=False,
                total_tokens=None,
                estimated_cost=None,
            )
            session.rollback()
            raise
        except ModelInvocationPolicyError as exc:
            last_provider_error = exc.to_provider_error()
            last_error = str(exc)
            last_error_code = exc.error_code
            last_category = "model_invocation_policy"
            last_retryable = False
            error_code = exc.error_code
            http_request_sent = False
            next_kind = "provider_abort"
            next_provider_name = authorized_provider
            # Audit the attempted (requested) provider when fallback was blocked.
            if exc.requested_provider:
                invocation_provider_name = exc.requested_provider
            response_model = exc.requested_model or authorized_model
            validation_audit = {
                **validation_audit,
                **{
                    key: value
                    for key, value in exc.as_safe_dict().items()
                    if key
                    in {
                        "invocation_type",
                        "requested_provider",
                        "requested_model",
                        "resolved_provider",
                        "resolved_model",
                        "route_source",
                        "auto_route",
                        "fallback_used",
                    }
                },
            }
        except ProviderRequestError as exc:
            last_provider_error = exc
            last_error = str(exc)
            last_error_code = exc.error_code
            last_category = "provider_request"
            last_retryable = should_retry_provider_error(exc)
            error_code = exc.error_code or "PROVIDER_ERROR"
            http_status_code = exc.http_status_code
            http_request_sent = exc.http_request_sent
            if in_repair_phase or invocation_kind in STRUCTURAL_REPAIR_TRANSPORT_KINDS:
                next_kind = (
                    "repair_provider_retry" if last_retryable else "provider_abort"
                )
            else:
                next_kind = "provider_retry" if last_retryable else "provider_abort"
            next_provider_name = invocation_provider_name
        except Exception as exc:
            wrapped = ProviderRequestError(
                str(exc) or type(exc).__name__,
                http_request_sent=False,
                error_code="PROVIDER_TRANSPORT_ERROR",
                exception_type=type(exc).__name__,
                provider=invocation_provider_name,
                model=invocation_provider.default_model,
                phase="provider_request",
                retryable=True,
                original_exception_type=type(exc).__name__,
            )
            last_provider_error = wrapped
            last_error = str(wrapped)
            last_error_code = wrapped.error_code
            last_category = "provider_request"
            last_retryable = True
            error_code = wrapped.error_code
            if in_repair_phase or invocation_kind in STRUCTURAL_REPAIR_TRANSPORT_KINDS:
                next_kind = "repair_provider_retry"
            else:
                next_kind = "provider_retry"
            next_provider_name = invocation_provider_name
        latency = int((time.perf_counter() - started) * 1000)
        request_json = request.model_dump_json()
        request_hash_value = hashlib.sha256(request_json.encode()).hexdigest()
        snapshot_json = json.dumps(input_snapshot, ensure_ascii=False)
        content_digest = hashlib.sha256(snapshot_json.encode()).hexdigest()
        estimated_cost, currency, pricing_version = estimate_cost(
            response_model or invocation_provider.default_model,
            input_tokens,
            output_tokens,
            Path("config/cloud_pricing.json"),
        )
        settle_cloud_attempt_usage(
            session,
            budget_claim,
            http_request_sent=http_request_sent,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
        )
        raw_logging = get_settings().cloud_raw_logging if invocation_capabilities.cloud else True
        stored_snapshot = snapshot_json
        stored_raw = raw
        if invocation_capabilities.cloud and not raw_logging:
            paragraph_ids = [
                item.get("id")
                for item in input_snapshot.get("paragraphs", [])
                if isinstance(item, dict) and item.get("id")
            ]
            stored_snapshot = json.dumps(
                {
                    "content_hash": content_digest,
                    "paragraph_ids": paragraph_ids,
                    "character_count": len(snapshot_json),
                },
                ensure_ascii=False,
            )
            stored_raw = ""
        request_params = {
            "temperature": request.temperature,
            "max_output_tokens": request.max_output_tokens,
            "configured_limit": output_limit.configured_limit,
            "user_hard_limit": output_limit.user_hard_limit,
            "effective_limit": output_limit.effective_limit,
            "provider_parameter_name": output_limit.provider_parameter_name,
            "response_format_mode": request.response_format_mode,
            "enable_thinking": request.enable_thinking,
            "normal_transport_used": normal_transport_used,
            "repair_transport_used": repair_transport_used,
            "repair_rounds_used": repair_rounds_used,
            "in_repair_phase": in_repair_phase,
            "request_hash": request_hash_value,
        }
        if primary_error is not None:
            request_params["primary_error"] = primary_error
        if validation_audit:
            request_params.update(validation_audit)
        session.add(
            ModelInvocation(
                run_id=run_id,
                task_type=task_type,
                provider_name=invocation_provider_name,
                model_name=(
                    (resolved_invocation.resolved_model if resolved_invocation else None)
                    or request.model
                    or response_model
                    or invocation_provider.default_model
                ),
                prompt_version=prompt.version,
                schema_version="v1",
                attempt_no=attempt_no,
                invocation_kind=invocation_kind,
                request_hash=request_hash_value,
                input_snapshot_json=stored_snapshot,
                raw_response_text=stored_raw,
                parsed_response_json=parsed_json,
                status=status,
                latency_ms=latency,
                http_status_code=http_status_code,
                response_model_name=response_model,
                structured_output_mode=request.response_format_mode,
                schema_hash=schema_hash(request.response_schema),
                grammar_hash=(
                    grammar_hash(schema_to_gbnf(request.response_schema))
                    if request.response_format_mode == "grammar"
                    else None
                ),
                thinking_enabled=False,
                thinking_control_method="chat_template_kwargs.enable_thinking",
                request_parameters_json=json.dumps(
                    request_params,
                    sort_keys=True,
                ),
                is_cloud=invocation_capabilities.cloud,
                cloud_provider=(
                    invocation_capabilities.provider_family
                    if invocation_capabilities.cloud
                    else None
                ),
                cloud_region=invocation_capabilities.region,
                sends_content_to_cloud=invocation_capabilities.sends_content_to_cloud,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cached_tokens=cached_tokens,
                request_id=request_id,
                estimated_cost=estimated_cost,
                currency=currency,
                pricing_version=pricing_version,
                raw_logging_enabled=raw_logging,
                content_hash=content_digest,
                error_code=error_code,
                error_message=(last_error or error_code or "PROVIDER_ERROR"),
                http_request_sent=http_request_sent,
                audit_type=(
                    "provider_invocation" if http_request_sent else "pre_send_failure"
                ),
                sent_at=datetime.now(timezone.utc) if http_request_sent else None,
                requested_output_tokens=output_limit.effective_limit,
                actual_output_tokens=output_tokens,
                provider_parameter_name=output_limit.provider_parameter_name,
                finish_reason=finish_reason,
                candidate_transition_count=transition_audit.get("candidate_count"),
                selected_transition_ids_json=(
                    json.dumps(transition_audit.get("selected", []))
                    if transition_audit
                    else None
                ),
                mapped_after_paragraph_ids_json=(
                    json.dumps(transition_audit.get("mapped", []))
                    if transition_audit
                    else None
                ),
                rejected_transition_ids_json=(
                    json.dumps(transition_audit.get("rejected", []))
                    if transition_audit
                    else None
                ),
                rejected_transition_classifications_json=(
                    json.dumps(transition_audit.get("rejected_classifications", []))
                    if transition_audit
                    else None
                ),
                transition_contract_version=(
                    "3.5"
                    if schema.__name__ == "CompactTransitionClassificationResultV35"
                    else (
                        "3.4"
                        if schema.__name__ == "CompactTransitionClassificationResultV34"
                        else (
                            "3.3"
                            if schema.__name__ == "CompactTransitionClassificationResult"
                            else (
                                "1.0"
                                if schema.__name__ == "BoundaryCandidateAdjudicationResult"
                                else ("v1" if transition_audit else None)
                            )
                        )
                    )
                ),
                canonical_schema_hash=(
                    schema_hash(SceneBoundaryResult.model_json_schema())
                    if schema.__name__
                    in {
                        "CompactTransitionClassificationResult",
                        "CompactTransitionClassificationResultV34",
                        "CompactTransitionClassificationResultV35",
                        "BoundaryCandidateAdjudicationResult",
                    }
                    else None
                ),
            )
        )
        session.commit()
        if status != "succeeded":
            latest = (
                session.query(ModelInvocation)
                .filter_by(run_id=run_id)
                .order_by(ModelInvocation.id.desc())
                .first()
            )
            last_invocation_id = latest.id if latest else last_invocation_id
        if status == "succeeded":
            return result
        if next_kind in {"truncation_abort", "validation_abort", "provider_abort"}:
            break
        if next_kind == "provider_retry":
            if not should_retry_provider_error(last_provider_error):
                break
            if normal_transport_used >= max_normal_transport:
                break
        if next_kind == "repair_provider_retry":
            if not should_retry_provider_error(last_provider_error):
                break
            if repair_transport_used >= max_repair_transport:
                break

    journey_final: str | None = None
    _compaction_final_codes = {
        "JOURNEY_EVIDENCE_COMPACTION_OUTPUT_TRUNCATED",
        "JOURNEY_EVIDENCE_COMPACTION_NO_PROGRESS",
        "JOURNEY_EVIDENCE_COMPACTION_INVALID",
        "JOURNEY_EVIDENCE_COUNT_INVALID",
    }
    if last_error_code in POLICY_ERROR_CODES or last_category == "model_invocation_policy":
        journey_final = None
    elif last_error_code == "JOURNEY_REPAIR_NO_PROGRESS":
        journey_final = "JOURNEY_REPAIR_NO_PROGRESS"
    elif last_error_code in _compaction_final_codes:
        # DEFECT-016: keep directed Evidence compaction codes (do not wrap).
        journey_final = last_error_code
    elif in_repair_phase and primary_error and str(primary_error).startswith("JOURNEY_"):
        if last_category == "provider_request" or last_provider_error is not None:
            journey_final = "JOURNEY_REPAIR_PROVIDER_FAILURE"
        else:
            journey_final = "JOURNEY_REPAIR_VALIDATION_FAILED"

    final_code = journey_final or last_error_code
    final_message = last_error or (str(last_provider_error) if last_provider_error else None)
    if journey_final == "JOURNEY_REPAIR_PROVIDER_FAILURE" and primary_error_message:
        final_message = (
            f"structural repair transport exhausted after {primary_error}: "
            f"{primary_error_message}; transport={last_error_code}"
        )
    elif journey_final == "JOURNEY_REPAIR_NO_PROGRESS" and primary_error_message:
        final_message = (
            f"structural repair made no progress after {primary_error}: "
            f"{last_error or primary_error_message}"
        )
    elif journey_final == "JOURNEY_REPAIR_VALIDATION_FAILED" and primary_error_message:
        final_message = (
            f"structural repair still violates contract after {primary_error}: "
            f"{last_error or primary_error_message}"
        )

    raise StructuredOutputError(
        final_message,
        final_code,
        category=last_category if journey_final is None else "journey_repair",
        retryable=False if journey_final else last_retryable,
        provider_error=last_provider_error,
        failed_invocation_id=last_invocation_id,
        primary_error=primary_error,
        transport_error=(
            last_error_code
            if journey_final == "JOURNEY_REPAIR_PROVIDER_FAILURE"
            else None
        ),
    ) from last_provider_error
