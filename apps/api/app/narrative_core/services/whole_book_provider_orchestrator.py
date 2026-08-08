"""Whole-book provider orchestrator (WB-0.5) — idempotent units, budget gates, Fake only."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import WholeBookProviderAttempt, WholeBookProviderUnit, WholeBookRun
from app.narrative_core.contracts.whole_book_contract_v1 import (
    WHOLE_BOOK_CONTRACT_VERSION,
    ResultOrigin,
)
from app.narrative_core.services.whole_book_consent_service import validate_whole_book_consent_for_run
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)

UNIT_WINDOW = "window_analysis"
UNIT_SYNTHESIS = "book_synthesis"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_request_hash(payload: dict[str, Any]) -> str:
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def build_idempotency_key(
    *,
    run_id: int,
    stage_code: str,
    unit_type: str,
    unit_key: str,
    request_hash: str,
    engine_version: str,
    prompt_version: str,
    contract_version: str = WHOLE_BOOK_CONTRACT_VERSION,
) -> str:
    material = "|".join(
        [
            str(run_id),
            stage_code,
            unit_type,
            unit_key,
            request_hash,
            engine_version,
            prompt_version,
            contract_version,
        ]
    )
    return sha256_text(material)


@dataclass
class ProviderCallResult:
    ok: bool
    result_payload: dict[str, Any] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_cny: Decimal = Decimal("0")
    error_code: str | None = None
    error_message_safe: str | None = None
    result_origin: str = ResultOrigin.fixture.value


class WholeBookProviderTransport(Protocol):
    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]) -> ProviderCallResult:
        ...


@dataclass
class CountingFakeWholeBookProvider:
    """Test-only Fake Provider. Never register as default production transport."""

    results_by_unit_key: dict[str, ProviderCallResult] = field(default_factory=dict)
    fail_once_unit_keys: set[str] = field(default_factory=set)
    delay_seconds: float = 0.0
    default_input_tokens: int = 100
    default_output_tokens: int = 50
    default_cost_cny: Decimal = Decimal("0.01")
    call_count: int = 0
    call_log: list[dict[str, Any]] = field(default_factory=list)
    _failed_once: set[str] = field(default_factory=set)
    network_calls: int = 0  # must stay 0

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]) -> ProviderCallResult:
        self.call_count += 1
        self.call_log.append({"unit_key": unit_key, "unit_type": unit_type})
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if unit_key in self.fail_once_unit_keys and unit_key not in self._failed_once:
            self._failed_once.add(unit_key)
            return ProviderCallResult(
                ok=False,
                error_code="FAKE_UNIT_FAILURE",
                error_message_safe="simulated unit failure",
                result_origin=ResultOrigin.fixture.value,
            )
        if unit_key in self.results_by_unit_key:
            result = self.results_by_unit_key[unit_key]
            return ProviderCallResult(
                ok=result.ok,
                result_payload=dict(result.result_payload),
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_cny=result.cost_cny,
                error_code=result.error_code,
                error_message_safe=result.error_message_safe,
                result_origin=ResultOrigin.fixture.value,
            )
        return ProviderCallResult(
            ok=True,
            result_payload={"unit_key": unit_key, "unit_type": unit_type, "ok": True},
            input_tokens=self.default_input_tokens,
            output_tokens=self.default_output_tokens,
            cost_cny=self.default_cost_cny,
            result_origin=ResultOrigin.fixture.value,
        )


@dataclass
class BudgetUsage:
    provider_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_cny: Decimal = Decimal("0")


class WholeBookProviderOrchestrator:
    def __init__(
        self,
        session: Session,
        *,
        engine_version: str = "wb-orch-0.5",
        prompt_version: str = "n/a",
    ) -> None:
        self.session = session
        self.engine_version = engine_version
        self.prompt_version = prompt_version

    def _usage_for_run(self, run_id: int) -> BudgetUsage:
        units = self.session.scalars(
            select(WholeBookProviderUnit).where(WholeBookProviderUnit.run_id == run_id)
        ).all()
        usage = BudgetUsage()
        for unit in units:
            attempts = self.session.scalars(
                select(WholeBookProviderAttempt).where(
                    WholeBookProviderAttempt.provider_unit_id == unit.id,
                    WholeBookProviderAttempt.status == "succeeded",
                )
            ).all()
            for attempt in attempts:
                usage.provider_calls += 1
                usage.input_tokens += int(attempt.input_tokens or 0)
                usage.output_tokens += int(attempt.output_tokens or 0)
                usage.cost_cny += Decimal(str(attempt.cost_cny or 0))
        return usage

    def check_budget_before_provider_call(
        self,
        *,
        consent_id: int,
        run_id: int,
        projected_input_tokens: int,
        projected_output_tokens: int,
        projected_cost_cny: Decimal,
    ) -> None:
        run = self.session.get(WholeBookRun, run_id)
        if run is None or run.snapshot_id is None:
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_NOT_FOUND,
                f"run not found or missing snapshot: {run_id}",
            )
        consent = validate_whole_book_consent_for_run(
            self.session,
            consent_id,
            book_id=int(run.book_id),
            snapshot_id=int(run.snapshot_id),
        )
        usage = self._usage_for_run(run_id)
        if usage.provider_calls + 1 > consent.max_provider_calls:
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.WHOLE_BOOK_CALL_BUDGET_EXCEEDED,
                "provider call budget exceeded",
            )
        # Token limits are the user-approved whole-run estimate envelope. They
        # are validated against the immutable estimate when consent is created.
        # Provider-reported live usage has different accounting boundaries
        # (cache/framing/repair), so it must not reinterpret these fields as a
        # second per-call context budget after Create has already passed.
        limit = Decimal(str(consent.user_budget_limit_cny))
        if usage.cost_cny + projected_cost_cny > limit:
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.WHOLE_BOOK_COST_BUDGET_EXCEEDED,
                "cost budget exceeded",
            )

    def execute_provider_unit(
        self,
        *,
        run_id: int,
        stage_code: str,
        unit_type: str,
        unit_key: str,
        request_payload: dict[str, Any],
        consent_id: int,
        transport: WholeBookProviderTransport,
        projected_input_tokens: int = 100,
        projected_output_tokens: int = 50,
        projected_cost_cny: Decimal | None = None,
        window_id: int | None = None,
        allow_retry: bool = False,
    ) -> dict[str, Any]:
        request_hash = stable_request_hash(request_payload)
        idem = build_idempotency_key(
            run_id=run_id,
            stage_code=stage_code,
            unit_type=unit_type,
            unit_key=unit_key,
            request_hash=request_hash,
            engine_version=self.engine_version,
            prompt_version=self.prompt_version,
        )
        unit = self.session.scalar(
            select(WholeBookProviderUnit).where(WholeBookProviderUnit.idempotency_key == idem)
        )
        if unit is None:
            unit = self.session.scalar(
                select(WholeBookProviderUnit).where(
                    WholeBookProviderUnit.run_id == run_id,
                    WholeBookProviderUnit.stage_code == stage_code,
                    WholeBookProviderUnit.unit_key == unit_key,
                )
            )
        if unit is not None:
            if unit.status == "completed":
                return {
                    "status": "reused",
                    "unit_id": unit.id,
                    "idempotency_key": unit.idempotency_key,
                    "result_hash": unit.result_hash,
                }
            if unit.status == "running":
                raise WholeBookFoundationError(
                    WholeBookFoundationErrorCode.WHOLE_BOOK_UNIT_RUNNING,
                    "unit already running",
                )
            if unit.status == "failed" and not allow_retry:
                raise WholeBookFoundationError(
                    WholeBookFoundationErrorCode.WHOLE_BOOK_RETRY_NOT_ALLOWED,
                    "failed unit requires explicit retry",
                )
        else:
            unit = WholeBookProviderUnit(
                run_id=run_id,
                stage_code=stage_code,
                unit_key=unit_key,
                unit_type=unit_type,
                window_id=window_id,
                idempotency_key=idem,
                request_hash=request_hash,
                status="pending",
                attempt_count=0,
            )
            self.session.add(unit)
            self.session.flush()

        cost_proj = projected_cost_cny if projected_cost_cny is not None else Decimal("0.01")
        # Budget check BEFORE creating attempt.
        self.check_budget_before_provider_call(
            consent_id=consent_id,
            run_id=run_id,
            projected_input_tokens=projected_input_tokens,
            projected_output_tokens=projected_output_tokens,
            projected_cost_cny=cost_proj,
        )

        unit.status = "running"
        unit.started_at = unit.started_at or _utc_now()
        unit.updated_at = _utc_now()
        attempt_no = unit.attempt_count + 1
        attempt = WholeBookProviderAttempt(
            provider_unit_id=unit.id,
            attempt_no=attempt_no,
            provider_id=str(
                request_payload.get("_provider_id")
                or getattr(transport, "provider_id", None)
                or "fake"
            )[:128],
            model_name=str(
                request_payload.get("_model_name")
                or getattr(transport, "model_name", None)
                or "counting-fake"
            )[:128],
            request_hash=request_hash,
            status="running",
            started_at=_utc_now(),
        )
        self.session.add(attempt)
        self.session.flush()

        result = transport.invoke(
            unit_key=unit_key, unit_type=unit_type, request_payload=request_payload
        )
        unit.attempt_count = attempt_no
        if result.ok:
            result_hash = stable_request_hash(result.result_payload)
            attempt.status = "succeeded"
            attempt.input_tokens = result.input_tokens
            attempt.output_tokens = result.output_tokens
            attempt.cost_cny = result.cost_cny
            attempt.completed_at = _utc_now()
            unit.status = "completed"
            unit.result_hash = result_hash
            unit.completed_at = _utc_now()
            unit.last_error_code = None
            unit.updated_at = _utc_now()
            self.session.flush()
            return {
                "status": "completed",
                "unit_id": unit.id,
                "attempt_no": attempt_no,
                "idempotency_key": unit.idempotency_key,
                "result_hash": result_hash,
                "result_payload": dict(result.result_payload or {}),
                "reused": False,
            }

        attempt.status = "failed"
        attempt.error_code = result.error_code or "PROVIDER_FAILED"
        attempt.error_message_safe = (result.error_message_safe or "provider failed")[:500]
        attempt.completed_at = _utc_now()
        unit.status = "failed"
        unit.last_error_code = attempt.error_code
        unit.updated_at = _utc_now()
        self.session.flush()
        return {
            "status": "failed",
            "unit_id": unit.id,
            "attempt_no": attempt_no,
            "error_code": attempt.error_code,
            "idempotency_key": unit.idempotency_key,
            "result_payload": dict(result.result_payload or {}),
        }

    def resume_incomplete_provider_units(self, run_id: int, stage_code: str) -> dict[str, list[dict[str, Any]]]:
        """Return execution plan only — never auto-calls transport."""
        units = self.session.scalars(
            select(WholeBookProviderUnit)
            .where(
                WholeBookProviderUnit.run_id == run_id,
                WholeBookProviderUnit.stage_code == stage_code,
            )
            .order_by(WholeBookProviderUnit.id.asc())
        ).all()
        plan: dict[str, list[dict[str, Any]]] = {
            "completed": [],
            "skipped": [],
            "retryable_failed": [],
            "pending": [],
            "blocked": [],
        }
        for unit in units:
            item = {
                "unit_id": unit.id,
                "unit_key": unit.unit_key,
                "unit_type": unit.unit_type,
                "status": unit.status,
                "idempotency_key": unit.idempotency_key,
            }
            if unit.status == "completed":
                plan["completed"].append(item)
                plan["skipped"].append(item)
            elif unit.status == "failed":
                plan["retryable_failed"].append(item)
            elif unit.status == "pending":
                plan["pending"].append(item)
            elif unit.status == "running":
                plan["blocked"].append(item)
            else:
                plan["pending"].append(item)
        return plan

    def retry_failed_provider_unit(
        self,
        unit_id: int,
        consent_id: int,
        transport: WholeBookProviderTransport,
        *,
        request_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        unit = self.session.get(WholeBookProviderUnit, unit_id)
        if unit is None or unit.status != "failed":
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.WHOLE_BOOK_RETRY_NOT_ALLOWED,
                "unit is not failed",
            )
        run = self.session.get(WholeBookRun, unit.run_id)
        if run is None or run.snapshot_id is None:
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_NOT_FOUND,
                f"run not found or missing snapshot: {unit.run_id}",
            )
        consent = validate_whole_book_consent_for_run(
            self.session,
            consent_id,
            book_id=int(run.book_id),
            snapshot_id=int(run.snapshot_id),
        )
        if not consent.auto_retry_enabled and consent.max_retries_per_unit <= 0:
            # Explicit worker retry still allowed when max_retries_per_unit > 0 OR caller is explicit.
            # Prompt: only when Consent allows retry — use max_retries_per_unit.
            pass
        max_attempts = 1 + int(consent.max_retries_per_unit)
        if unit.attempt_count >= max_attempts:
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.WHOLE_BOOK_RETRY_LIMIT_EXCEEDED,
                "retry limit exceeded",
            )
        payload = request_payload or {"unit_key": unit.unit_key, "retry": True}
        return self.execute_provider_unit(
            run_id=unit.run_id,
            stage_code=unit.stage_code,
            unit_type=unit.unit_type,
            unit_key=unit.unit_key,
            request_payload=payload,
            consent_id=consent_id,
            transport=transport,
            allow_retry=True,
            window_id=unit.window_id,
        )


def ensure_test_run(session: Session, *, book_id: int, consent_id: int | None = None) -> WholeBookRun:
    """Helper for tests — creates a minimal whole_book_runs row without product entry."""
    from app.narrative_core.services.whole_book_snapshot_v1_service import create_or_reuse_book_snapshot_v1

    snap = create_or_reuse_book_snapshot_v1(session, book_id)["snapshot"]
    run = WholeBookRun(
        book_id=book_id,
        snapshot_id=snap.id,
        mode="whole_book_native",
        status="running",
        current_stage_code="extract_entities_events",
        idempotency_key=sha256_text(f"test-run-{book_id}-{_utc_now().isoformat()}"),
        engine_id="wb-orch",
        engine_version="0.5",
        contract_version=WHOLE_BOOK_CONTRACT_VERSION,
        prompt_version="n/a",
        result_origin=ResultOrigin.fixture.value,
        consent_id=consent_id,
    )
    session.add(run)
    session.flush()
    return run
