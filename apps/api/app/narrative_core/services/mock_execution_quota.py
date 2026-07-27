"""Mock execution quota / budget guards (Phase 2A Agent O).

Synthetic Lab limits only. Not commercial billing. Not License.
Not Cloud Budget. Does not persist across process restart.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from app.narrative_core.run_shell_contract.errors import MockRunErrorCode
from app.narrative_core.run_shell_contract.quota import (
    DEFAULT_MOCK_EXECUTION_QUOTA_POLICY,
    MockBudgetGuardDecision,
    MockExecutionQuotaPolicy,
    deny_budget_at_stage,
)
from app.narrative_core.services.mock_run_idempotency import MockRunConcurrencyGuard


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class MockQuotaReservation:
    reservation_id: str
    run_id: int | None
    book_id: int | None
    chapters: int
    characters: int
    synthetic_tokens: int
    synthetic_cost: float
    duration_seconds: int
    concurrent_slots: int
    status: str  # reserved | committed | released
    created_at: str = field(default_factory=_utc_now_iso)


@dataclass(frozen=True, slots=True)
class MockQuotaUsageSnapshot:
    concurrent_mock_runs: int
    mock_chapters: int
    mock_characters: int
    synthetic_tokens: int
    synthetic_cost: float
    run_duration_seconds: int
    synthetic: bool = True
    persist_across_restart: bool = False


@dataclass(frozen=True, slots=True)
class MockQuotaDecision:
    allowed: bool
    reason_code: str | None
    reservation_id: str | None
    usage: MockQuotaUsageSnapshot
    synthetic: bool = True
    release_execution_slot_on_deny: bool = True
    write_assets_on_deny: bool = False


class MockExecutionQuotaService:
    """In-memory mock quota accounting (non-production, non-persistent)."""

    persist_across_restart = False
    writes_commercial_usage = False
    mutates_license = False
    separate_from_cloud_budget = True

    def __init__(
        self,
        *,
        policy: MockExecutionQuotaPolicy | None = None,
        concurrency_guard: MockRunConcurrencyGuard | None = None,
    ) -> None:
        self.policy = policy or DEFAULT_MOCK_EXECUTION_QUOTA_POLICY
        self._concurrency = concurrency_guard
        self._lock = threading.RLock()
        self._reservations: dict[str, MockQuotaReservation] = {}
        self._used = MockQuotaUsageSnapshot(
            concurrent_mock_runs=0,
            mock_chapters=0,
            mock_characters=0,
            synthetic_tokens=0,
            synthetic_cost=0.0,
            run_duration_seconds=0,
        )
        self._reserved_concurrent = 0
        self._reserved_chapters = 0
        self._reserved_characters = 0
        self._reserved_tokens = 0
        self._reserved_cost = 0.0
        self._reserved_duration = 0

    def clear(self) -> None:
        with self._lock:
            self._reservations.clear()
            self._used = MockQuotaUsageSnapshot(
                concurrent_mock_runs=0,
                mock_chapters=0,
                mock_characters=0,
                synthetic_tokens=0,
                synthetic_cost=0.0,
                run_duration_seconds=0,
            )
            self._reserved_concurrent = 0
            self._reserved_chapters = 0
            self._reserved_characters = 0
            self._reserved_tokens = 0
            self._reserved_cost = 0.0
            self._reserved_duration = 0

    def usage_snapshot(self) -> MockQuotaUsageSnapshot:
        with self._lock:
            return MockQuotaUsageSnapshot(
                concurrent_mock_runs=self._used.concurrent_mock_runs + self._reserved_concurrent,
                mock_chapters=self._used.mock_chapters + self._reserved_chapters,
                mock_characters=self._used.mock_characters + self._reserved_characters,
                synthetic_tokens=self._used.synthetic_tokens + self._reserved_tokens,
                synthetic_cost=self._used.synthetic_cost + self._reserved_cost,
                run_duration_seconds=self._used.run_duration_seconds + self._reserved_duration,
                synthetic=True,
                persist_across_restart=False,
            )

    def evaluate(
        self,
        *,
        chapters: int = 0,
        characters: int = 0,
        synthetic_tokens: int = 0,
        synthetic_cost: float = 0.0,
        duration_seconds: int = 0,
        concurrent_slots: int = 1,
    ) -> MockQuotaDecision:
        usage = self.usage_snapshot()
        checks = (
            (
                usage.concurrent_mock_runs + concurrent_slots
                <= self.policy.max_concurrent_mock_runs,
                "concurrent_mock_runs",
            ),
            (
                usage.mock_chapters + chapters <= self.policy.max_mock_chapters,
                "max_mock_chapters",
            ),
            (
                usage.mock_characters + characters <= self.policy.max_mock_characters,
                "max_mock_characters",
            ),
            (
                usage.synthetic_tokens + synthetic_tokens
                <= self.policy.max_synthetic_tokens,
                "max_synthetic_tokens",
            ),
            (
                usage.synthetic_cost + synthetic_cost <= self.policy.max_synthetic_cost + 1e-12,
                "max_synthetic_cost",
            ),
            (
                usage.run_duration_seconds + duration_seconds
                <= self.policy.max_run_duration_seconds,
                "max_run_duration",
            ),
        )
        for ok, reason in checks:
            if not ok:
                return MockQuotaDecision(
                    allowed=False,
                    reason_code=MockRunErrorCode.MOCK_RUN_BUDGET_EXCEEDED.value,
                    reservation_id=None,
                    usage=usage,
                    release_execution_slot_on_deny=True,
                    write_assets_on_deny=False,
                )
        return MockQuotaDecision(
            allowed=True,
            reason_code=None,
            reservation_id=None,
            usage=usage,
            write_assets_on_deny=False,
        )

    def reserve(
        self,
        *,
        run_id: int | None = None,
        book_id: int | None = None,
        chapters: int = 0,
        characters: int = 0,
        synthetic_tokens: int = 0,
        synthetic_cost: float = 0.0,
        duration_seconds: int = 0,
        concurrent_slots: int = 1,
        reservation_id: str | None = None,
    ) -> MockQuotaDecision:
        rid = reservation_id or uuid.uuid4().hex
        with self._lock:
            existing = self._reservations.get(rid)
            if existing is not None and existing.status == "reserved":
                return MockQuotaDecision(
                    allowed=True,
                    reason_code=None,
                    reservation_id=rid,
                    usage=self.usage_snapshot(),
                )
            decision = self.evaluate(
                chapters=chapters,
                characters=characters,
                synthetic_tokens=synthetic_tokens,
                synthetic_cost=synthetic_cost,
                duration_seconds=duration_seconds,
                concurrent_slots=concurrent_slots,
            )
            if not decision.allowed:
                if self._concurrency is not None and book_id is not None:
                    self._concurrency.release_book_slot(book_id=book_id, run_id=run_id)
                return decision
            self._reserved_concurrent += concurrent_slots
            self._reserved_chapters += chapters
            self._reserved_characters += characters
            self._reserved_tokens += synthetic_tokens
            self._reserved_cost += synthetic_cost
            self._reserved_duration += duration_seconds
            self._reservations[rid] = MockQuotaReservation(
                reservation_id=rid,
                run_id=run_id,
                book_id=book_id,
                chapters=chapters,
                characters=characters,
                synthetic_tokens=synthetic_tokens,
                synthetic_cost=synthetic_cost,
                duration_seconds=duration_seconds,
                concurrent_slots=concurrent_slots,
                status="reserved",
            )
            return MockQuotaDecision(
                allowed=True,
                reason_code=None,
                reservation_id=rid,
                usage=self.usage_snapshot(),
            )

    def commit(self, reservation_id: str) -> None:
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None or reservation.status in {"committed", "released"}:
                return
            self._move_reserved_to_used(reservation, commit=True)
            reservation.status = "committed"

    def release(self, reservation_id: str) -> None:
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None or reservation.status in {"committed", "released"}:
                return
            self._move_reserved_to_used(reservation, commit=False)
            reservation.status = "released"
            if self._concurrency is not None and reservation.book_id is not None:
                self._concurrency.release_book_slot(
                    book_id=reservation.book_id, run_id=reservation.run_id
                )

    def _move_reserved_to_used(self, reservation: MockQuotaReservation, *, commit: bool) -> None:
        self._reserved_concurrent = max(
            0, self._reserved_concurrent - reservation.concurrent_slots
        )
        self._reserved_chapters = max(0, self._reserved_chapters - reservation.chapters)
        self._reserved_characters = max(
            0, self._reserved_characters - reservation.characters
        )
        self._reserved_tokens = max(0, self._reserved_tokens - reservation.synthetic_tokens)
        self._reserved_cost = max(0.0, self._reserved_cost - reservation.synthetic_cost)
        self._reserved_duration = max(
            0, self._reserved_duration - reservation.duration_seconds
        )
        if commit:
            self._used = MockQuotaUsageSnapshot(
                concurrent_mock_runs=self._used.concurrent_mock_runs,
                mock_chapters=self._used.mock_chapters + reservation.chapters,
                mock_characters=self._used.mock_characters + reservation.characters,
                synthetic_tokens=self._used.synthetic_tokens + reservation.synthetic_tokens,
                synthetic_cost=self._used.synthetic_cost + reservation.synthetic_cost,
                run_duration_seconds=(
                    self._used.run_duration_seconds + reservation.duration_seconds
                ),
                synthetic=True,
                persist_across_restart=False,
            )


class MockExecutionBudgetGuard:
    """Pre-write budget gate. Deny must not write assets; may release slot."""

    def __init__(
        self,
        quota_service: MockExecutionQuotaService,
        *,
        deny_at_stage: str | None = None,
        concurrency_guard: MockRunConcurrencyGuard | None = None,
    ) -> None:
        self._quota = quota_service
        self._deny_at_stage = deny_at_stage
        self._concurrency = concurrency_guard or quota_service._concurrency
        self._asset_write_attempts: list[dict[str, Any]] = []
        self._asset_writes: list[dict[str, Any]] = []

    def clear(self) -> None:
        self._asset_write_attempts.clear()
        self._asset_writes.clear()

    def set_deny_at_stage(self, stage_key: str | None) -> None:
        self._deny_at_stage = stage_key

    def check_before_write(
        self,
        *,
        stage_key: str,
        run_id: int | None = None,
        book_id: int | None = None,
        synthetic_tokens: int = 0,
        synthetic_cost: float = 0.0,
    ) -> MockBudgetGuardDecision:
        if self._deny_at_stage and stage_key == self._deny_at_stage:
            decision = deny_budget_at_stage(stage_key)
            if decision.release_execution_slot_on_deny and self._concurrency is not None:
                self._concurrency.release_book_slot(book_id=book_id, run_id=run_id)
            return decision
        quota = self._quota.evaluate(
            synthetic_tokens=synthetic_tokens,
            synthetic_cost=synthetic_cost,
            concurrent_slots=0,
        )
        if not quota.allowed:
            if self._concurrency is not None:
                self._concurrency.release_book_slot(book_id=book_id, run_id=run_id)
            return MockBudgetGuardDecision(
                allowed=False,
                stage_key=stage_key,
                reason_code=MockRunErrorCode.MOCK_RUN_BUDGET_EXCEEDED.value,
                synthetic=True,
                release_execution_slot_on_deny=True,
                write_assets_on_deny=False,
            )
        return MockBudgetGuardDecision(
            allowed=True,
            stage_key=stage_key,
            reason_code=None,
            synthetic=True,
            release_execution_slot_on_deny=True,
            write_assets_on_deny=False,
        )

    def try_write_asset(
        self,
        *,
        stage_key: str,
        run_id: int,
        book_id: int | None = None,
        asset_key: str,
        payload_meta: Mapping[str, Any] | None = None,
    ) -> tuple[bool, MockBudgetGuardDecision]:
        """Attempt an asset write under budget guard. Denied writes are recorded but not applied."""
        attempt = {
            "stage_key": stage_key,
            "run_id": run_id,
            "asset_key": asset_key,
            "meta_keys": sorted((payload_meta or {}).keys()),
        }
        self._asset_write_attempts.append(attempt)
        decision = self.check_before_write(
            stage_key=stage_key, run_id=run_id, book_id=book_id
        )
        if not decision.allowed:
            return False, decision
        self._asset_writes.append(attempt)
        return True, decision

    @property
    def written_assets(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._asset_writes)

    @property
    def attempted_assets(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._asset_write_attempts)


__all__ = [
    "MockExecutionBudgetGuard",
    "MockExecutionQuotaService",
    "MockQuotaDecision",
    "MockQuotaReservation",
    "MockQuotaUsageSnapshot",
]
