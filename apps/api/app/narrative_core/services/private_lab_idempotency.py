"""Private Lab create idempotency + concurrency guard (Phase 2B-R1 Agent V).

Process-local. No new tables/migrations. Distinct from Mock Lab stores.
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


class PrivateLabIdempotencyNamespace(StrEnum):
    CREATE = "create"
    CANCEL = "cancel"
    RESUME = "resume"
    RETRY = "retry"
    STAGE_COMPLETE = "stage_complete"


ACTIVE_SLOT_STATUSES: frozenset[str] = frozenset(
    {
        WholeBookRunViewStatus.PENDING.value,
        WholeBookRunViewStatus.RUNNING.value,
        WholeBookRunViewStatus.PAUSED.value,
        WholeBookRunViewStatus.INTERRUPTED.value,
    }
)


def occupies_active_slot(status: str) -> bool:
    return str(status) in ACTIVE_SLOT_STATUSES


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fingerprint_payload(payload: Mapping[str, Any] | None) -> str:
    data = dict(payload or {})
    forbidden = {
        "full_text",
        "novel_body",
        "prompt",
        "system_prompt",
        "api_key",
        "credential",
        "raw_response",
    }
    cleaned = {k: v for k, v in data.items() if k not in forbidden}
    blob = json.dumps(cleaned, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PrivateLabIdempotencyRecord:
    namespace: str
    key: str
    actor: str
    request_scope: str
    payload_fingerprint: str
    status: str
    result: Mapping[str, Any]
    created_at: str
    updated_at: str
    run_id: int | None = None


@dataclass(frozen=True, slots=True)
class PrivateLabIdempotencyResolveResult:
    hit: bool
    conflict: bool
    record: PrivateLabIdempotencyRecord | None


class PrivateLabCreateIdempotency:
    """Create + action idempotency for Private Lab."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, PrivateLabIdempotencyRecord] = {}

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def _namespaced(
        self, namespace: str, key: str, *, actor: str, request_scope: str
    ) -> str:
        raw = f"{namespace}|{actor}|{request_scope}|{key.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def resolve_create_request(
        self,
        *,
        idempotency_key: str,
        actor: str,
        request_scope: str,
        payload: Mapping[str, Any],
    ) -> PrivateLabIdempotencyResolveResult:
        ns_key = self._namespaced(
            PrivateLabIdempotencyNamespace.CREATE.value,
            idempotency_key,
            actor=actor,
            request_scope=request_scope,
        )
        fp = fingerprint_payload(payload)
        with self._lock:
            existing = self._records.get(ns_key)
            if existing is None:
                return PrivateLabIdempotencyResolveResult(hit=False, conflict=False, record=None)
            if existing.payload_fingerprint != fp:
                return PrivateLabIdempotencyResolveResult(hit=False, conflict=True, record=existing)
            return PrivateLabIdempotencyResolveResult(hit=True, conflict=False, record=existing)

    def register_create_request(
        self,
        *,
        idempotency_key: str,
        actor: str,
        request_scope: str,
        payload: Mapping[str, Any],
        run_id: int | None = None,
    ) -> PrivateLabIdempotencyRecord:
        ns_key = self._namespaced(
            PrivateLabIdempotencyNamespace.CREATE.value,
            idempotency_key,
            actor=actor,
            request_scope=request_scope,
        )
        now = _utc_now_iso()
        record = PrivateLabIdempotencyRecord(
            namespace=PrivateLabIdempotencyNamespace.CREATE.value,
            key=idempotency_key,
            actor=actor,
            request_scope=request_scope,
            payload_fingerprint=fingerprint_payload(payload),
            status="completed",
            result={"run_id": run_id} if run_id is not None else {},
            created_at=now,
            updated_at=now,
            run_id=run_id,
        )
        with self._lock:
            self._records[ns_key] = record
        return record

    def mark_operation_completed(
        self,
        *,
        namespace: PrivateLabIdempotencyNamespace | str,
        idempotency_key: str,
        actor: str,
        request_scope: str,
        result: Mapping[str, Any],
        run_id: int | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> PrivateLabIdempotencyRecord:
        ns = str(namespace)
        ns_key = self._namespaced(ns, idempotency_key, actor=actor, request_scope=request_scope)
        now = _utc_now_iso()
        record = PrivateLabIdempotencyRecord(
            namespace=ns,
            key=idempotency_key,
            actor=actor,
            request_scope=request_scope,
            payload_fingerprint=fingerprint_payload(payload or result),
            status="completed",
            result=dict(result),
            created_at=now,
            updated_at=now,
            run_id=run_id,
        )
        with self._lock:
            self._records[ns_key] = record
        return record


@dataclass(frozen=True, slots=True)
class PrivateLabConcurrencyReservation:
    reservation_id: str
    book_id: int
    run_id: int | None = None


class PrivateLabConcurrencyGuard:
    """≤1 active Private Lab run per book; 1 executor lease per run."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._book_slots: dict[int, str] = {}
        self._reservations: dict[str, PrivateLabConcurrencyReservation] = {}
        self._executor_leases: set[int] = set()
        self._run_status: dict[int, str] = {}

    def clear(self) -> None:
        with self._lock:
            self._book_slots.clear()
            self._reservations.clear()
            self._executor_leases.clear()
            self._run_status.clear()

    def reserve_book_slot(self, *, book_id: int) -> PrivateLabConcurrencyReservation:
        bid = int(book_id)
        with self._lock:
            if bid in self._book_slots:
                raise RuntimeError("PRIVATE_ENGINE_LAB_CONCURRENCY_LIMIT")
            rid = f"pelab-slot-{bid}-{len(self._reservations) + 1}"
            reservation = PrivateLabConcurrencyReservation(reservation_id=rid, book_id=bid)
            self._book_slots[bid] = rid
            self._reservations[rid] = reservation
            return reservation

    def bind_reservation_run(self, reservation_id: str, run_id: int) -> None:
        with self._lock:
            existing = self._reservations.get(reservation_id)
            if existing is None:
                return
            bound = PrivateLabConcurrencyReservation(
                reservation_id=reservation_id,
                book_id=existing.book_id,
                run_id=int(run_id),
            )
            self._reservations[reservation_id] = bound
            self._run_status[int(run_id)] = WholeBookRunViewStatus.PENDING.value

    def release_book_slot(self, *, book_id: int, reservation_id: str | None = None) -> None:
        bid = int(book_id)
        with self._lock:
            current = self._book_slots.get(bid)
            if current is None:
                return
            if reservation_id is not None and current != reservation_id:
                return
            self._book_slots.pop(bid, None)
            if current in self._reservations:
                res = self._reservations.pop(current)
                if res.run_id is not None:
                    self._run_status.pop(int(res.run_id), None)
                    self._executor_leases.discard(int(res.run_id))

    def note_run_status(self, run_id: int, status: str) -> None:
        with self._lock:
            self._run_status[int(run_id)] = str(status)
            if not occupies_active_slot(status):
                # Find and release book slot bound to this run.
                for bid, rid in list(self._book_slots.items()):
                    res = self._reservations.get(rid)
                    if res and res.run_id == int(run_id):
                        self.release_book_slot(book_id=bid, reservation_id=rid)
                        break

    def acquire_executor(self, run_id: int) -> bool:
        rid = int(run_id)
        with self._lock:
            if rid in self._executor_leases:
                return False
            self._executor_leases.add(rid)
            return True

    def release_executor(self, run_id: int) -> None:
        with self._lock:
            self._executor_leases.discard(int(run_id))


__all__ = [
    "ACTIVE_SLOT_STATUSES",
    "PrivateLabConcurrencyGuard",
    "PrivateLabConcurrencyReservation",
    "PrivateLabCreateIdempotency",
    "PrivateLabIdempotencyNamespace",
    "PrivateLabIdempotencyRecord",
    "PrivateLabIdempotencyResolveResult",
    "fingerprint_payload",
    "occupies_active_slot",
]
