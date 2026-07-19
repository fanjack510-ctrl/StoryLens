# -*- coding: utf-8 -*-
"""Global model invocation policy (DEFECT-CANARY-015 / change v1.1.0).

All production model calls must resolve provider/model through this broker
before any HTTP request is sent. Nested repair/retry/recovery inherit the
frozen AnalysisRun policy; ``auto_route=false`` forbids Flash fallback.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, ProviderConfiguration
from app.model_gateway.base import ModelRequest, ModelResponse, ProviderRequestError
from app.model_gateway.gateway import ModelGateway

# Canonical production invocation types (must stay registered for the offline gate).
REGISTERED_INVOCATION_TYPES = frozenset(
    {
        "scene_boundary",
        "scene_boundary_schema_repair",
        "scene_analysis",
        "scene_analysis_provider_retry",
        "scene_analysis_provider_recovery",
        "reader_journey_scene_batch",
        "reader_journey_scene_schema_repair",
        "reader_journey_structural_repair",
        "reader_journey_targeted_evidence_patch",
        "reader_journey_chapter",
        "reader_journey_chapter_schema_repair",
        "repair_provider_retry",
        "generic_provider_retry",
        # Internal kinds still used by generate_validated envelopes:
        "initial",
        "json_repair",
        "schema_repair",
        "structural_repair",
        "evidence_repair",
        "business_repair",
        "truncation_retry",
        "provider_retry",
        "normal_batch_request",
        "split_batch_request",
        "boundary_candidate_detection",
        "boundary_candidate_adjudication",
    }
)

ERROR_POLICY_VIOLATION = "MODEL_INVOCATION_POLICY_VIOLATION"
ERROR_PROVIDER_DISABLED_PRECHECK = "MODEL_PROVIDER_DISABLED_PRECHECK"
ERROR_UNAUTHORIZED_FALLBACK = "MODEL_UNAUTHORIZED_FALLBACK"
ERROR_TYPE_UNREGISTERED = "MODEL_INVOCATION_TYPE_UNREGISTERED"

POLICY_ERROR_CODES = frozenset(
    {
        ERROR_POLICY_VIOLATION,
        ERROR_PROVIDER_DISABLED_PRECHECK,
        ERROR_UNAUTHORIZED_FALLBACK,
        ERROR_TYPE_UNREGISTERED,
    }
)

# Providers that historically appeared as silent repair fallbacks.
KNOWN_FALLBACK_PROVIDERS = frozenset({"aliyun_qwen_flash", "aliyun_qwen_max"})


@dataclass(frozen=True)
class RunModelPolicy:
    authorized_provider: str
    authorized_model: str
    auto_route: bool = False
    fallback_policy: str = "none"
    source: str = "analysis_run"


@dataclass(frozen=True)
class ResolvedInvocation:
    invocation_type: str
    caller: str
    requested_provider: str
    requested_model: str
    resolved_provider: str
    resolved_model: str
    route_source: str
    fallback_used: bool
    auto_route: bool
    provider_enabled: bool
    policy_match: bool
    request_hash_policy: str = "independent_of_model_policy"

    def as_audit_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelInvocationPolicyError(Exception):
    """Raised before any provider HTTP send when policy resolution fails."""

    message: str
    error_code: str
    invocation_type: str | None = None
    requested_provider: str | None = None
    requested_model: str | None = None
    resolved_provider: str | None = None
    resolved_model: str | None = None
    route_source: str | None = None
    auto_route: bool | None = None
    fallback_used: bool | None = None
    retryable: bool = False
    category: str = "model_invocation_policy"
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def as_safe_dict(self) -> dict[str, Any]:
        payload = {
            "error_code": self.error_code,
            "message": self.message,
            "category": self.category,
            "retryable": self.retryable,
            "invocation_type": self.invocation_type,
            "requested_provider": self.requested_provider,
            "requested_model": self.requested_model,
            "resolved_provider": self.resolved_provider,
            "resolved_model": self.resolved_model,
            "route_source": self.route_source,
            "auto_route": self.auto_route,
            "fallback_used": self.fallback_used,
        }
        if self.details:
            # Never attach secrets; only allow non-sensitive diagnostic keys.
            safe_keys = {
                "caller",
                "provider_enabled",
                "policy_match",
                "fallback_policy",
                "authorized_provider",
                "authorized_model",
            }
            payload["details"] = {
                key: value for key, value in self.details.items() if key in safe_keys
            }
        return payload

    def to_provider_error(self) -> ProviderRequestError:
        return ProviderRequestError(
            self.message,
            http_request_sent=False,
            error_code=self.error_code,
            exception_type="ModelInvocationPolicyError",
            provider=self.resolved_provider or self.requested_provider,
            model=self.resolved_model or self.requested_model,
            phase="pre_send",
            retryable=False,
            safe_details=self.as_safe_dict(),
            user_action_hint="检查 AnalysisRun 冻结的 Provider/Model 策略；禁止未授权 Fallback",
        )


def map_invocation_type(
    task_type: str,
    invocation_kind: str,
    *,
    targeted_evidence_repair: bool = False,
) -> str:
    """Map (task_type, invocation_kind) onto a registered policy type."""
    kind = (invocation_kind or "initial").strip()
    task = (task_type or "").strip()

    if kind == "repair_provider_retry":
        return "repair_provider_retry"
    if kind == "provider_retry":
        if task == "scene_analysis":
            return "scene_analysis_provider_retry"
        return "generic_provider_retry"

    if targeted_evidence_repair or (
        kind in {"structural_repair", "evidence_repair"}
        and task.startswith("reader_journey")
        and "targeted" in kind
    ):
        if targeted_evidence_repair and task.startswith("reader_journey"):
            return "reader_journey_targeted_evidence_patch"

    if task == "scene_boundary" or task.startswith("scene_boundary"):
        if kind == "schema_repair":
            return "scene_boundary_schema_repair"
        return "scene_boundary" if kind in {"initial", "truncation_retry"} else kind

    if task == "scene_analysis":
        if kind in {"initial", "truncation_retry"}:
            return "scene_analysis"
        if kind == "schema_repair":
            return "schema_repair"
        return kind

    if task.startswith("reader_journey_scene") or task == "reader_journey_scene":
        if targeted_evidence_repair:
            return "reader_journey_targeted_evidence_patch"
        if kind == "schema_repair":
            return "reader_journey_scene_schema_repair"
        if kind in {"structural_repair", "evidence_repair", "business_repair"}:
            return "reader_journey_structural_repair"
        if kind in {"normal_batch_request", "split_batch_request", "initial"}:
            return "reader_journey_scene_batch"
        return kind

    if task.startswith("reader_journey_chapter") or task == "reader_journey_chapter":
        if kind == "schema_repair":
            return "reader_journey_chapter_schema_repair"
        if kind in {"initial", "normal_batch_request"}:
            return "reader_journey_chapter"
        return kind

    # Boundary pipeline / other tasks keep the raw kind when already registered.
    if kind in REGISTERED_INVOCATION_TYPES:
        return kind
    if task in REGISTERED_INVOCATION_TYPES:
        return task
    return kind or task or "initial"


def load_run_model_policy(
    session: Session,
    run_id: int,
    *,
    fallback_provider: str | None = None,
    fallback_model: str | None = None,
) -> RunModelPolicy:
    run = session.get(AnalysisRun, int(run_id)) if run_id else None
    if run is not None:
        provider = str(run.provider)
        model = str(run.model)
        row = session.scalar(
            select(ProviderConfiguration).where(
                ProviderConfiguration.provider_name == provider
            )
        )
        auto_route = bool(row.allow_auto_route) if row is not None else False
        return RunModelPolicy(
            authorized_provider=provider,
            authorized_model=model,
            auto_route=auto_route,
            fallback_policy="none" if not auto_route else "authorized_only",
            source="analysis_run",
        )
    provider = fallback_provider or "unknown"
    model = fallback_model or ""
    return RunModelPolicy(
        authorized_provider=provider,
        authorized_model=model,
        auto_route=False,
        fallback_policy="none",
        source="caller_fallback",
    )


class ModelInvocationBroker:
    """Single policy entry for production model invocations."""

    def resolve(
        self,
        *,
        run_id: int,
        invocation_type: str,
        authorized_provider: str,
        authorized_model: str,
        auto_route: bool,
        requested_provider: str | None = None,
        requested_model: str | None = None,
        gateway: ModelGateway | None = None,
        fallback_policy: str = "none",
        caller: str = "structured_output.generate_validated",
        repair_context: dict[str, Any] | None = None,
    ) -> ResolvedInvocation:
        del repair_context  # reserved for future budget/repair audits
        if invocation_type not in REGISTERED_INVOCATION_TYPES:
            raise ModelInvocationPolicyError(
                f"未注册的模型调用类型: {invocation_type}",
                ERROR_TYPE_UNREGISTERED,
                invocation_type=invocation_type,
                requested_provider=requested_provider,
                requested_model=requested_model,
                route_source="unregistered",
                auto_route=auto_route,
                fallback_used=False,
                details={"caller": caller},
            )

        req_provider = (requested_provider or authorized_provider).strip()
        req_model = (requested_model or authorized_model).strip()
        auth_provider = authorized_provider.strip()
        auth_model = authorized_model.strip()

        # Default: inherit frozen run policy (no silent re-route).
        resolved_provider = auth_provider
        resolved_model = auth_model
        route_source = "run_frozen_policy"
        fallback_used = False

        if not auto_route or fallback_policy == "none":
            if req_provider != auth_provider or req_model != auth_model:
                code = (
                    ERROR_UNAUTHORIZED_FALLBACK
                    if req_provider in KNOWN_FALLBACK_PROVIDERS
                    or req_provider != auth_provider
                    else ERROR_POLICY_VIOLATION
                )
                raise ModelInvocationPolicyError(
                    (
                        "模型调用策略违规：auto_route=false 时禁止偏离授权 Provider/Model "
                        f"(requested={req_provider}/{req_model}, "
                        f"authorized={auth_provider}/{auth_model})"
                    ),
                    code if code == ERROR_UNAUTHORIZED_FALLBACK else ERROR_POLICY_VIOLATION,
                    invocation_type=invocation_type,
                    requested_provider=req_provider,
                    requested_model=req_model,
                    resolved_provider=auth_provider,
                    resolved_model=auth_model,
                    route_source="rejected_fallback",
                    auto_route=False,
                    fallback_used=True,
                    details={
                        "caller": caller,
                        "authorized_provider": auth_provider,
                        "authorized_model": auth_model,
                        "fallback_policy": fallback_policy,
                    },
                )
            resolved_provider = auth_provider
            resolved_model = auth_model
            route_source = "run_frozen_policy"
            fallback_used = False
        else:
            # auto_route=true still does not invent Flash; keep authorized unless
            # an explicit same-family override is requested and enabled.
            if req_provider != auth_provider:
                raise ModelInvocationPolicyError(
                    "模型调用策略违规：未授权的 Provider Fallback",
                    ERROR_UNAUTHORIZED_FALLBACK,
                    invocation_type=invocation_type,
                    requested_provider=req_provider,
                    requested_model=req_model,
                    resolved_provider=auth_provider,
                    resolved_model=auth_model,
                    route_source="rejected_fallback",
                    auto_route=True,
                    fallback_used=True,
                    details={"caller": caller},
                )
            resolved_provider = req_provider
            resolved_model = req_model or auth_model
            route_source = "authorized_direct"
            fallback_used = False

        provider_enabled = True
        if gateway is not None:
            try:
                provider = gateway.get(resolved_provider)
            except Exception as exc:  # noqa: BLE001 — treat missing provider as disabled
                raise ModelInvocationPolicyError(
                    f"Provider 不可用: {resolved_provider}",
                    ERROR_PROVIDER_DISABLED_PRECHECK,
                    invocation_type=invocation_type,
                    requested_provider=req_provider,
                    requested_model=req_model,
                    resolved_provider=resolved_provider,
                    resolved_model=resolved_model,
                    route_source=route_source,
                    auto_route=auto_route,
                    fallback_used=fallback_used,
                    details={"caller": caller, "provider_enabled": False},
                ) from exc
            provider_enabled = bool(provider.capabilities().enabled)
            if not provider_enabled:
                raise ModelInvocationPolicyError(
                    f"Provider已停用，拒绝发送请求: {resolved_provider}",
                    ERROR_PROVIDER_DISABLED_PRECHECK,
                    invocation_type=invocation_type,
                    requested_provider=req_provider,
                    requested_model=req_model,
                    resolved_provider=resolved_provider,
                    resolved_model=resolved_model,
                    route_source=route_source,
                    auto_route=auto_route,
                    fallback_used=fallback_used,
                    details={"caller": caller, "provider_enabled": False},
                )

        policy_match = (
            resolved_provider == auth_provider
            and resolved_model == auth_model
            and fallback_used is False
        )
        if not auto_route and not policy_match:
            raise ModelInvocationPolicyError(
                "模型调用策略违规：resolved 与 authorized 不一致",
                ERROR_POLICY_VIOLATION,
                invocation_type=invocation_type,
                requested_provider=req_provider,
                requested_model=req_model,
                resolved_provider=resolved_provider,
                resolved_model=resolved_model,
                route_source=route_source,
                auto_route=False,
                fallback_used=fallback_used,
                details={"caller": caller, "policy_match": False},
            )

        return ResolvedInvocation(
            invocation_type=invocation_type,
            caller=caller,
            requested_provider=req_provider,
            requested_model=req_model,
            resolved_provider=resolved_provider,
            resolved_model=resolved_model,
            route_source=route_source,
            fallback_used=fallback_used,
            auto_route=bool(auto_route),
            provider_enabled=provider_enabled,
            policy_match=policy_match,
            request_hash_policy="independent_of_model_policy",
        )

    async def invoke(
        self,
        *,
        gateway: ModelGateway,
        resolved: ResolvedInvocation,
        request: ModelRequest,
    ) -> ModelResponse:
        """Send only after resolve(); stamps authorized model onto the request."""
        stamped = request.model_copy(
            update={"model": resolved.resolved_model or request.model}
        )
        return await gateway.generate(resolved.resolved_provider, stamped)


def resolve_for_offline_graph(
    *,
    invocation_type: str,
    authorized_provider: str = "aliyun_qwen_plus",
    authorized_model: str = "qwen3.7-plus",
    auto_route: bool = False,
    requested_provider: str | None = None,
    requested_model: str | None = None,
    provider_enabled: bool = True,
    caller: str = "offline_graph",
) -> dict[str, Any]:
    """Deterministic offline resolution used by audits / gates (no HTTP)."""
    broker = ModelInvocationBroker()
    try:
        # Build a tiny stub gateway only when we need enabled checks.
        if provider_enabled and (
            requested_provider in (None, authorized_provider)
            and (requested_model in (None, authorized_model))
        ):
            resolved = broker.resolve(
                run_id=0,
                invocation_type=invocation_type,
                authorized_provider=authorized_provider,
                authorized_model=authorized_model,
                auto_route=auto_route,
                requested_provider=requested_provider or authorized_provider,
                requested_model=requested_model or authorized_model,
                gateway=None,
                fallback_policy="none" if not auto_route else "authorized_only",
                caller=caller,
            )
            payload = resolved.as_audit_dict()
            payload["provider_enabled"] = provider_enabled
            payload["error_code"] = None
            return payload
        resolved = broker.resolve(
            run_id=0,
            invocation_type=invocation_type,
            authorized_provider=authorized_provider,
            authorized_model=authorized_model,
            auto_route=auto_route,
            requested_provider=requested_provider or authorized_provider,
            requested_model=requested_model or authorized_model,
            gateway=None,
            fallback_policy="none" if not auto_route else "authorized_only",
            caller=caller,
        )
        if not provider_enabled:
            raise ModelInvocationPolicyError(
                f"Provider已停用，拒绝发送请求: {resolved.resolved_provider}",
                ERROR_PROVIDER_DISABLED_PRECHECK,
                invocation_type=invocation_type,
                requested_provider=resolved.requested_provider,
                requested_model=resolved.requested_model,
                resolved_provider=resolved.resolved_provider,
                resolved_model=resolved.resolved_model,
                route_source=resolved.route_source,
                auto_route=auto_route,
                fallback_used=resolved.fallback_used,
            )
        payload = resolved.as_audit_dict()
        payload["error_code"] = None
        return payload
    except ModelInvocationPolicyError as exc:
        return {
            "invocation_type": invocation_type,
            "caller": caller,
            "requested_provider": exc.requested_provider,
            "requested_model": exc.requested_model,
            "resolved_provider": exc.resolved_provider,
            "resolved_model": exc.resolved_model,
            "route_source": exc.route_source,
            "fallback_used": exc.fallback_used,
            "auto_route": exc.auto_route,
            "provider_enabled": provider_enabled,
            "policy_match": False,
            "request_hash_policy": "independent_of_model_policy",
            "error_code": exc.error_code,
        }


# Module-level singleton used by production call sites.
broker = ModelInvocationBroker()
