"""CapabilityService implementation (Phase 1C Agent H).

Backend is the sole trusted source of ``allowed``. Frontend-supplied allowed
flags are ignored. Public narrative asset APIs must NOT call this service for
foundation storage; only Pro-gated product capabilities (esp. whole-book runs).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy.orm import Session

from app.narrative_core.capability_legacy import (
    LEGACY_TO_CAPABILITY,
    map_legacy_feature_key,
)
from app.narrative_core.capability_registry import (
    CAPABILITY_REGISTRY,
    get_capability_metadata as registry_get_metadata,
    list_capability_metadata,
)
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.contracts.capability import (
    CapabilityDecision,
    CapabilityMetadata,
    QuotaDecision,
    is_pro_gated_capability,
)
from app.narrative_core.enums import (
    CapabilityAvailability,
    CapabilityKey,
    CapabilityReasonCode,
    WholeBookAnalysisMode,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.quota_service import InMemoryQuotaService, QuotaService
from app.services import entitlement as entitlement_service
from app.services.license_crypto import CANONICAL_FEATURES, LicenseError, parse_and_verify

LicenseStatus = str  # "ok" | "missing" | "expired" | "invalid" | "n/a"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_capability_key(feature_key: str) -> CapabilityKey | None:
    """Map canonical or legacy feature key → CapabilityKey. Unknown → None."""

    raw = (feature_key or "").strip()
    if not raw:
        return None
    try:
        return CapabilityKey(raw)
    except ValueError:
        pass
    mapped = LEGACY_TO_CAPABILITY.get(raw)
    if mapped is not None:
        return mapped
    legacy = map_legacy_feature_key(raw)
    return legacy.capability_key


# Call sites still using can_use_feature (compat adapter) — keep in sync in docs.
UNMIGRATED_CAN_USE_FEATURE_CALL_SITES: tuple[str, ...] = (
    "apps/api/app/api/v1/desktop.py:get_feature_entitlement",
)


class DefaultCapabilityService:
    """Production CapabilityService backed by frozen registry + local License."""

    def __init__(
        self,
        session: Session | None = None,
        *,
        quota: QuotaService | None = None,
        metadata_overrides: Mapping[CapabilityKey, CapabilityMetadata] | None = None,
        license_state: dict[str, Any] | None = None,
        reverify_license: bool = True,
    ) -> None:
        self._session = session
        self._quota: QuotaService = quota or InMemoryQuotaService()
        self._metadata_overrides = dict(metadata_overrides or {})
        # Test injection: {"status": "ok"|"missing"|"expired"|"invalid", "features": [...]}
        self._license_state = license_state
        self._reverify_license = reverify_license

    # -- metadata -------------------------------------------------------------

    def list_capabilities(self) -> Sequence[CapabilityMetadata]:
        items = list(list_capability_metadata())
        if not self._metadata_overrides:
            return items
        by_key = {item.key: item for item in items}
        by_key.update(self._metadata_overrides)
        return list(by_key.values())

    def get_capability_metadata(self, capability_key: CapabilityKey | str) -> CapabilityMetadata:
        resolved = self._resolve_or_raise(capability_key)
        if resolved in self._metadata_overrides:
            return self._metadata_overrides[resolved]
        return registry_get_metadata(resolved)

    def _resolve_or_raise(self, capability_key: CapabilityKey | str) -> CapabilityKey:
        if isinstance(capability_key, CapabilityKey):
            return capability_key
        try:
            return CapabilityKey(str(capability_key))
        except ValueError as exc:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED,
                f"Unknown capability: {capability_key}",
            ) from exc

    def _try_resolve(self, capability_key: CapabilityKey | str) -> CapabilityKey | None:
        if isinstance(capability_key, CapabilityKey):
            return capability_key
        try:
            return CapabilityKey(str(capability_key))
        except ValueError:
            return None

    # -- license --------------------------------------------------------------

    def _evaluate_license(
        self,
        metadata: CapabilityMetadata,
        *,
        context: dict[str, Any] | None,
    ) -> tuple[LicenseStatus, set[str]]:
        ctx = context or {}
        if self._license_state is not None:
            status = str(self._license_state.get("status") or "missing")
            features = {
                str(item)
                for item in (self._license_state.get("features") or CANONICAL_FEATURES)
            }
            return status, features

        forced = ctx.get("license_status")
        if forced in {"ok", "missing", "expired", "invalid"}:
            features = {
                str(item)
                for item in (ctx.get("license_features") or CANONICAL_FEATURES)
            }
            return str(forced), features

        if self._session is None:
            if not metadata.requires_license:
                return "n/a", set(CANONICAL_FEATURES)
            return "missing", set()

        row = entitlement_service.active_license_row(self._session)
        if row is None:
            return "missing", set()

        if str(row.license_status or "").lower() in {"expired", "revoked"}:
            return "expired", set()

        features: set[str] = set(CANONICAL_FEATURES)
        if self._reverify_license and row.signed_license:
            try:
                keys = entitlement_service.public_keys_by_id()
                verified = parse_and_verify(
                    row.signed_license,
                    public_keys_by_id=keys,
                    expected_major_version=entitlement_service.app_major_version(),
                )
                payload = verified.payload
                expires_raw = payload.get("expires_at") or payload.get("valid_until")
                if expires_raw:
                    expires_at = _parse_iso_datetime(str(expires_raw))
                    if expires_at is not None and expires_at <= _utc_now():
                        return "expired", set()
                raw_features = payload.get("features")
                if isinstance(raw_features, list) and raw_features:
                    features = {str(item) for item in raw_features}
            except LicenseError:
                return "invalid", set()
            except Exception:  # noqa: BLE001 — treat verify failure as invalid
                return "invalid", set()

        return "ok", features

    # -- evaluate -------------------------------------------------------------

    def evaluate_capability(
        self,
        capability_key: CapabilityKey | str,
        *,
        context: dict[str, Any] | None = None,
    ) -> CapabilityDecision:
        # Frontend-supplied allowed is never trusted.
        ctx = {k: v for k, v in (context or {}).items() if k != "allowed"}

        resolved = self._try_resolve(capability_key)
        if resolved is None:
            # Contract CapabilityKey cannot represent unknown ids; pass raw str
            # for diagnostics (runtime dataclass accepts it). API maps to 404.
            return CapabilityDecision(
                capability_key=str(capability_key),  # type: ignore[arg-type]
                allowed=False,
                reason_code=CapabilityReasonCode.CAPABILITY_UNKNOWN,
                availability=CapabilityAvailability.UNAVAILABLE,
                display_message=f"Unknown capability: {capability_key}",
                license_status="n/a",
                offline_status="n/a",
            )

        try:
            metadata = self.get_capability_metadata(resolved)
        except (KeyError, NarrativeCoreError):
            return CapabilityDecision(
                capability_key=resolved,
                allowed=False,
                reason_code=CapabilityReasonCode.CAPABILITY_UNKNOWN,
                availability=CapabilityAvailability.UNAVAILABLE,
                display_message=f"Unknown capability: {resolved.value}",
                license_status="n/a",
                offline_status="n/a",
            )

        modes = metadata.supported_modes

        # 1) shipped=false takes priority (preview_visible ≠ usable).
        if not metadata.shipped:
            preview_msg = (
                "Capability preview visible but not shipped"
                if metadata.preview_visible
                else "Capability not shipped"
            )
            return CapabilityDecision(
                capability_key=resolved,
                allowed=False,
                reason_code=CapabilityReasonCode.CAPABILITY_NOT_SHIPPED,
                availability=CapabilityAvailability.UNAVAILABLE,
                display_message=preview_msg,
                supported_modes=modes,
                license_status="n/a",
                offline_status="n/a",
                preview_only=bool(metadata.preview_visible),
                metadata=metadata,
            )

        license_status, licensed_features = self._evaluate_license(metadata, context=ctx)

        if metadata.requires_license:
            if license_status == "missing":
                return CapabilityDecision(
                    capability_key=resolved,
                    allowed=False,
                    reason_code=CapabilityReasonCode.CAPABILITY_NOT_LICENSED,
                    availability=metadata.availability,
                    display_message="License required",
                    supported_modes=modes,
                    license_status="missing",
                    metadata=metadata,
                )
            if license_status == "expired":
                return CapabilityDecision(
                    capability_key=resolved,
                    allowed=False,
                    reason_code=CapabilityReasonCode.CAPABILITY_LICENSE_EXPIRED,
                    availability=metadata.availability,
                    display_message="License expired",
                    supported_modes=modes,
                    license_status="expired",
                    metadata=metadata,
                )
            if license_status == "invalid":
                return CapabilityDecision(
                    capability_key=resolved,
                    allowed=False,
                    reason_code=CapabilityReasonCode.CAPABILITY_LICENSE_INVALID,
                    availability=metadata.availability,
                    display_message="License invalid",
                    supported_modes=modes,
                    license_status="invalid",
                    metadata=metadata,
                )
            if resolved.value not in licensed_features and str(resolved) not in licensed_features:
                return CapabilityDecision(
                    capability_key=resolved,
                    allowed=False,
                    reason_code=CapabilityReasonCode.CAPABILITY_NOT_LICENSED,
                    availability=metadata.availability,
                    display_message="Feature not included in license",
                    supported_modes=modes,
                    license_status="missing",
                    metadata=metadata,
                )

        # Offline gate (optional).
        if not metadata.offline_allowed and ctx.get("offline") is True:
            return CapabilityDecision(
                capability_key=resolved,
                allowed=False,
                reason_code=CapabilityReasonCode.CAPABILITY_OFFLINE_NOT_ALLOWED,
                availability=metadata.availability,
                display_message="Offline use not allowed",
                supported_modes=modes,
                license_status=license_status if metadata.requires_license else "n/a",
                offline_status="offline",
                metadata=metadata,
            )

        quota = self.evaluate_quota(resolved, context=ctx)
        if not quota.allowed:
            return CapabilityDecision(
                capability_key=resolved,
                allowed=False,
                reason_code=CapabilityReasonCode.CAPABILITY_QUOTA_EXCEEDED,
                availability=metadata.availability,
                display_message=quota.message or "Quota exceeded",
                supported_modes=modes,
                quota=quota,
                usage=quota.used,
                remaining=quota.remaining,
                license_status=license_status if metadata.requires_license else "n/a",
                offline_status="online",
                metadata=metadata,
            )

        if metadata.availability == CapabilityAvailability.PREVIEW:
            return CapabilityDecision(
                capability_key=resolved,
                allowed=True,
                reason_code=CapabilityReasonCode.CAPABILITY_PREVIEW_ONLY,
                availability=CapabilityAvailability.PREVIEW,
                display_message="Preview only",
                supported_modes=modes,
                quota=quota,
                usage=quota.used,
                remaining=quota.remaining,
                preview_only=True,
                license_status=license_status if metadata.requires_license else "n/a",
                offline_status="online",
                metadata=metadata,
            )

        return CapabilityDecision(
            capability_key=resolved,
            allowed=True,
            reason_code=CapabilityReasonCode.CAPABILITY_AVAILABLE,
            availability=CapabilityAvailability.AVAILABLE,
            display_message="Available",
            supported_modes=modes,
            quota=quota,
            usage=quota.used,
            remaining=quota.remaining,
            license_status=license_status if metadata.requires_license else "n/a",
            offline_status="online",
            metadata=metadata,
        )

    def require_capability(
        self,
        capability_key: CapabilityKey | str,
        *,
        context: dict[str, Any] | None = None,
    ) -> CapabilityDecision:
        decision = self.evaluate_capability(capability_key, context=context)
        if decision.reason_code == CapabilityReasonCode.CAPABILITY_UNKNOWN:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED,
                decision.display_message or "Unknown capability",
            )
        if not decision.allowed:
            code = NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED
            if decision.reason_code == CapabilityReasonCode.CAPABILITY_QUOTA_EXCEEDED:
                code = NarrativeCoreErrorCode.WHOLE_BOOK_QUOTA_EXCEEDED
            raise NarrativeCoreError(code, decision.display_message or decision.reason_code.value)
        return decision

    def evaluate_mode(
        self,
        capability_key: CapabilityKey | str,
        mode: WholeBookAnalysisMode | str,
    ) -> CapabilityDecision:
        resolved = self._try_resolve(capability_key)
        if resolved is None:
            return CapabilityDecision(
                capability_key=CapabilityKey.WHOLE_BOOK_ANALYSIS,
                allowed=False,
                reason_code=CapabilityReasonCode.CAPABILITY_UNKNOWN,
                availability=CapabilityAvailability.UNAVAILABLE,
                display_message=f"Unknown capability: {capability_key}",
            )

        metadata = self.get_capability_metadata(resolved)
        try:
            mode_resolved = (
                mode if isinstance(mode, WholeBookAnalysisMode) else WholeBookAnalysisMode(str(mode))
            )
        except ValueError:
            return CapabilityDecision(
                capability_key=resolved,
                allowed=False,
                reason_code=CapabilityReasonCode.CAPABILITY_MODE_NOT_SUPPORTED,
                availability=metadata.availability,
                display_message=f"分析模式不受支持: {mode}",
                supported_modes=metadata.supported_modes,
                metadata=metadata,
            )

        if mode_resolved not in metadata.supported_modes:
            return CapabilityDecision(
                capability_key=resolved,
                allowed=False,
                reason_code=CapabilityReasonCode.CAPABILITY_MODE_NOT_SUPPORTED,
                availability=metadata.availability,
                display_message=(
                    f"分析模式不受支持: {mode_resolved.value}（该能力仅支持 "
                    f"{', '.join(m.value for m in metadata.supported_modes)}）"
                ),
                supported_modes=metadata.supported_modes,
                metadata=metadata,
            )

        base = self.evaluate_capability(resolved)
        if not base.allowed:
            return base
        return replace(base, display_message=f"Mode {mode_resolved.value} supported")

    def evaluate_quota(
        self,
        capability_key: CapabilityKey | str,
        *,
        context: dict[str, Any] | None = None,
    ) -> QuotaDecision:
        return self._quota.evaluate_quota(capability_key, context=context)

    def reserve_usage(
        self,
        capability_key: CapabilityKey | str,
        *,
        amount: int | float = 1,
        context: dict[str, Any] | None = None,
    ) -> QuotaDecision:
        return self._quota.reserve_usage(capability_key, amount=amount, context=context)

    def release_usage(
        self,
        capability_key: CapabilityKey | str,
        *,
        reservation_id: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self._quota.release_usage(
            capability_key, reservation_id=reservation_id, context=context
        )

    def commit_usage(
        self,
        capability_key: CapabilityKey | str,
        *,
        reservation_id: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self._quota.commit_usage(
            capability_key, reservation_id=reservation_id, context=context
        )


def _parse_iso_datetime(raw: str) -> datetime | None:
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def decision_to_compat_gate(
    decision: CapabilityDecision,
    *,
    feature_key: str,
    license_id: str | None = None,
    major_version: int | None = None,
    edition: str = "free",
) -> dict[str, Any]:
    """Map CapabilityDecision → legacy can_use_feature response shape.

    Compatibility semantics: ``enabled`` reflects License entitlement for the
    feature key, not full shipped/quota gate. NOT_SHIPPED with a valid license
    still returns enabled=True so existing Pro activation UX keeps working.
    Unknown keys never silently authorize.
    """

    reason_code = decision.reason_code
    if reason_code == CapabilityReasonCode.CAPABILITY_UNKNOWN:
        return {
            "enabled": False,
            "reason": "FEATURE_UNKNOWN",
            "source": "none",
            "edition": edition,
            "license_id": None,
            "major_version": None,
            "feature_key": feature_key,
            "capability_reason_code": reason_code.value,
        }

    licensed_ok = decision.license_status in {"ok", "n/a"} and reason_code not in {
        CapabilityReasonCode.CAPABILITY_NOT_LICENSED,
        CapabilityReasonCode.CAPABILITY_LICENSE_EXPIRED,
        CapabilityReasonCode.CAPABILITY_LICENSE_INVALID,
    }
    # When only blocker is not-shipped / quota, legacy gate still reports license.
    if reason_code == CapabilityReasonCode.CAPABILITY_NOT_SHIPPED:
        # Re-check via license_status on decision when evaluate short-circuited
        # before license — treat as "license unknown here"; caller may pass snap.
        pass

    if reason_code in {
        CapabilityReasonCode.CAPABILITY_NOT_LICENSED,
    }:
        return {
            "enabled": False,
            "reason": "PRO_LICENSE_REQUIRED",
            "source": "none",
            "edition": edition,
            "license_id": None,
            "major_version": None,
            "feature_key": feature_key,
            "capability_reason_code": reason_code.value,
        }
    if reason_code == CapabilityReasonCode.CAPABILITY_LICENSE_EXPIRED:
        return {
            "enabled": False,
            "reason": "LICENSE_EXPIRED",
            "source": "none",
            "edition": edition,
            "license_id": license_id,
            "major_version": major_version,
            "feature_key": feature_key,
            "capability_reason_code": reason_code.value,
        }
    if reason_code == CapabilityReasonCode.CAPABILITY_LICENSE_INVALID:
        return {
            "enabled": False,
            "reason": "LICENSE_INVALID",
            "source": "none",
            "edition": edition,
            "license_id": None,
            "major_version": None,
            "feature_key": feature_key,
            "capability_reason_code": reason_code.value,
        }

    # Available / preview / not_shipped / quota — license held.
    if decision.allowed or reason_code in {
        CapabilityReasonCode.CAPABILITY_NOT_SHIPPED,
        CapabilityReasonCode.CAPABILITY_QUOTA_EXCEEDED,
        CapabilityReasonCode.CAPABILITY_OFFLINE_NOT_ALLOWED,
        CapabilityReasonCode.CAPABILITY_PREVIEW_ONLY,
        CapabilityReasonCode.CAPABILITY_AVAILABLE,
    }:
        # For NOT_SHIPPED the evaluate path sets license_status=n/a; caller
        # must supply edition/license from entitlement snapshot for enabled.
        if reason_code == CapabilityReasonCode.CAPABILITY_NOT_SHIPPED and edition != "pro":
            return {
                "enabled": False,
                "reason": "PRO_LICENSE_REQUIRED",
                "source": "none",
                "edition": edition,
                "license_id": None,
                "major_version": None,
                "feature_key": feature_key,
                "capability_reason_code": reason_code.value,
            }
        if reason_code == CapabilityReasonCode.CAPABILITY_NOT_SHIPPED and edition == "pro":
            return {
                "enabled": True,
                "reason": None,
                "source": "signed_local_license",
                "edition": edition,
                "license_id": license_id,
                "major_version": major_version,
                "feature_key": feature_key,
                "capability_reason_code": reason_code.value,
            }
        if decision.allowed or licensed_ok:
            return {
                "enabled": True,
                "reason": None,
                "source": "signed_local_license",
                "edition": edition,
                "license_id": license_id,
                "major_version": major_version,
                "feature_key": feature_key,
                "capability_reason_code": reason_code.value,
            }

    return {
        "enabled": False,
        "reason": "PRO_LICENSE_REQUIRED",
        "source": "none",
        "edition": edition,
        "license_id": None,
        "major_version": None,
        "feature_key": feature_key,
        "capability_reason_code": reason_code.value,
    }


def make_shipped_test_metadata(
    key: CapabilityKey,
    *,
    requires_license: bool = True,
    preview_visible: bool = False,
    availability: CapabilityAvailability = CapabilityAvailability.AVAILABLE,
    supported_modes: tuple[WholeBookAnalysisMode, ...] = (),
    quota_policies: tuple = (),
) -> CapabilityMetadata:
    """Helper for tests: clone registry row with shipped=True."""

    base = registry_get_metadata(key)
    return CapabilityMetadata(
        key=base.key,
        display_name=base.display_name,
        description=base.description,
        shipped=True,
        requires_license=requires_license,
        availability=availability,
        preview_visible=preview_visible,
        supported_modes=supported_modes or base.supported_modes,
        quota_policy_key=base.quota_policy_key,
        estimated_cost_class=base.estimated_cost_class,
        quota_policies=quota_policies or base.quota_policies,
        offline_allowed=base.offline_allowed,
    )


def assert_foundation_not_pro_gated() -> None:
    """Invariant: narrative_asset_library must not be Pro-gated at API layer."""

    assert not is_pro_gated_capability(CapabilityKey.NARRATIVE_ASSET_LIBRARY)
    assert CapabilityKey.NARRATIVE_ASSET_LIBRARY in CAPABILITY_REGISTRY
