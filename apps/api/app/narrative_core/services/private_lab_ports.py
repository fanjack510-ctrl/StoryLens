"""Private Lab parallel-compatible Ports (Phase 2B-R1 Agent V).

Minimal Ports so V does not import Agent U files that are not yet merged.
Integration adapts these Ports to U's Estimate / Consent / Preflight services.
No hardcoded token/cost estimates. Tests use Fake implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class PrivateLabPreflightResult:
    """Preflight outcome — Snapshot/capability/gate checks only; no Run."""

    ok: bool
    fingerprint: str
    book_id: int
    book_snapshot_id: int
    snapshot_content_hash: str | None = None
    reason_code: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PrivateLabEstimateResult:
    """Estimate fingerprint envelope — values come from U; V only validates match."""

    fingerprint: str
    configuration_fingerprint: str
    provider_key: str
    model_id: str
    quality_profile: str
    module_keys: tuple[str, ...] = ()
    # Opaque usage/cost fields — never invent numbers in V.
    usage_summary: Mapping[str, Any] = field(default_factory=dict)
    cost_summary: Mapping[str, Any] = field(default_factory=dict)
    data_transfer_manifest_hash: str | None = None


@dataclass(frozen=True, slots=True)
class PrivateLabConsentResult:
    """Consent fingerprint vs data-transfer manifest."""

    ok: bool
    consent_fingerprint: str
    data_transfer_manifest_hash: str
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class PrivateLabProviderUsageResult:
    """Per-module usage after provider execution — opaque; no fake costs."""

    module_key: str
    status: str
    usage: Mapping[str, Any] = field(default_factory=dict)
    output_fingerprint: str | None = None
    cancellation_honored: bool = False
    structured_output: Mapping[str, Any] | None = None


@runtime_checkable
class PrivateLabPreflightPort(Protocol):
    def preflight(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        configuration_fingerprint: str,
        requested_modules: tuple[str, ...],
    ) -> PrivateLabPreflightResult: ...


@runtime_checkable
class PrivateLabEstimatePort(Protocol):
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
    ) -> PrivateLabEstimateResult: ...

    def validate_fingerprint(
        self,
        *,
        expected_fingerprint: str,
        estimate: PrivateLabEstimateResult,
    ) -> bool: ...


@runtime_checkable
class PrivateLabConsentValidationPort(Protocol):
    def validate_consent(
        self,
        *,
        consent_fingerprint: str,
        data_transfer_manifest_hash: str,
        data_transfer_consented: bool,
    ) -> PrivateLabConsentResult: ...


@runtime_checkable
class PrivateLabProviderExecutionPort(Protocol):
    """Provider execution boundary for Lab executor tests / Integration wiring."""

    def execute_module(
        self,
        *,
        module_key: str,
        request: Mapping[str, Any],
        cancellation_ref: str | None = None,
    ) -> PrivateLabProviderUsageResult: ...

    def cancel(self, cancellation_ref: str) -> bool: ...


@dataclass
class FakePrivateLabPreflightPort:
    """Test Fake — accepts by default; set ok=False to reject."""

    ok: bool = True
    fingerprint: str = "preflight-fp-ok"
    reason_code: str | None = None
    snapshot_content_hash: str = "snap-hash-synthetic"

    def preflight(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        configuration_fingerprint: str,
        requested_modules: tuple[str, ...],
    ) -> PrivateLabPreflightResult:
        _ = configuration_fingerprint, requested_modules
        return PrivateLabPreflightResult(
            ok=self.ok,
            fingerprint=self.fingerprint,
            book_id=int(book_id),
            book_snapshot_id=int(book_snapshot_id),
            snapshot_content_hash=self.snapshot_content_hash,
            reason_code=None if self.ok else (self.reason_code or "PREFLIGHT_REJECTED"),
        )


@dataclass
class FakePrivateLabEstimatePort:
    """Test Fake — returns fixed fingerprint; no token/cost invention beyond opaque stubs."""

    fingerprint: str = "estimate-fp-ok"
    data_transfer_manifest_hash: str = "manifest-hash-ok"

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
        _ = book_id, book_snapshot_id, preflight_fingerprint
        return PrivateLabEstimateResult(
            fingerprint=self.fingerprint,
            configuration_fingerprint=configuration_fingerprint,
            provider_key=provider_key,
            model_id=model_id,
            quality_profile=quality_profile,
            module_keys=tuple(requested_modules),
            usage_summary={"source": "fake_port", "tokens_unknown": True},
            cost_summary={"source": "fake_port", "cost_unknown": True},
            data_transfer_manifest_hash=self.data_transfer_manifest_hash,
        )

    def validate_fingerprint(
        self,
        *,
        expected_fingerprint: str,
        estimate: PrivateLabEstimateResult,
    ) -> bool:
        return str(expected_fingerprint) == str(estimate.fingerprint)


@dataclass
class FakePrivateLabConsentValidationPort:
    ok: bool = True
    reason_code: str | None = None

    def validate_consent(
        self,
        *,
        consent_fingerprint: str,
        data_transfer_manifest_hash: str,
        data_transfer_consented: bool,
    ) -> PrivateLabConsentResult:
        ok = self.ok and bool(data_transfer_consented) and bool(consent_fingerprint)
        return PrivateLabConsentResult(
            ok=ok,
            consent_fingerprint=consent_fingerprint,
            data_transfer_manifest_hash=data_transfer_manifest_hash,
            reason_code=None if ok else (self.reason_code or "CONSENT_REJECTED"),
        )


@dataclass
class FakePrivateLabProviderExecutionPort:
    """Synthetic provider — no HTTP, no credentials, no model calls."""

    cancelled: set[str] = field(default_factory=set)
    responses: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    http_calls: int = 0

    def execute_module(
        self,
        *,
        module_key: str,
        request: Mapping[str, Any],
        cancellation_ref: str | None = None,
    ) -> PrivateLabProviderUsageResult:
        if cancellation_ref and cancellation_ref in self.cancelled:
            return PrivateLabProviderUsageResult(
                module_key=module_key,
                status="cancelled",
                cancellation_honored=True,
                usage={"synthetic": True, "http": False},
            )
        payload = dict(self.responses.get(module_key) or {"synthetic": True, "module_key": module_key})
        return PrivateLabProviderUsageResult(
            module_key=module_key,
            status="success",
            usage={"synthetic": True, "http": False, "tokens_unknown": True},
            output_fingerprint=f"out-fp-{module_key}",
            structured_output=payload,
        )

    def cancel(self, cancellation_ref: str) -> bool:
        if cancellation_ref:
            self.cancelled.add(cancellation_ref)
            return True
        return False


__all__ = [
    "FakePrivateLabConsentValidationPort",
    "FakePrivateLabEstimatePort",
    "FakePrivateLabPreflightPort",
    "FakePrivateLabProviderExecutionPort",
    "PrivateLabConsentResult",
    "PrivateLabConsentValidationPort",
    "PrivateLabEstimatePort",
    "PrivateLabEstimateResult",
    "PrivateLabPreflightPort",
    "PrivateLabPreflightResult",
    "PrivateLabProviderExecutionPort",
    "PrivateLabProviderUsageResult",
]
