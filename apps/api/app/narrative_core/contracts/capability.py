"""Capability / Quota Protocol contracts (Agent H implements)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

from app.narrative_core.enums import (
    CapabilityAvailability,
    CapabilityKey,
    CapabilityReasonCode,
    CostClass,
    QuotaPolicyKind,
    WholeBookAnalysisMode,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class QuotaPolicy:
    """Frozen quota policy metadata attached to a capability."""

    kind: QuotaPolicyKind
    policy_key: str = ""
    limit: int | float | None = None
    window_seconds: int | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.policy_key:
            object.__setattr__(self, "policy_key", f"quota_{self.kind.value}")


@dataclass(frozen=True, slots=True)
class CapabilityMetadata:
    """Frozen registry metadata for a canonical capability key.

    ``shipped`` is independent of whether the user holds a License.
    Final use requires: shipped + environment + license + quota + runtime conditions.
    """

    key: CapabilityKey
    display_name: str
    description: str
    shipped: bool
    requires_license: bool
    availability: CapabilityAvailability
    preview_visible: bool = False
    enabled: bool = False
    entry_visible: bool = False
    product_reason_code: str | None = None
    minimum_version: str | None = None
    supported_modes: tuple[WholeBookAnalysisMode, ...] = ()
    quota_policy_key: str = ""
    estimated_cost_class: CostClass = CostClass.FREE
    quota_policies: tuple[QuotaPolicy, ...] = ()
    offline_allowed: bool = True

    @property
    def label(self) -> str:
        """Back-compat alias for display_name."""
        return self.display_name

    @property
    def capability_id(self) -> str:
        return self.key.value

    @property
    def requires_pro(self) -> bool:
        return self.requires_license


@dataclass(frozen=True, slots=True)
class QuotaDecision:
    """Quota evaluation result for reserve/commit flows (License-separated)."""

    allowed: bool
    reason_code: CapabilityReasonCode
    policy_key: str = ""
    policy_kind: QuotaPolicyKind = QuotaPolicyKind.NONE
    limit: int | float | None = None
    used: int | float | None = None
    reserved: int | float | None = None
    remaining: int | float | None = None
    reset_at: datetime | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    """Pre-evaluated capability gate result. Frontend must not recompute ``allowed``."""

    capability_key: CapabilityKey
    allowed: bool
    reason_code: CapabilityReasonCode
    availability: CapabilityAvailability
    display_message: str = ""
    supported_modes: tuple[WholeBookAnalysisMode, ...] = ()
    quota: QuotaDecision | None = None
    usage: int | float | None = None
    remaining: int | float | None = None
    offline_status: str = "unknown"
    license_status: str = "unknown"
    evaluated_at: datetime = field(default_factory=_utc_now)
    preview_only: bool = False
    metadata: CapabilityMetadata | None = None

    @property
    def message(self) -> str:
        """Back-compat alias for display_message."""
        return self.display_message


def evaluate_from_metadata(
    metadata: CapabilityMetadata,
    *,
    licensed: bool = False,
) -> CapabilityDecision:
    """Pure helper for contract tests — not a production License service."""

    modes = metadata.supported_modes
    if not metadata.shipped:
        return CapabilityDecision(
            capability_key=metadata.key,
            allowed=False,
            reason_code=CapabilityReasonCode.CAPABILITY_NOT_SHIPPED,
            availability=CapabilityAvailability.UNAVAILABLE,
            display_message="Capability not shipped",
            supported_modes=modes,
            license_status="n/a",
            offline_status="n/a",
            metadata=metadata,
        )
    if metadata.requires_license and not licensed:
        return CapabilityDecision(
            capability_key=metadata.key,
            allowed=False,
            reason_code=CapabilityReasonCode.CAPABILITY_NOT_LICENSED,
            availability=metadata.availability,
            display_message="License required",
            supported_modes=modes,
            license_status="missing",
            metadata=metadata,
        )
    if metadata.availability == CapabilityAvailability.PREVIEW:
        return CapabilityDecision(
            capability_key=metadata.key,
            allowed=True,
            reason_code=CapabilityReasonCode.CAPABILITY_PREVIEW_ONLY,
            availability=CapabilityAvailability.PREVIEW,
            display_message="Preview only",
            supported_modes=modes,
            preview_only=True,
            license_status="ok" if licensed or not metadata.requires_license else "missing",
            metadata=metadata,
        )
    return CapabilityDecision(
        capability_key=metadata.key,
        allowed=True,
        reason_code=CapabilityReasonCode.CAPABILITY_AVAILABLE,
        availability=CapabilityAvailability.AVAILABLE,
        display_message="Available",
        supported_modes=modes,
        license_status="ok" if licensed or not metadata.requires_license else "missing",
        metadata=metadata,
    )


# Narrative foundation capabilities are NOT Pro-gated at the public asset API layer.
NARRATIVE_FOUNDATION_CAPABILITY_KEYS: frozenset[CapabilityKey] = frozenset(
    {CapabilityKey.NARRATIVE_ASSET_LIBRARY}
)


def is_pro_gated_capability(key: CapabilityKey | str) -> bool:
    """True when capability evaluation must gate Pro license (not foundation storage)."""

    resolved = CapabilityKey(key) if isinstance(key, str) else key
    return resolved not in NARRATIVE_FOUNDATION_CAPABILITY_KEYS


class CapabilityService(Protocol):
    def evaluate_capability(
        self,
        capability_key: CapabilityKey | str,
        *,
        context: dict[str, Any] | None = None,
    ) -> CapabilityDecision:
        ...

    def require_capability(
        self,
        capability_key: CapabilityKey | str,
        *,
        context: dict[str, Any] | None = None,
    ) -> CapabilityDecision:
        """Raise NarrativeCoreError when not allowed."""

    def list_capabilities(self) -> Sequence[CapabilityMetadata]:
        ...

    def get_capability_metadata(self, capability_key: CapabilityKey | str) -> CapabilityMetadata:
        ...

    def evaluate_mode(
        self,
        capability_key: CapabilityKey | str,
        mode: WholeBookAnalysisMode | str,
    ) -> CapabilityDecision:
        ...

    def evaluate_quota(
        self,
        capability_key: CapabilityKey | str,
        *,
        context: dict[str, Any] | None = None,
    ) -> QuotaDecision:
        ...

    def reserve_usage(
        self,
        capability_key: CapabilityKey | str,
        *,
        amount: int | float = 1,
        context: dict[str, Any] | None = None,
    ) -> QuotaDecision:
        ...

    def release_usage(
        self,
        capability_key: CapabilityKey | str,
        *,
        reservation_id: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        ...

    def commit_usage(
        self,
        capability_key: CapabilityKey | str,
        *,
        reservation_id: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        ...
