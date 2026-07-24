"""Data Transfer Consent + Provider Budget Guards (Phase 2B-R1 Agent U).

Unconfirmed / budget-denied / cancelled requests must not call Provider.
Does not write Candidates or create AnalysisRuns. Credentials never logged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.narrative_core.private_engine_contract.data_transfer import (
    ConsentFingerprintService,
    WholeBookDataTransferManifest,
)
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineErrorCode,
    private_engine_error,
)


@dataclass(frozen=True, slots=True)
class ConsentGuardResult:
    allowed: bool
    reason: str | None = None
    credential_present: bool | None = None


@dataclass(frozen=True, slots=True)
class BudgetGuardResult:
    allowed: bool
    reason: str | None = None
    request_count: int = 0
    token_count: int = 0
    cost_total: float = 0.0


@dataclass
class PrivateEngineDataTransferConsentGuard:
    """Gate Provider calls on Manifest consent fingerprint + binding hashes."""

    consent: ConsentFingerprintService = field(default_factory=ConsentFingerprintService)
    require_consent: bool = True

    def check(
        self,
        *,
        manifest: WholeBookDataTransferManifest,
        consent_fingerprint: str | None,
        estimate_fingerprint: str | None = None,
        snapshot_content_hash: str | None = None,
        context_bundle_hash: str | None = None,
        provider_key: str | None = None,
        model_id: str | None = None,
        prompt_pack_version: str | None = None,
        credential_present: bool | None = None,
    ) -> ConsentGuardResult:
        if self.require_consent and manifest.consent_required:
            if not consent_fingerprint:
                return ConsentGuardResult(
                    allowed=False,
                    reason="consent_missing",
                    credential_present=credential_present,
                )
            if not self.consent.matches(
                consent_fingerprint=consent_fingerprint,
                manifest=manifest,
            ):
                return ConsentGuardResult(
                    allowed=False,
                    reason="consent_fingerprint_mismatch",
                    credential_present=credential_present,
                )
        if estimate_fingerprint is not None and estimate_fingerprint != manifest.estimate_fingerprint:
            return ConsentGuardResult(
                allowed=False,
                reason="estimate_fingerprint_mismatch",
                credential_present=credential_present,
            )
        if snapshot_content_hash is not None and manifest.snapshot_content_hash:
            if snapshot_content_hash != manifest.snapshot_content_hash:
                return ConsentGuardResult(
                    allowed=False,
                    reason="snapshot_hash_mismatch",
                    credential_present=credential_present,
                )
        if context_bundle_hash is not None and context_bundle_hash != manifest.context_bundle_hash:
            return ConsentGuardResult(
                allowed=False,
                reason="context_bundle_hash_mismatch",
                credential_present=credential_present,
            )
        if provider_key is not None and provider_key != manifest.provider_key:
            return ConsentGuardResult(
                allowed=False,
                reason="provider_key_mismatch",
                credential_present=credential_present,
            )
        if model_id is not None and model_id != manifest.model_id:
            return ConsentGuardResult(
                allowed=False,
                reason="model_id_mismatch",
                credential_present=credential_present,
            )
        if prompt_pack_version is not None and manifest.prompt_pack_version:
            if prompt_pack_version != manifest.prompt_pack_version:
                return ConsentGuardResult(
                    allowed=False,
                    reason="prompt_pack_version_mismatch",
                    credential_present=credential_present,
                )
        if manifest.pricing_status == "unknown":
            return ConsentGuardResult(
                allowed=False,
                reason="pricing_unknown_blocks_auto_confirm",
                credential_present=credential_present,
            )
        return ConsentGuardResult(allowed=True, reason=None, credential_present=credential_present)

    def assert_allowed(self, result: ConsentGuardResult) -> None:
        if not result.allowed:
            raise private_engine_error(
                PrivateEngineErrorCode.DATA_HANDLING_CONSENT_REQUIRED,
                detail_code=result.reason,
            )


@dataclass
class PrivateEngineProviderBudgetGuard:
    """Single-call + daily request/token/cost + retry budget gate."""

    single_request_token_limit: int = 200_000
    single_request_cost_limit: float = 1.0
    daily_request_limit: int = 50
    daily_token_limit: int = 200_000
    daily_cost_limit: float = 1.0
    max_retries: int = 2
    request_count: int = 0
    token_count: int = 0
    cost_total: float = 0.0
    cancelled_refs: set[str] = field(default_factory=set)
    force_deny: bool = False
    checks: list[dict[str, Any]] = field(default_factory=list)

    def cancel(self, cancellation_ref: str) -> None:
        if cancellation_ref:
            self.cancelled_refs.add(cancellation_ref)

    def is_cancelled(self, cancellation_ref: str | None) -> bool:
        return bool(cancellation_ref) and cancellation_ref in self.cancelled_refs

    def check(
        self,
        *,
        estimated_tokens: int,
        estimated_cost: float | None,
        cancellation_ref: str | None = None,
        retry_index: int = 0,
        stage_key: str = "provider",
    ) -> BudgetGuardResult:
        if self.force_deny:
            result = BudgetGuardResult(allowed=False, reason="force_deny")
            self._record(stage_key, result, estimated_tokens)
            return result
        if self.is_cancelled(cancellation_ref):
            result = BudgetGuardResult(allowed=False, reason="cancelled_blocks_retry")
            self._record(stage_key, result, estimated_tokens)
            return result
        if retry_index > self.max_retries:
            result = BudgetGuardResult(allowed=False, reason="retry_budget_exceeded")
            self._record(stage_key, result, estimated_tokens)
            return result
        if estimated_tokens > self.single_request_token_limit:
            result = BudgetGuardResult(allowed=False, reason="single_request_token_budget")
            self._record(stage_key, result, estimated_tokens)
            return result
        if estimated_cost is not None and estimated_cost > self.single_request_cost_limit:
            result = BudgetGuardResult(allowed=False, reason="single_request_cost_budget")
            self._record(stage_key, result, estimated_tokens)
            return result
        if self.request_count + 1 > self.daily_request_limit:
            result = BudgetGuardResult(
                allowed=False,
                reason="daily_request_budget",
                request_count=self.request_count,
                token_count=self.token_count,
                cost_total=self.cost_total,
            )
            self._record(stage_key, result, estimated_tokens)
            return result
        if self.token_count + estimated_tokens > self.daily_token_limit:
            result = BudgetGuardResult(
                allowed=False,
                reason="daily_token_budget",
                request_count=self.request_count,
                token_count=self.token_count,
                cost_total=self.cost_total,
            )
            self._record(stage_key, result, estimated_tokens)
            return result
        projected_cost = self.cost_total + float(estimated_cost or 0.0)
        if estimated_cost is not None and projected_cost > self.daily_cost_limit:
            result = BudgetGuardResult(
                allowed=False,
                reason="daily_cost_budget",
                request_count=self.request_count,
                token_count=self.token_count,
                cost_total=self.cost_total,
            )
            self._record(stage_key, result, estimated_tokens)
            return result
        result = BudgetGuardResult(
            allowed=True,
            request_count=self.request_count,
            token_count=self.token_count,
            cost_total=self.cost_total,
        )
        self._record(stage_key, result, estimated_tokens)
        return result

    def assert_allowed(self, result: BudgetGuardResult) -> None:
        if not result.allowed:
            if result.reason == "cancelled_blocks_retry":
                raise private_engine_error(
                    PrivateEngineErrorCode.PROVIDER_CANCELLED,
                    detail_code=result.reason,
                )
            raise private_engine_error(
                PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED,
                detail_code=result.reason,
            )

    def record_spend(self, *, tokens: int = 0, cost: float = 0.0) -> None:
        self.request_count += 1
        self.token_count += int(tokens)
        self.cost_total += float(cost)

    # BudgetGuard Protocol compatibility for gateway bridge.
    def check_budget(self, *, stage_key: str, estimated_tokens: int = 0) -> bool:
        return self.check(
            estimated_tokens=estimated_tokens,
            estimated_cost=None,
            stage_key=stage_key,
        ).allowed

    def _record(self, stage_key: str, result: BudgetGuardResult, estimated_tokens: int) -> None:
        self.checks.append(
            {
                "stage_key": stage_key,
                "estimated_tokens": int(estimated_tokens),
                "allowed": result.allowed,
                "reason": result.reason,
            }
        )


@dataclass
class PrivateLabPreflightEstimateService:
    """Private Lab preflight foundation — estimate + manifest + guards, no Run create."""

    resolver: Any
    consent_guard: PrivateEngineDataTransferConsentGuard = field(
        default_factory=PrivateEngineDataTransferConsentGuard
    )
    budget_guard: PrivateEngineProviderBudgetGuard = field(
        default_factory=PrivateEngineProviderBudgetGuard
    )

    def preflight(
        self,
        *,
        resolve_kwargs: Mapping[str, Any],
        consent_fingerprint: str | None = None,
        max_retries: int = 1,
        credential_present: bool | None = None,
    ) -> dict[str, Any]:
        bundle = self.resolver.resolve(**dict(resolve_kwargs))
        estimate = self.resolver.estimate(bundle, max_retries=max_retries)
        manifest = self.resolver.build_transfer_manifest(bundle, estimate=estimate)
        consent = self.consent_guard.check(
            manifest=manifest,
            consent_fingerprint=consent_fingerprint,
            estimate_fingerprint=estimate.estimate_fingerprint,
            context_bundle_hash=bundle.context_bundle_hash,
            provider_key=bundle.provider_key,
            model_id=bundle.model_id,
            prompt_pack_version=bundle.prompt_pack_version,
            credential_present=credential_present,
        )
        budget = self.budget_guard.check(
            estimated_tokens=estimate.estimated_total_tokens,
            estimated_cost=estimate.cost.cost_expected,
        )
        return {
            "bundle_fingerprint": bundle.bundle_fingerprint,
            "manifest": manifest.safe_dict(),
            "estimate": estimate.safe_dict(),
            "consent": {
                "allowed": consent.allowed,
                "reason": consent.reason,
                "credential_present": consent.credential_present,
            },
            "budget": {
                "allowed": budget.allowed,
                "reason": budget.reason,
            },
            "provider_call_allowed": bool(consent.allowed and budget.allowed and estimate.context_limit_ok),
            "creates_analysis_run": False,
            "writes_candidate": False,
        }
