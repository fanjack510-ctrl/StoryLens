"""Mock Run idempotency + concurrency guards (Phase 2A Agent O).

Process-local stores only. No new DB tables / migrations.
Schema Issue: AnalysisRun has no metadata_json column for durable
idempotency records — keys bind via client_request_id / in-memory
namespace when a run exists.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping

from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.errors import (
    MockRunError,
    MockRunErrorCode,
    mock_run_error,
)
from app.narrative_core.run_shell_contract.idempotency import (
    DEFAULT_MOCK_RUN_CONCURRENCY_POLICY,
    MockRunConcurrencyPolicy,
    occupies_active_slot,
)


class MockRunServiceError(Exception):
    """Raiseable wrapper around contract MockRunError (Agent O services)."""

    def __init__(self, error: MockRunError) -> None:
        self.error = error
        self.code = error.code
        super().__init__(error.message)


def raise_mock_run_error(code: MockRunErrorCode, **kwargs: object) -> None:
    raise MockRunServiceError(mock_run_error(code, **kwargs))

IDEMPOTENCY_STORE_SCHEMA = "mock_run_idempotency_store"
IDEMPOTENCY_STORE_VERSION = "1.0.0"

# Schema Issue for Integration / future persistence (no migration in Phase 2A).
SCHEMA_ISSUE_NO_RUN_METADATA_JSON = (
    "AnalysisRun lacks metadata_json/config_json; durable idempotency "
    "records cannot be persisted without a new column/migration. "
    "Phase 2A uses process-local store + optional client_request_id bind."
)


class IdempotencyNamespace(StrEnum):
    CREATE = "create"
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    RETRY = "retry"
    STAGE_COMPLETE = "stage_complete"
    ARTIFACT_WRITE = "artifact_write"
    ASSET_VERSION_WRITE = "asset_version_write"


class IdempotencyRecordStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    namespace: str
    key: str
    actor: str
    request_scope: str
    payload_fingerprint: str
    status: IdempotencyRecordStatus
    result: Mapping[str, Any]
    created_at: str
    updated_at: str
    run_id: int | None = None
    detail_code: str | None = None


@dataclass(frozen=True, slots=True)
class IdempotencyResolveResult:
    hit: bool
    conflict: bool
    record: IdempotencyRecord | None
    error_code: MockRunErrorCode | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fingerprint_payload(payload: Mapping[str, Any] | None) -> str:
    """Stable fingerprint of request payload. Never stores novel body."""
    data = dict(payload or {})
    forbidden = {
        "full_text",
        "novel_body",
        "prompt",
        "system_prompt",
        "api_key",
        "credential",
        "evidence_full_text",
    }
    cleaned = {k: v for k, v in data.items() if k not in forbidden}
    blob = json.dumps(cleaned, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def namespaced_key(
    namespace: IdempotencyNamespace | str,
    key: str,
    *,
    actor: str,
    request_scope: str,
) -> str:
    ns = str(namespace)
    raw = f"{ns}|{actor}|{request_scope}|{key.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class MockRunIdempotencyService:
    """In-memory idempotency registry for Mock Lab create/actions/writes."""

    schema = IDEMPOTENCY_STORE_SCHEMA
    version = IDEMPOTENCY_STORE_VERSION

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, IdempotencyRecord] = {}

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def register_create_request(
        self,
        *,
        idempotency_key: str,
        actor: str,
        request_scope: str,
        payload: Mapping[str, Any],
        run_id: int | None = None,
    ) -> IdempotencyRecord:
        return self._register(
            namespace=IdempotencyNamespace.CREATE,
            key=idempotency_key,
            actor=actor,
            request_scope=request_scope,
            payload=payload,
            run_id=run_id,
        )

    def resolve_create_request(
        self,
        *,
        idempotency_key: str,
        actor: str,
        request_scope: str,
        payload: Mapping[str, Any],
    ) -> IdempotencyResolveResult:
        return self._resolve(
            namespace=IdempotencyNamespace.CREATE,
            key=idempotency_key,
            actor=actor,
            request_scope=request_scope,
            payload=payload,
        )

    def register_operation(
        self,
        *,
        namespace: IdempotencyNamespace | str,
        idempotency_key: str,
        actor: str,
        request_scope: str,
        payload: Mapping[str, Any],
        run_id: int | None = None,
    ) -> IdempotencyRecord:
        return self._register(
            namespace=namespace,
            key=idempotency_key,
            actor=actor,
            request_scope=request_scope,
            payload=payload,
            run_id=run_id,
        )

    def resolve_operation(
        self,
        *,
        namespace: IdempotencyNamespace | str,
        idempotency_key: str,
        actor: str,
        request_scope: str,
        payload: Mapping[str, Any],
    ) -> IdempotencyResolveResult:
        return self._resolve(
            namespace=namespace,
            key=idempotency_key,
            actor=actor,
            request_scope=request_scope,
            payload=payload,
        )

    def mark_operation_completed(
        self,
        *,
        namespace: IdempotencyNamespace | str,
        idempotency_key: str,
        actor: str,
        request_scope: str,
        result: Mapping[str, Any],
        run_id: int | None = None,
    ) -> IdempotencyRecord:
        return self._mark(
            namespace=namespace,
            key=idempotency_key,
            actor=actor,
            request_scope=request_scope,
            status=IdempotencyRecordStatus.COMPLETED,
            result=result,
            run_id=run_id,
        )

    def mark_operation_failed(
        self,
        *,
        namespace: IdempotencyNamespace | str,
        idempotency_key: str,
        actor: str,
        request_scope: str,
        detail_code: str | None = None,
        run_id: int | None = None,
    ) -> IdempotencyRecord:
        return self._mark(
            namespace=namespace,
            key=idempotency_key,
            actor=actor,
            request_scope=request_scope,
            status=IdempotencyRecordStatus.FAILED,
            result={"ok": False},
            run_id=run_id,
            detail_code=detail_code,
        )

    def remember_stage_completion(
        self,
        *,
        run_id: int,
        stage_key: str,
        attempt: int,
        artifact_id: int | None,
        actor: str = "executor",
    ) -> IdempotencyResolveResult:
        """Prevent duplicate stage completion / artifact writes on replay."""
        key = f"run:{run_id}:stage:{stage_key}:attempt:{attempt}"
        payload = {
            "run_id": run_id,
            "stage_key": stage_key,
            "attempt": attempt,
            "artifact_id": artifact_id,
        }
        resolved = self.resolve_operation(
            namespace=IdempotencyNamespace.STAGE_COMPLETE,
            idempotency_key=key,
            actor=actor,
            request_scope=f"run:{run_id}",
            payload=payload,
        )
        if resolved.hit or resolved.conflict:
            return resolved
        self.register_operation(
            namespace=IdempotencyNamespace.STAGE_COMPLETE,
            idempotency_key=key,
            actor=actor,
            request_scope=f"run:{run_id}",
            payload=payload,
            run_id=run_id,
        )
        self.mark_operation_completed(
            namespace=IdempotencyNamespace.STAGE_COMPLETE,
            idempotency_key=key,
            actor=actor,
            request_scope=f"run:{run_id}",
            result={"artifact_id": artifact_id, "written": True},
            run_id=run_id,
        )
        if artifact_id is not None:
            self.remember_artifact_write(
                run_id=run_id,
                stage_key=stage_key,
                attempt=attempt,
                artifact_id=artifact_id,
                actor=actor,
            )
        return IdempotencyResolveResult(hit=False, conflict=False, record=None)

    def remember_artifact_write(
        self,
        *,
        run_id: int,
        stage_key: str,
        attempt: int,
        artifact_id: int,
        actor: str = "executor",
    ) -> IdempotencyResolveResult:
        key = f"run:{run_id}:artifact:{stage_key}:{attempt}"
        payload = {
            "run_id": run_id,
            "stage_key": stage_key,
            "attempt": attempt,
            "artifact_id": artifact_id,
        }
        resolved = self.resolve_operation(
            namespace=IdempotencyNamespace.ARTIFACT_WRITE,
            idempotency_key=key,
            actor=actor,
            request_scope=f"run:{run_id}",
            payload=payload,
        )
        if resolved.hit or resolved.conflict:
            return resolved
        self.register_operation(
            namespace=IdempotencyNamespace.ARTIFACT_WRITE,
            idempotency_key=key,
            actor=actor,
            request_scope=f"run:{run_id}",
            payload=payload,
            run_id=run_id,
        )
        self.mark_operation_completed(
            namespace=IdempotencyNamespace.ARTIFACT_WRITE,
            idempotency_key=key,
            actor=actor,
            request_scope=f"run:{run_id}",
            result={"artifact_id": artifact_id, "written": True},
            run_id=run_id,
        )
        return IdempotencyResolveResult(hit=False, conflict=False, record=None)

    def remember_asset_version_write(
        self,
        *,
        run_id: int,
        asset_key: str,
        attempt: int,
        asset_version_id: int,
        actor: str = "executor",
    ) -> IdempotencyResolveResult:
        key = f"run:{run_id}:asset:{asset_key}:attempt:{attempt}"
        payload = {
            "run_id": run_id,
            "asset_key": asset_key,
            "attempt": attempt,
            "asset_version_id": asset_version_id,
        }
        resolved = self.resolve_operation(
            namespace=IdempotencyNamespace.ASSET_VERSION_WRITE,
            idempotency_key=key,
            actor=actor,
            request_scope=f"run:{run_id}",
            payload=payload,
        )
        if resolved.hit or resolved.conflict:
            return resolved
        self.register_operation(
            namespace=IdempotencyNamespace.ASSET_VERSION_WRITE,
            idempotency_key=key,
            actor=actor,
            request_scope=f"run:{run_id}",
            payload=payload,
            run_id=run_id,
        )
        self.mark_operation_completed(
            namespace=IdempotencyNamespace.ASSET_VERSION_WRITE,
            idempotency_key=key,
            actor=actor,
            request_scope=f"run:{run_id}",
            result={"asset_version_id": asset_version_id, "written": True},
            run_id=run_id,
        )
        return IdempotencyResolveResult(hit=False, conflict=False, record=None)

    def _storage_key(
        self,
        namespace: IdempotencyNamespace | str,
        key: str,
        *,
        actor: str,
        request_scope: str,
    ) -> str:
        if not key or not str(key).strip():
            raise ValueError("idempotency_key required")
        if not actor.strip():
            raise ValueError("actor required")
        if not request_scope.strip():
            raise ValueError("request_scope required")
        return namespaced_key(namespace, key, actor=actor, request_scope=request_scope)

    def _register(
        self,
        *,
        namespace: IdempotencyNamespace | str,
        key: str,
        actor: str,
        request_scope: str,
        payload: Mapping[str, Any],
        run_id: int | None,
    ) -> IdempotencyRecord:
        storage_key = self._storage_key(
            namespace, key, actor=actor, request_scope=request_scope
        )
        fp = fingerprint_payload(payload)
        now = _utc_now_iso()
        with self._lock:
            existing = self._records.get(storage_key)
            if existing is not None:
                if existing.payload_fingerprint != fp:
                    raise_mock_run_error(MockRunErrorCode.MOCK_RUN_IDEMPOTENCY_CONFLICT)
                return existing
            record = IdempotencyRecord(
                namespace=str(namespace),
                key=key.strip(),
                actor=actor,
                request_scope=request_scope,
                payload_fingerprint=fp,
                status=IdempotencyRecordStatus.IN_PROGRESS,
                result={},
                created_at=now,
                updated_at=now,
                run_id=run_id,
            )
            self._records[storage_key] = record
            return record

    def _resolve(
        self,
        *,
        namespace: IdempotencyNamespace | str,
        key: str,
        actor: str,
        request_scope: str,
        payload: Mapping[str, Any],
    ) -> IdempotencyResolveResult:
        storage_key = self._storage_key(
            namespace, key, actor=actor, request_scope=request_scope
        )
        fp = fingerprint_payload(payload)
        with self._lock:
            existing = self._records.get(storage_key)
            if existing is None:
                return IdempotencyResolveResult(hit=False, conflict=False, record=None)
            if existing.payload_fingerprint != fp:
                return IdempotencyResolveResult(
                    hit=False,
                    conflict=True,
                    record=existing,
                    error_code=MockRunErrorCode.MOCK_RUN_IDEMPOTENCY_CONFLICT,
                )
            return IdempotencyResolveResult(hit=True, conflict=False, record=existing)

    def _mark(
        self,
        *,
        namespace: IdempotencyNamespace | str,
        key: str,
        actor: str,
        request_scope: str,
        status: IdempotencyRecordStatus,
        result: Mapping[str, Any],
        run_id: int | None,
        detail_code: str | None = None,
    ) -> IdempotencyRecord:
        storage_key = self._storage_key(
            namespace, key, actor=actor, request_scope=request_scope
        )
        now = _utc_now_iso()
        with self._lock:
            existing = self._records.get(storage_key)
            if existing is None:
                record = IdempotencyRecord(
                    namespace=str(namespace),
                    key=key.strip(),
                    actor=actor,
                    request_scope=request_scope,
                    payload_fingerprint="",
                    status=status,
                    result=dict(result),
                    created_at=now,
                    updated_at=now,
                    run_id=run_id,
                    detail_code=detail_code,
                )
                self._records[storage_key] = record
                return record
            if existing.status == status and dict(existing.result) == dict(result):
                return existing
            updated = IdempotencyRecord(
                namespace=existing.namespace,
                key=existing.key,
                actor=existing.actor,
                request_scope=existing.request_scope,
                payload_fingerprint=existing.payload_fingerprint,
                status=status,
                result=dict(result),
                created_at=existing.created_at,
                updated_at=now,
                run_id=run_id if run_id is not None else existing.run_id,
                detail_code=detail_code,
            )
            self._records[storage_key] = updated
            return updated


@dataclass
class ConcurrencyReservation:
    book_id: int
    run_id: int | None
    reservation_id: str
    status: str  # reserved | released
    created_at: str


@dataclass
class ExecutorLease:
    run_id: int
    lease_id: str
    status: str  # held | released
    created_at: str


class MockRunConcurrencyGuard:
    """In-process concurrency guard: ≤1 active mock run/book; 1 executor/run."""

    def __init__(
        self,
        *,
        policy: MockRunConcurrencyPolicy = DEFAULT_MOCK_RUN_CONCURRENCY_POLICY,
    ) -> None:
        self.policy = policy
        self._lock = threading.RLock()
        self._book_slots: dict[int, ConcurrencyReservation] = {}
        self._executor_leases: dict[int, ExecutorLease] = {}
        self._reservation_by_id: dict[str, ConcurrencyReservation] = {}
        self._active_statuses: dict[int, str] = {}  # run_id -> status

    def clear(self) -> None:
        with self._lock:
            self._book_slots.clear()
            self._executor_leases.clear()
            self._reservation_by_id.clear()
            self._active_statuses.clear()

    def reserve_book_slot(
        self,
        *,
        book_id: int,
        run_id: int | None = None,
        reservation_id: str | None = None,
    ) -> ConcurrencyReservation:
        if book_id <= 0:
            raise ValueError("book_id must be positive")
        rid = reservation_id or f"book:{book_id}:{run_id or 'pending'}"
        now = _utc_now_iso()
        with self._lock:
            existing_by_id = self._reservation_by_id.get(rid)
            if existing_by_id is not None:
                return existing_by_id
            current = self._book_slots.get(book_id)
            if current is not None and current.status == "reserved":
                if run_id is not None and current.run_id == run_id:
                    return current
                raise_mock_run_error(MockRunErrorCode.MOCK_RUN_ALREADY_ACTIVE)
            reservation = ConcurrencyReservation(
                book_id=book_id,
                run_id=run_id,
                reservation_id=rid,
                status="reserved",
                created_at=now,
            )
            self._book_slots[book_id] = reservation
            self._reservation_by_id[rid] = reservation
            if run_id is not None:
                self._active_statuses[run_id] = WholeBookRunViewStatus.PENDING.value
            return reservation

    def bind_reservation_run(self, reservation_id: str, run_id: int) -> ConcurrencyReservation:
        with self._lock:
            reservation = self._reservation_by_id.get(reservation_id)
            if reservation is None:
                raise_mock_run_error(MockRunErrorCode.MOCK_RUN_NOT_FOUND)
            if reservation.run_id == run_id:
                return reservation
            updated = ConcurrencyReservation(
                book_id=reservation.book_id,
                run_id=run_id,
                reservation_id=reservation.reservation_id,
                status=reservation.status,
                created_at=reservation.created_at,
            )
            self._book_slots[reservation.book_id] = updated
            self._reservation_by_id[reservation_id] = updated
            self._active_statuses[run_id] = WholeBookRunViewStatus.PENDING.value
            return updated

    def release_book_slot(
        self,
        *,
        book_id: int | None = None,
        run_id: int | None = None,
        reservation_id: str | None = None,
    ) -> None:
        with self._lock:
            target: ConcurrencyReservation | None = None
            if reservation_id and reservation_id in self._reservation_by_id:
                target = self._reservation_by_id[reservation_id]
            elif run_id is not None:
                for item in self._book_slots.values():
                    if item.run_id == run_id:
                        target = item
                        break
            elif book_id is not None:
                target = self._book_slots.get(book_id)
            if target is None:
                return  # idempotent
            if target.status == "released":
                return
            released = ConcurrencyReservation(
                book_id=target.book_id,
                run_id=target.run_id,
                reservation_id=target.reservation_id,
                status="released",
                created_at=target.created_at,
            )
            self._reservation_by_id[target.reservation_id] = released
            current = self._book_slots.get(target.book_id)
            if current and current.reservation_id == target.reservation_id:
                del self._book_slots[target.book_id]
            if target.run_id is not None:
                self._active_statuses.pop(target.run_id, None)

    def note_run_status(self, run_id: int, status: WholeBookRunViewStatus | str) -> None:
        """Update occupancy from factual run status (failed does not occupy)."""
        status_value = WholeBookRunViewStatus(status)
        with self._lock:
            if occupies_active_slot(status_value, policy=self.policy):
                self._active_statuses[run_id] = status_value.value
            else:
                self._active_statuses.pop(run_id, None)
                # Release book slot when run leaves active set.
                for book_id, reservation in list(self._book_slots.items()):
                    if reservation.run_id == run_id:
                        self.release_book_slot(book_id=book_id, run_id=run_id)
                        break

    def acquire_executor(self, run_id: int, *, lease_id: str | None = None) -> ExecutorLease:
        lid = lease_id or f"executor:{run_id}"
        now = _utc_now_iso()
        with self._lock:
            existing = self._executor_leases.get(run_id)
            if existing is not None and existing.status == "held":
                if existing.lease_id == lid:
                    return existing
                raise_mock_run_error(
                    MockRunErrorCode.MOCK_RUN_STATE_CONFLICT,
                    detail_code="EXECUTOR_ALREADY_HELD",
                )
            lease = ExecutorLease(
                run_id=run_id, lease_id=lid, status="held", created_at=now
            )
            self._executor_leases[run_id] = lease
            return lease

    def release_executor(self, run_id: int, *, lease_id: str | None = None) -> None:
        with self._lock:
            existing = self._executor_leases.get(run_id)
            if existing is None:
                return
            if lease_id is not None and existing.lease_id != lease_id:
                return
            if existing.status == "released":
                return
            self._executor_leases[run_id] = ExecutorLease(
                run_id=run_id,
                lease_id=existing.lease_id,
                status="released",
                created_at=existing.created_at,
            )

    def has_active_book_run(self, book_id: int) -> bool:
        with self._lock:
            reservation = self._book_slots.get(book_id)
            return reservation is not None and reservation.status == "reserved"

    def executor_held(self, run_id: int) -> bool:
        with self._lock:
            lease = self._executor_leases.get(run_id)
            return lease is not None and lease.status == "held"


__all__ = [
    "SCHEMA_ISSUE_NO_RUN_METADATA_JSON",
    "IDEMPOTENCY_STORE_SCHEMA",
    "IDEMPOTENCY_STORE_VERSION",
    "IdempotencyNamespace",
    "IdempotencyRecord",
    "IdempotencyRecordStatus",
    "IdempotencyResolveResult",
    "MockRunConcurrencyGuard",
    "MockRunIdempotencyService",
    "MockRunServiceError",
    "ConcurrencyReservation",
    "ExecutorLease",
    "fingerprint_payload",
    "namespaced_key",
    "raise_mock_run_error",
]
