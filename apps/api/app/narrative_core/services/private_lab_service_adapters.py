"""Map Agent V Private Lab Ports → Agent U formal services (Phase 2B-R1 Integration).

No second estimate/consent/manifest stack. Fake Ports remain for unit tests only.
Credentials never appear in DTOs or logs. Provider bodies stay process-local.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Book, BookSnapshot
from app.narrative_core.enums import SnapshotStatus
from app.narrative_core.private_engine_contract.provider_input import (
    ProviderInputBundle,
    ResolvedProviderPayload,
)
from app.narrative_core.run_shell_contract.private_engine_lab import (
    PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER,
    PRIVATE_LAB_FIRST_MODEL_ID,
    PRIVATE_LAB_FIRST_PROVIDER_KEY,
    WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
)
from app.narrative_core.services.private_engine_lab_authorization_service import (
    is_private_provider_live_probe_enabled,
)
from app.narrative_core.services.provider_execution_authorization import (
    ProviderExecutionAuthorization,
    compute_provider_execution_authorization,
)
from app.narrative_core.services.data_transfer_consent_guard import (
    PrivateEngineDataTransferConsentGuard,
    PrivateEngineProviderBudgetGuard,
)
from app.narrative_core.services.private_lab_ports import (
    PrivateLabConsentResult,
    PrivateLabEstimateResult,
    PrivateLabPreflightResult,
    PrivateLabProviderUsageResult,
)
from app.narrative_core.services.provider_input_bundle_resolver import (
    FakeProviderInputBundleResolver,
)
from app.narrative_core.services.whole_book_provider_estimate_service import (
    WholeBookProviderEstimateService,
)
from app.narrative_core.services.whole_book_provider_gateway import (
    CapturingProviderTransport,
    ExistingCredentialServiceAdapter,
    NoCredentialFakeResolver,
    StubTransportResponse,
    create_lab_provider_gateway,
)


def _fingerprint(parts: Mapping[str, Any]) -> str:
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class ServerSecurityStatus:
    """Server-resolved security gates — never trust client booleans alone."""

    credential_present: bool
    budget_ok: bool
    capability_ok: bool
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class PrivateLabPreflightServiceAdapter:
    """PrivateLabPreflightPort → snapshot/env/module/route checks (+ U foundation)."""

    session: Session | None = None
    environment: str = "test"
    lab_enabled: bool = True
    credential_status_fn: Callable[[str], bool] | None = None
    capability_ok_fn: Callable[[], bool] | None = None

    def preflight(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        configuration_fingerprint: str,
        requested_modules: tuple[str, ...],
    ) -> PrivateLabPreflightResult:
        details: dict[str, Any] = {
            "creates_analysis_run": False,
            "writes_candidate": False,
            "calls_provider": False,
            "environment": self.environment,
            "lab_enabled": self.lab_enabled,
        }
        if self.environment not in {"development", "test"}:
            return PrivateLabPreflightResult(
                ok=False,
                fingerprint="",
                book_id=int(book_id),
                book_snapshot_id=int(book_snapshot_id),
                reason_code="ENVIRONMENT_NOT_ALLOWED",
                details=details,
            )
        if not self.lab_enabled:
            return PrivateLabPreflightResult(
                ok=False,
                fingerprint="",
                book_id=int(book_id),
                book_snapshot_id=int(book_snapshot_id),
                reason_code="PRIVATE_LAB_DISABLED",
                details=details,
            )
        _ = WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED  # documented default; adapter lab_enabled overrides for tests

        modules = tuple(str(m) for m in requested_modules) or PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER
        unknown = [m for m in modules if m not in PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER]
        if unknown:
            return PrivateLabPreflightResult(
                ok=False,
                fingerprint="",
                book_id=int(book_id),
                book_snapshot_id=int(book_snapshot_id),
                reason_code="MODULE_NOT_ALLOWED",
                details={**details, "unknown_modules": unknown},
            )

        snapshot_hash: str | None = None
        if self.session is not None:
            book = self.session.get(Book, int(book_id))
            if book is None:
                return PrivateLabPreflightResult(
                    ok=False,
                    fingerprint="",
                    book_id=int(book_id),
                    book_snapshot_id=int(book_snapshot_id),
                    reason_code="BOOK_NOT_FOUND",
                    details=details,
                )
            snapshot = self.session.get(BookSnapshot, int(book_snapshot_id))
            if snapshot is None or int(snapshot.book_id) != int(book_id):
                return PrivateLabPreflightResult(
                    ok=False,
                    fingerprint="",
                    book_id=int(book_id),
                    book_snapshot_id=int(book_snapshot_id),
                    reason_code="SNAPSHOT_NOT_BOUND",
                    details=details,
                )
            if str(snapshot.snapshot_status) != SnapshotStatus.COMPLETED.value:
                return PrivateLabPreflightResult(
                    ok=False,
                    fingerprint="",
                    book_id=int(book_id),
                    book_snapshot_id=int(book_snapshot_id),
                    reason_code="SNAPSHOT_NOT_COMPLETED",
                    details=details,
                )
            snapshot_hash = str(
                getattr(snapshot, "content_hash", None)
                or getattr(snapshot, "snapshot_hash", None)
                or f"snap:{snapshot.id}"
            )
            details["snapshot_status"] = str(snapshot.snapshot_status)

        capability_ok = True
        if self.capability_ok_fn is not None:
            capability_ok = bool(self.capability_ok_fn())
        details["capability_ok"] = capability_ok
        if not capability_ok:
            return PrivateLabPreflightResult(
                ok=False,
                fingerprint="",
                book_id=int(book_id),
                book_snapshot_id=int(book_snapshot_id),
                snapshot_content_hash=snapshot_hash,
                reason_code="CAPABILITY_DENIED",
                details=details,
            )

        credential_present = False
        if self.credential_status_fn is not None:
            credential_present = bool(self.credential_status_fn(PRIVATE_LAB_FIRST_PROVIDER_KEY))
        details["credential_present"] = credential_present
        details["provider_route"] = {
            "provider_key": PRIVATE_LAB_FIRST_PROVIDER_KEY,
            "model_id": PRIVATE_LAB_FIRST_MODEL_ID,
        }
        details["can_enter_estimate"] = True

        fp = _fingerprint(
            {
                "book_id": int(book_id),
                "book_snapshot_id": int(book_snapshot_id),
                "configuration_fingerprint": configuration_fingerprint,
                "modules": list(modules),
                "snapshot_content_hash": snapshot_hash,
                "schema": "private_lab_preflight.v1",
            }
        )
        return PrivateLabPreflightResult(
            ok=True,
            fingerprint=fp,
            book_id=int(book_id),
            book_snapshot_id=int(book_snapshot_id),
            snapshot_content_hash=snapshot_hash,
            reason_code=None,
            details=details,
        )


@dataclass
class PrivateLabEstimateServiceAdapter:
    """PrivateLabEstimatePort → WholeBookProviderEstimateService + Manifest builder."""

    resolver: Any = field(default_factory=FakeProviderInputBundleResolver)
    estimate_service: WholeBookProviderEstimateService = field(
        default_factory=WholeBookProviderEstimateService
    )
    snapshot_content_hash: str = ""
    source_blocks_provider: Callable[..., Sequence[Mapping[str, Any]]] | None = None
    _cache: dict[str, Any] = field(default_factory=dict, repr=False)

    def estimate(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        configuration_fingerprint: str,
        provider_key: str,
        model_id: str,
        quality_profile: str,
        requested_modules: tuple[str, ...],
        preflight_fingerprint: str,
    ) -> PrivateLabEstimateResult:
        modules = tuple(requested_modules) or PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER
        module_estimates: list[dict[str, Any]] = []
        manifests: list[Any] = []
        total_in = 0
        total_out = 0
        cost_low = 0.0
        cost_exp = 0.0
        cost_high = 0.0
        pricing_status = "known"
        pricing_version = ""
        any_unknown = False

        for module_key in modules:
            blocks = None
            if self.source_blocks_provider is not None:
                blocks = self.source_blocks_provider(
                    book_id=book_id,
                    book_snapshot_id=book_snapshot_id,
                    module_key=module_key,
                )
            bundle: ProviderInputBundle = self.resolver.resolve(
                request_id=f"est-{book_id}-{book_snapshot_id}-{module_key}",
                book_id=int(book_id),
                book_snapshot_id=int(book_snapshot_id),
                module_key=module_key,
                context_bundle_hash=f"ctx:{configuration_fingerprint}:{module_key}",
                provider_key=provider_key,
                model_id=model_id,
                quality_profile=quality_profile,
                source_blocks=blocks,
            )
            est = self.estimate_service.estimate(bundle)
            manifest = self.resolver.build_transfer_manifest(
                bundle,
                estimate=est,
                snapshot_content_hash=self.snapshot_content_hash,
            )
            module_estimates.append(est.safe_dict())
            manifests.append(manifest)
            total_in += int(est.estimated_input_tokens)
            total_out += int(est.estimated_output_tokens)
            if est.cost.pricing_status == "unknown" or est.cost.cost_expected is None:
                any_unknown = True
                pricing_status = "unknown"
            else:
                cost_low += float(est.cost.cost_low or 0.0)
                cost_exp += float(est.cost.cost_expected or 0.0)
                cost_high += float(est.cost.cost_high or 0.0)
                pricing_version = est.cost.pricing_version or pricing_version

        primary = manifests[0] if manifests else None
        # Manifest has no separate manifest_hash field — use consent_fingerprint as binding id.
        manifest_hash = str(getattr(primary, "consent_fingerprint", None) or "")
        if primary is not None and hasattr(primary, "safe_dict"):
            manifest_hash = _fingerprint({"manifest": primary.safe_dict(), "schema": "dtm_hash.v1"})
        aggregate_fp = _fingerprint(
            {
                "schema": "private_lab_estimate.v1",
                "configuration_fingerprint": configuration_fingerprint,
                "preflight_fingerprint": preflight_fingerprint,
                "provider_key": provider_key,
                "model_id": model_id,
                "quality_profile": quality_profile,
                "modules": list(modules),
                "module_estimate_fingerprints": [
                    e.get("estimate_fingerprint") for e in module_estimates
                ],
                "manifest_hash": manifest_hash,
                "input_tokens": total_in,
                "output_tokens": total_out,
            }
        )
        consent_fp = str(getattr(primary, "consent_fingerprint", "") or "")
        estimate_fp = aggregate_fp
        if primary is not None:
            # Prefer U estimate fingerprint for single-module; aggregate for multi.
            if len(modules) == 1 and module_estimates:
                estimate_fp = str(module_estimates[0].get("estimate_fingerprint") or aggregate_fp)

        usage_summary: dict[str, Any] = {
            "source": "whole_book_provider_estimate_service",
            "estimated_input_tokens": total_in,
            "estimated_output_tokens": total_out,
            "estimated_total_tokens": total_in + total_out,
            "tokens_hardcoded": False,
            "module_count": len(modules),
        }
        cost_summary: dict[str, Any] = {
            "source": "provider_pricing_resolver",
            "pricing_status": pricing_status,
            "pricing_version": pricing_version or None,
            "cost_low": None if any_unknown else cost_low,
            "cost_expected": None if any_unknown else cost_exp,
            "cost_high": None if any_unknown else cost_high,
            "cost_hardcoded": False,
            "cost_unknown": any_unknown,
        }
        result = PrivateLabEstimateResult(
            fingerprint=estimate_fp,
            configuration_fingerprint=configuration_fingerprint,
            provider_key=provider_key,
            model_id=model_id,
            quality_profile=quality_profile,
            module_keys=modules,
            usage_summary=usage_summary,
            cost_summary=cost_summary,
            data_transfer_manifest_hash=manifest_hash or consent_fp,
        )
        self._cache[estimate_fp] = {
            "result": result,
            "manifests": manifests,
            "module_estimates": module_estimates,
            "consent_fingerprint": consent_fp,
            "primary_manifest": primary,
        }
        return result

    def validate_fingerprint(
        self,
        *,
        expected_fingerprint: str,
        estimate: PrivateLabEstimateResult,
    ) -> bool:
        return str(expected_fingerprint) == str(estimate.fingerprint)

    def cached_primary_manifest(self, estimate_fingerprint: str) -> Any | None:
        entry = self._cache.get(str(estimate_fingerprint))
        if not entry:
            return None
        return entry.get("primary_manifest")


@dataclass
class PrivateLabConsentServiceAdapter:
    """PrivateLabConsentValidationPort → ConsentGuard + BudgetGuard."""

    consent_guard: PrivateEngineDataTransferConsentGuard = field(
        default_factory=PrivateEngineDataTransferConsentGuard
    )
    budget_guard: PrivateEngineProviderBudgetGuard = field(
        default_factory=PrivateEngineProviderBudgetGuard
    )
    estimate_adapter: PrivateLabEstimateServiceAdapter | None = None
    # When True, client data_transfer_consented is ignored — fingerprint must match.
    ignore_client_consent_boolean: bool = True

    def validate_consent(
        self,
        *,
        consent_fingerprint: str,
        data_transfer_manifest_hash: str,
        data_transfer_consented: bool,
    ) -> PrivateLabConsentResult:
        _ = data_transfer_consented  # deprecated client boolean — not authoritative
        manifest = None
        if self.estimate_adapter is not None:
            # Find cached manifest by hash or any cache entry matching consent fp.
            for entry in self.estimate_adapter._cache.values():
                primary = entry.get("primary_manifest")
                if primary is None:
                    continue
                mh = str(getattr(primary, "consent_fingerprint", "") or "")
                # Also accept recomputed hash stored as data_transfer_manifest_hash
                cached_hash = None
                for fp_key, ent in self.estimate_adapter._cache.items():
                    if ent.get("primary_manifest") is primary:
                        cached_hash = str(
                            getattr(ent.get("result"), "data_transfer_manifest_hash", "") or ""
                        )
                        break
                cf = str(getattr(primary, "consent_fingerprint", "") or "")
                if (
                    mh == data_transfer_manifest_hash
                    or cf == consent_fingerprint
                    or (cached_hash and cached_hash == data_transfer_manifest_hash)
                ):
                    manifest = primary
                    break
        if manifest is None:
            return PrivateLabConsentResult(
                ok=False,
                consent_fingerprint=consent_fingerprint,
                data_transfer_manifest_hash=data_transfer_manifest_hash,
                reason_code="MANIFEST_NOT_REBUILT",
            )
        result = self.consent_guard.check(
            manifest=manifest,
            consent_fingerprint=consent_fingerprint,
            estimate_fingerprint=getattr(manifest, "estimate_fingerprint", None),
        )
        if not result.allowed:
            return PrivateLabConsentResult(
                ok=False,
                consent_fingerprint=consent_fingerprint,
                data_transfer_manifest_hash=data_transfer_manifest_hash,
                reason_code=result.reason or "CONSENT_REJECTED",
            )
        tokens = int(getattr(manifest, "estimated_input_tokens", 0) or 0) + int(
            getattr(manifest, "estimated_output_tokens", 0) or 0
        )
        cost = getattr(manifest, "estimated_cost_expected", None)
        budget = self.budget_guard.check(estimated_tokens=tokens, estimated_cost=cost)
        if not budget.allowed:
            return PrivateLabConsentResult(
                ok=False,
                consent_fingerprint=consent_fingerprint,
                data_transfer_manifest_hash=data_transfer_manifest_hash,
                reason_code=budget.reason or "BUDGET_DENIED",
            )
        return PrivateLabConsentResult(
            ok=True,
            consent_fingerprint=consent_fingerprint,
            data_transfer_manifest_hash=data_transfer_manifest_hash,
            reason_code=None,
        )


@dataclass
class PrivateLabProviderExecutionServiceAdapter:
    """PrivateLabProviderExecutionPort → DefaultWholeBookProviderGateway + Bailian.

    Default composition: dry_run default + Capturing transport.
    Live requires request.dry_run=false AND runtime allow_network AND Live Probe
    AND remaining security gates (CHG-050). Never silent Fake success for denied Live.
    """

    resolver: Any = field(default_factory=FakeProviderInputBundleResolver)
    budget_guard: PrivateEngineProviderBudgetGuard = field(
        default_factory=PrivateEngineProviderBudgetGuard
    )
    dry_run: bool = True
    allow_network: bool = False
    transport: Any | None = None
    live_transport: Any | None = None
    explicit_test_transport_override: bool = False
    credential_resolver: Any | None = None
    environment: str = "development"
    lab_enabled: bool = True
    http_calls: int = 0
    cancelled: set[str] = field(default_factory=set)
    last_payloads: list[dict[str, Any]] = field(default_factory=list, repr=False)
    last_authorization: ProviderExecutionAuthorization | None = field(default=None, repr=False)
    _gateway: Any | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        # Capturing is dry/test default only — never the Live transport.
        if self.transport is None:
            self.transport = CapturingProviderTransport(
                stub=StubTransportResponse(
                    text='{"synthetic":true,"partial":true,"items":[]}',
                    model=PRIVATE_LAB_FIRST_MODEL_ID,
                    request_id="capture-stub",
                    input_tokens=32,
                    output_tokens=16,
                    transport_kind="CAPTURING_TEST",
                )
            )
        if self.credential_resolver is None:
            self.credential_resolver = NoCredentialFakeResolver()
        # Composition gateway stays dry-capable; Live rebuilds per authorization.
        self._gateway = create_lab_provider_gateway(
            dry_run=True,
            allow_network=False,
            credential_resolver=self.credential_resolver,
            budget_guard=self.budget_guard,
            transport=self.transport,
        )

    def _build_authorization(
        self,
        *,
        request: Mapping[str, Any],
        cancellation_ref: str | None,
        budget_valid: bool,
        credential_valid: bool,
    ) -> ProviderExecutionAuthorization:
        if "dry_run" in request:
            requested_dry = bool(request.get("dry_run"))
        else:
            requested_dry = bool(self.dry_run)
        consent_valid = bool(request.get("consent_valid", True))
        estimate_valid = bool(request.get("estimate_valid", True))
        provider_route_valid = bool(request.get("provider_route_valid", True))
        provider_health_allowed = bool(request.get("provider_health_allowed", True))
        return compute_provider_execution_authorization(
            environment=str(request.get("environment") or self.environment),
            private_lab_enabled=bool(request.get("lab_enabled", self.lab_enabled)),
            live_probe_enabled=is_private_provider_live_probe_enabled(),
            allow_network=bool(self.allow_network),
            requested_dry_run=requested_dry,
            consent_valid=consent_valid,
            estimate_valid=estimate_valid,
            budget_valid=budget_valid,
            credential_valid=credential_valid,
            cancellation_requested=bool(
                cancellation_ref and cancellation_ref in self.cancelled
            ),
            provider_route_valid=provider_route_valid,
            provider_health_allowed=provider_health_allowed,
        )

    def _live_gateway(self) -> Any:
        """Gateway for authorized Live — never reuses Capturing dry transport.

        REAL_HTTP: transport=None so Bailian builds formal DashScope transport.
        FAKE_HTTP_TEST: only via live_transport + test override.
        """

        from app.narrative_core.services.provider_transport_kind import (
            ProviderTransportKind,
            is_capturing_transport,
            live_transport_allowed,
        )

        candidate = self.live_transport
        if candidate is None:
            # Do not reuse dry Capturing instance.
            if is_capturing_transport(self.transport):
                candidate = None
            else:
                candidate = self.transport
        ok, deny, kind = live_transport_allowed(
            transport=candidate,
            environment=self.environment,
            explicit_test_override=bool(self.explicit_test_transport_override),
        )
        if not ok:
            raise RuntimeError(f"live_transport_rejected:{deny}")
        live_transport = candidate if kind != ProviderTransportKind.REAL_HTTP else None
        if kind == ProviderTransportKind.FAKE_HTTP_TEST:
            live_transport = candidate
        return create_lab_provider_gateway(
            dry_run=False,
            allow_network=True,
            credential_resolver=self.credential_resolver,
            budget_guard=None,
            transport=live_transport,
        )

    def execute_module(
        self,
        *,
        module_key: str,
        request: Mapping[str, Any],
        cancellation_ref: str | None = None,
    ) -> PrivateLabProviderUsageResult:
        if cancellation_ref and cancellation_ref in self.cancelled:
            auth = self._build_authorization(
                request={**dict(request), "dry_run": False},
                cancellation_ref=cancellation_ref,
                budget_valid=True,
                credential_valid=True,
            )
            self.last_authorization = auth
            return PrivateLabProviderUsageResult(
                module_key=module_key,
                status="cancelled",
                cancellation_honored=True,
                usage={
                    "http": False,
                    "cancelled": True,
                    "authorization_fingerprint": auth.authorization_fingerprint,
                },
            )

        book_id = int(request.get("book_id") or 0)
        book_snapshot_id = int(request.get("book_snapshot_id") or 0)
        bundle = self.resolver.resolve(
            request_id=f"exec-{book_id}-{module_key}",
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            module_key=module_key,
            context_bundle_hash=str(request.get("context_bundle_hash") or "ctx-lab"),
            provider_key=str(request.get("provider_key") or PRIVATE_LAB_FIRST_PROVIDER_KEY),
            model_id=str(request.get("model_id") or PRIVATE_LAB_FIRST_MODEL_ID),
            quality_profile=str(request.get("quality_profile") or "balanced"),
        )
        messages = bundle.transport_messages()
        response_schema = None
        response_schema_ref = getattr(bundle, "response_schema_ref", None)
        response_format_mode = "json_object"
        if str(module_key) == "book_overview":
            from app.narrative_core.services.book_overview_output_contract import (
                SCHEMA_REF,
                book_overview_result_json_schema,
                provider_output_constraint_text,
            )

            response_schema = book_overview_result_json_schema()
            response_schema_ref = SCHEMA_REF
            # Append output constraint to the last user message (schema-derived).
            constraint = provider_output_constraint_text()
            msgs = [dict(m) for m in messages]
            if msgs and msgs[-1].get("role") == "user":
                content = str(msgs[-1].get("content") or "")
                if "Output contract:" not in content:
                    msgs[-1]["content"] = content.rstrip() + "\n\n" + constraint
            messages = tuple(msgs)
        payload = ResolvedProviderPayload(
            messages=messages,
            input_bundle=bundle,
            response_format_mode=response_format_mode,
            response_schema=response_schema,
            response_schema_ref=response_schema_ref,
            allow_tools=False,
            allow_schema_repair=True,
            max_repair_count=1,
        )
        self.last_payloads.append(
            {
                "module_key": module_key,
                "message_count": len(messages),
                "roles": [m.get("role") for m in messages],
                "has_system": any(m.get("role") == "system" for m in messages),
                "has_user": any(m.get("role") == "user" for m in messages),
                "ref_only": False,
                "source_untrusted": True,
                "bundle_fingerprint": bundle.bundle_fingerprint,
            }
        )

        tokens = bundle.source_character_count() // 2 + 64
        budget = self.budget_guard.check(
            estimated_tokens=tokens,
            estimated_cost=None,
            cancellation_ref=cancellation_ref,
            stage_key=module_key,
        )
        if not budget.allowed:
            auth = self._build_authorization(
                request=request,
                cancellation_ref=cancellation_ref,
                budget_valid=False,
                credential_valid=True,
            )
            self.last_authorization = auth
            return PrivateLabProviderUsageResult(
                module_key=module_key,
                status="budget_denied",
                usage={
                    "http": False,
                    "reason": budget.reason,
                    "authorization_fingerprint": auth.authorization_fingerprint,
                    "deny_reason": auth.deny_reason or "budget_denied",
                },
            )

        cred_ok = False
        if self.credential_resolver is not None:
            secret = self.credential_resolver.resolve(PRIVATE_LAB_FIRST_PROVIDER_KEY)
            cred_ok = bool(secret)
            secret = None

        requested_dry = auth_requested_dry(request, self.dry_run)
        auth = self._build_authorization(
            request=request,
            cancellation_ref=cancellation_ref,
            budget_valid=True,
            # Intentional dry does not require credential at execute boundary.
            credential_valid=True if requested_dry else cred_ok,
        )
        self.last_authorization = auth

        from app.narrative_core.private_engine_contract.provider_gateway import (
            ProviderInferenceRequest,
        )

        inference = ProviderInferenceRequest(
            request_id=f"lab-{module_key}-{book_id}",
            provider_kind=(
                PRIVATE_LAB_FIRST_PROVIDER_KEY
                if not auth.effective_dry_run
                else "fake"
            ),
            model_route="balanced",
            task_type=f"module:{module_key}",
            system_instruction_ref=bundle.system_instruction_ref,
            prompt_pack_ref=f"{bundle.prompt_pack_id}@{bundle.prompt_pack_version}",
            input_bundle_ref=f"bundle:{bundle.bundle_fingerprint[:12]}",
            response_schema_ref=bundle.response_schema_ref,
            temperature_policy={"temperature": 0.2},
            token_budget=bundle.token_budget or 2048,
            cost_budget=bundle.cost_budget,
            timeout_policy={"timeout_seconds": 30},
            retry_policy={"max_retries": 1},
            cancellation_ref=cancellation_ref,
            data_handling_policy=dict(bundle.data_handling_policy),
            metadata={
                "module_key": module_key,
                "requested_dry_run": auth.requested_dry_run,
                "effective_dry_run": auth.effective_dry_run,
                "authorization_fingerprint": auth.authorization_fingerprint,
                "environment": self.environment,
                "explicit_test_transport_override": bool(
                    self.explicit_test_transport_override
                ),
            },
        )

        if not auth.effective_dry_run:
            # Authorized Live — never Capturing; REAL_HTTP or FAKE_HTTP_TEST only.
            try:
                live_gw = self._live_gateway()
            except Exception as exc:  # noqa: BLE001
                return PrivateLabProviderUsageResult(
                    module_key=module_key,
                    status="security_denied",
                    usage={
                        "http": False,
                        "live": False,
                        "deny_reason": "live_transport_rejected",
                        "detail": type(exc).__name__,
                        "authorization_fingerprint": auth.authorization_fingerprint,
                        "effective_dry_run": True,
                        "synthetic_success": False,
                    },
                )
            live_gw.bind_resolved_payload(inference.request_id, payload)
            try:
                resp = live_gw.execute(inference, resolved_payload=payload)
            except Exception as exc:  # noqa: BLE001
                detail = getattr(exc, "detail_code", None) or type(exc).__name__
                return PrivateLabProviderUsageResult(
                    module_key=module_key,
                    status="provider_failed",
                    usage={
                        "http": False,
                        "live": True,
                        "authorization_fingerprint": auth.authorization_fingerprint,
                        "synthetic_success": False,
                        "detail_code": str(detail),
                    },
                )
            self.http_calls += 1
            if getattr(resp, "status", "") != "success":
                return PrivateLabProviderUsageResult(
                    module_key=module_key,
                    status=str(getattr(resp, "status", "failed")),
                    usage={
                        "http": True,
                        "live": True,
                        "authorization_fingerprint": auth.authorization_fingerprint,
                        "synthetic_success": False,
                        "provider_request_id": getattr(resp, "provider_request_id", None),
                    },
                )
            structured = dict(getattr(resp, "structured_output", None) or {})
            audit = dict(structured.pop("_provider_audit", None) or {})
            transport_kind = audit.get("transport_kind")
            provider_request_id = (
                getattr(resp, "provider_request_id", None)
                or audit.get("provider_request_id")
            )
            if transport_kind == "CAPTURING_TEST" or not provider_request_id:
                return PrivateLabProviderUsageResult(
                    module_key=module_key,
                    status="provider_failed",
                    usage={
                        "http": False,
                        "live": True,
                        "deny_reason": "live_usage_not_confirmed",
                        "transport_kind": transport_kind,
                        "provider_request_id": provider_request_id,
                        "authorization_fingerprint": auth.authorization_fingerprint,
                        "synthetic_success": False,
                    },
                )
            return PrivateLabProviderUsageResult(
                module_key=module_key,
                status="success",
                usage={
                    "http": True,
                    "live": True,
                    "live_request_confirmed": True,
                    "transport_kind": transport_kind,
                    "provider_request_id": provider_request_id,
                    "http_status": audit.get("http_status"),
                    "provider_host": audit.get("host"),
                    "usage_source": audit.get("usage_source") or "provider_response",
                    "input_tokens": getattr(resp, "token_input", None),
                    "output_tokens": getattr(resp, "token_output", None),
                    "actual_cost": getattr(resp, "cost", None),
                    "latency_ms": getattr(resp, "latency_ms", None),
                    "finish_reason": getattr(resp, "finish_reason", None),
                    "retry_count": getattr(resp, "retry_count", 0),
                    "authorization_fingerprint": auth.authorization_fingerprint,
                    "effective_dry_run": False,
                    "synthetic_success": False,
                },
                output_fingerprint=f"live-{module_key}-{bundle.bundle_fingerprint[:8]}",
                structured_output=structured,
            )

        # Live was requested but gates failed — explicit deny, never Fake Success.
        if not auth.requested_dry_run and auth.deny_reason:
            return PrivateLabProviderUsageResult(
                module_key=module_key,
                status="security_denied",
                usage={
                    "http": False,
                    "live": False,
                    "deny_reason": auth.deny_reason,
                    "authorization_fingerprint": auth.authorization_fingerprint,
                    "effective_dry_run": True,
                    "synthetic_success": False,
                },
            )

        # Intentional dry path: Capturing / Fake only — zero network.
        if hasattr(self.transport, "generate"):
            try:
                self.transport.generate(
                    messages=[{"role": m["role"], "content": m["content"]} for m in messages],
                    model=str(request.get("model_id") or PRIVATE_LAB_FIRST_MODEL_ID),
                    response_format_mode="json_object",
                    max_tokens=512,
                    timeout_seconds=5,
                    cancellation_ref=cancellation_ref,
                )
            except Exception:
                pass
        return PrivateLabProviderUsageResult(
            module_key=module_key,
            status="success",
            usage={
                "http": False,
                "dry_run": True,
                "live_probe": is_private_provider_live_probe_enabled(),
                "tokens_from_payload": True,
                "authorization_fingerprint": auth.authorization_fingerprint,
                "effective_dry_run": True,
                "requested_dry_run": auth.requested_dry_run,
            },
            output_fingerprint=f"dry-{module_key}-{bundle.bundle_fingerprint[:8]}",
            structured_output={
                "synthetic": True,
                "partial": True,
                "module_key": module_key,
                "private_lab": True,
            },
        )

    def cancel(self, cancellation_ref: str) -> bool:
        if cancellation_ref:
            self.cancelled.add(cancellation_ref)
            self.budget_guard.cancel(cancellation_ref)
            if self._gateway is not None and hasattr(self._gateway, "cancel"):
                self._gateway.cancel(cancellation_ref)
            return True
        return False


def auth_requested_dry(request: Mapping[str, Any], default_dry: bool) -> bool:
    if "dry_run" in request:
        return bool(request.get("dry_run"))
    return bool(default_dry)

def resolve_server_security_status(
    *,
    credential_resolver: ExistingCredentialServiceAdapter | None = None,
    budget_guard: PrivateEngineProviderBudgetGuard | None = None,
    capability_ok: bool = True,
    provider_key: str = PRIVATE_LAB_FIRST_PROVIDER_KEY,
    estimated_tokens: int = 0,
    estimated_cost: float | None = None,
) -> ServerSecurityStatus:
    """Server-side credential / budget / capability — client booleans ignored."""

    cred_ok = False
    detail: dict[str, Any] = {}
    if credential_resolver is not None and credential_resolver.enabled:
        secret = credential_resolver.resolve(provider_key)
        cred_ok = bool(secret)
        detail["credential_checked"] = True
        # Never retain secret
        secret = None
    else:
        detail["credential_checked"] = False
        detail["credential_adapter_disabled"] = True

    guard = budget_guard or PrivateEngineProviderBudgetGuard()
    budget = guard.check(estimated_tokens=estimated_tokens, estimated_cost=estimated_cost)
    return ServerSecurityStatus(
        credential_present=cred_ok,
        budget_ok=bool(budget.allowed),
        capability_ok=bool(capability_ok),
        detail={**detail, "budget_reason": budget.reason},
    )


__all__ = [
    "PrivateLabConsentServiceAdapter",
    "PrivateLabEstimateServiceAdapter",
    "PrivateLabPreflightServiceAdapter",
    "PrivateLabProviderExecutionServiceAdapter",
    "ServerSecurityStatus",
    "resolve_server_security_status",
]
