"""In-memory Quota skeleton for Phase 1C (NON-PRODUCTION).

Does not persist to SQLite / payment tables. Test and local-dev only.
Cloud budget (cloud_budget / budget_reservation) remains a separate subsystem.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol

from app.narrative_core.capability_registry import get_capability_metadata
from app.narrative_core.contracts.capability import QuotaDecision, QuotaPolicy
from app.narrative_core.enums import CapabilityKey, CapabilityReasonCode, QuotaPolicyKind

QuotaStoreBackend = Literal["memory_non_production"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _day_reset_at(now: datetime | None = None) -> datetime:
    current = now or _utc_now()
    start = current.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return start + timedelta(days=1)


@dataclass
class QuotaReservation:
    reservation_id: str
    capability_key: str
    policy_key: str
    policy_kind: QuotaPolicyKind
    amount: float
    status: Literal["reserved", "committed", "released"]
    book_id: int | None = None
    created_at: datetime = field(default_factory=_utc_now)
    context_fingerprint: str = ""


@dataclass
class QuotaBucket:
    """used + reserved accounting for one policy scope."""

    used: float = 0.0
    reserved: float = 0.0

    @property
    def occupied(self) -> float:
        return self.used + self.reserved


class QuotaService(Protocol):
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


class InMemoryQuotaService:
    """NON-PRODUCTION in-memory quota accounting.

    Explicitly not backed by a payment or commercial quota database.
    ``backend`` is always ``memory_non_production``.
    """

    backend: QuotaStoreBackend = "memory_non_production"

    def __init__(
        self,
        *,
        policy_overrides: dict[str, tuple[QuotaPolicy, ...]] | None = None,
    ) -> None:
        self._policy_overrides = dict(policy_overrides or {})
        # key: (capability, policy_key, scope) → bucket
        self._buckets: dict[tuple[str, str, str], QuotaBucket] = {}
        self._reservations: dict[str, QuotaReservation] = {}

    def clear(self) -> None:
        """Drop all in-memory state (tests only)."""

        self._buckets.clear()
        self._reservations.clear()

    def set_policy_overrides(
        self, overrides: dict[str, tuple[QuotaPolicy, ...]] | None
    ) -> None:
        self._policy_overrides = dict(overrides or {})

    def _resolve_key(self, capability_key: CapabilityKey | str) -> str:
        if isinstance(capability_key, CapabilityKey):
            return capability_key.value
        return str(capability_key)

    def _policies_for(self, capability_key: str) -> tuple[QuotaPolicy, ...]:
        if capability_key in self._policy_overrides:
            return self._policy_overrides[capability_key]
        try:
            meta = get_capability_metadata(capability_key)
        except (KeyError, ValueError):
            return (
                QuotaPolicy(kind=QuotaPolicyKind.NONE, policy_key="quota_none", limit=None),
            )
        if meta.quota_policies:
            return meta.quota_policies
        return (
            QuotaPolicy(kind=QuotaPolicyKind.NONE, policy_key="quota_none", limit=None),
        )

    def _scope(
        self,
        policy: QuotaPolicy,
        *,
        context: dict[str, Any] | None,
    ) -> str:
        ctx = context or {}
        if policy.kind == QuotaPolicyKind.PER_BOOK:
            book_id = ctx.get("book_id")
            snapshot_id = ctx.get("book_snapshot_id")
            return f"book:{book_id}:snap:{snapshot_id}"
        if policy.kind == QuotaPolicyKind.PER_DAY:
            day = (_utc_now()).date().isoformat()
            return f"day:{day}"
        if policy.kind == QuotaPolicyKind.CONCURRENT_RUNS:
            return "concurrent:global"
        if policy.kind in {
            QuotaPolicyKind.CHARACTER_LIMIT,
            QuotaPolicyKind.TOKEN_BUDGET,
            QuotaPolicyKind.COST_BUDGET,
        }:
            book_id = ctx.get("book_id", "global")
            return f"{policy.kind.value}:{book_id}"
        return "none"

    def _requested_amount(
        self,
        policy: QuotaPolicy,
        *,
        amount: float,
        context: dict[str, Any] | None,
    ) -> float:
        ctx = context or {}
        if policy.kind == QuotaPolicyKind.CHARACTER_LIMIT:
            return float(ctx.get("character_count", amount))
        if policy.kind == QuotaPolicyKind.TOKEN_BUDGET:
            return float(ctx.get("token_count", amount))
        if policy.kind == QuotaPolicyKind.COST_BUDGET:
            return float(ctx.get("estimated_cost", amount))
        if policy.kind == QuotaPolicyKind.CONCURRENT_RUNS:
            return 1.0
        return float(amount)

    def _bucket(self, capability_key: str, policy: QuotaPolicy, scope: str) -> QuotaBucket:
        key = (capability_key, policy.policy_key, scope)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = QuotaBucket()
            self._buckets[key] = bucket
        return bucket

    def _decision_for_policy(
        self,
        capability_key: str,
        policy: QuotaPolicy,
        *,
        amount: float,
        context: dict[str, Any] | None,
    ) -> QuotaDecision:
        if policy.kind == QuotaPolicyKind.NONE:
            return QuotaDecision(
                allowed=True,
                reason_code=CapabilityReasonCode.CAPABILITY_AVAILABLE,
                policy_key=policy.policy_key,
                policy_kind=QuotaPolicyKind.NONE,
                limit=None,
                used=0,
                reserved=0,
                remaining=None,
                reset_at=None,
                message="No quota limit",
            )

        scope = self._scope(policy, context=context)
        bucket = self._bucket(capability_key, policy, scope)
        requested = self._requested_amount(policy, amount=amount, context=context)
        limit = policy.limit
        remaining: float | None
        if limit is None:
            remaining = None
            allowed = True
        else:
            remaining = float(limit) - bucket.occupied
            allowed = bucket.occupied + requested <= float(limit) + 1e-9

        reset_at: datetime | None = None
        if policy.kind == QuotaPolicyKind.PER_DAY:
            reset_at = _day_reset_at()
        elif policy.window_seconds:
            reset_at = _utc_now() + timedelta(seconds=int(policy.window_seconds))

        return QuotaDecision(
            allowed=allowed,
            reason_code=(
                CapabilityReasonCode.CAPABILITY_AVAILABLE
                if allowed
                else CapabilityReasonCode.CAPABILITY_QUOTA_EXCEEDED
            ),
            policy_key=policy.policy_key,
            policy_kind=policy.kind,
            limit=limit,
            used=bucket.used,
            reserved=bucket.reserved,
            remaining=remaining,
            reset_at=reset_at,
            message="" if allowed else f"Quota exceeded for {policy.policy_key}",
        )

    def evaluate_quota(
        self,
        capability_key: CapabilityKey | str,
        *,
        context: dict[str, Any] | None = None,
        amount: int | float = 1,
    ) -> QuotaDecision:
        key = self._resolve_key(capability_key)
        policies = self._policies_for(key)
        last = QuotaDecision(
            allowed=True,
            reason_code=CapabilityReasonCode.CAPABILITY_AVAILABLE,
            policy_kind=QuotaPolicyKind.NONE,
            message="No quota policy",
        )
        for policy in policies:
            decision = self._decision_for_policy(
                key, policy, amount=float(amount), context=context
            )
            last = decision
            if not decision.allowed:
                return decision
        return last

    def reserve_usage(
        self,
        capability_key: CapabilityKey | str,
        *,
        amount: int | float = 1,
        context: dict[str, Any] | None = None,
    ) -> QuotaDecision:
        key = self._resolve_key(capability_key)
        ctx = dict(context or {})
        # Idempotent re-reserve by reservation_id if caller retries.
        existing_id = str(ctx.get("reservation_id") or "").strip()
        if existing_id and existing_id in self._reservations:
            reservation = self._reservations[existing_id]
            if reservation.status == "reserved":
                return self.evaluate_quota(key, context=ctx, amount=amount)

        decision = self.evaluate_quota(key, context=ctx, amount=amount)
        if not decision.allowed:
            return decision

        # Reserve against every non-none policy that applies.
        reservation_id = existing_id or uuid.uuid4().hex
        primary_policy: QuotaPolicy | None = None
        for policy in self._policies_for(key):
            if policy.kind == QuotaPolicyKind.NONE:
                continue
            scope = self._scope(policy, context=ctx)
            bucket = self._bucket(key, policy, scope)
            requested = self._requested_amount(policy, amount=float(amount), context=ctx)
            bucket.reserved += requested
            primary_policy = primary_policy or policy

        if primary_policy is None:
            primary_policy = QuotaPolicy(kind=QuotaPolicyKind.NONE, policy_key="quota_none")

        self._reservations[reservation_id] = QuotaReservation(
            reservation_id=reservation_id,
            capability_key=key,
            policy_key=primary_policy.policy_key,
            policy_kind=primary_policy.kind,
            amount=float(amount),
            status="reserved",
            book_id=ctx.get("book_id"),
            context_fingerprint=str(ctx.get("fingerprint") or ""),
        )
        refreshed = self.evaluate_quota(key, context=ctx, amount=0)
        return QuotaDecision(
            allowed=True,
            reason_code=CapabilityReasonCode.CAPABILITY_AVAILABLE,
            policy_key=refreshed.policy_key or primary_policy.policy_key,
            policy_kind=refreshed.policy_kind,
            limit=refreshed.limit,
            used=refreshed.used,
            reserved=refreshed.reserved,
            remaining=refreshed.remaining,
            reset_at=refreshed.reset_at,
            message=f"reserved:{reservation_id}",
        )

    def _apply_release_or_commit(
        self,
        capability_key: CapabilityKey | str,
        *,
        reservation_id: str,
        context: dict[str, Any] | None,
        commit: bool,
    ) -> None:
        key = self._resolve_key(capability_key)
        reservation = self._reservations.get(reservation_id)
        if reservation is None:
            # Idempotent no-op for unknown / already-forgotten ids.
            return
        if reservation.capability_key != key:
            return
        if reservation.status in {"released", "committed"}:
            # Idempotent: second release/commit is a no-op.
            return

        ctx = dict(context or {})
        if reservation.book_id is not None and "book_id" not in ctx:
            ctx["book_id"] = reservation.book_id

        for policy in self._policies_for(key):
            if policy.kind == QuotaPolicyKind.NONE:
                continue
            scope = self._scope(policy, context=ctx)
            bucket = self._bucket(key, policy, scope)
            requested = self._requested_amount(
                policy, amount=reservation.amount, context=ctx
            )
            bucket.reserved = max(0.0, bucket.reserved - requested)
            if commit and policy.kind != QuotaPolicyKind.CONCURRENT_RUNS:
                bucket.used += requested

        reservation.status = "committed" if commit else "released"

    def release_usage(
        self,
        capability_key: CapabilityKey | str,
        *,
        reservation_id: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self._apply_release_or_commit(
            capability_key,
            reservation_id=reservation_id,
            context=context,
            commit=False,
        )

    def commit_usage(
        self,
        capability_key: CapabilityKey | str,
        *,
        reservation_id: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self._apply_release_or_commit(
            capability_key,
            reservation_id=reservation_id,
            context=context,
            commit=True,
        )


def extract_reservation_id(decision: QuotaDecision) -> str | None:
    """Parse reservation id from ``reserve_usage`` message ``reserved:<id>``."""

    msg = decision.message or ""
    if msg.startswith("reserved:"):
        return msg.split(":", 1)[1] or None
    return None
