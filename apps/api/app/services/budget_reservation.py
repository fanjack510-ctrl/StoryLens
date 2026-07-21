import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CloudBudgetReservation, RequestGateDecision
from app.services.cloud_budget import RequestBlockedError, active_reservation_remaining_totals
from app.services.staged_budget import BudgetAmounts, exceeded_dimensions


class InsufficientBudgetReservation(ValueError):
    def __init__(
        self,
        *,
        stage: str,
        required: BudgetAmounts,
        remaining: BudgetAmounts,
        exceeded: list[str],
        pricing_version: str | None = None,
    ) -> None:
        super().__init__("INSUFFICIENT_BUDGET_RESERVATION")
        self.stage = stage
        self.required = required
        self.remaining = remaining
        self.exceeded_dimensions = exceeded
        self.pricing_version = pricing_version

    def as_error_detail(self) -> dict[str, object]:
        return {
            "error_code": "INSUFFICIENT_BUDGET_RESERVATION",
            "message": "预计用量超出剩余云端预算",
            "stage": self.stage,
            "required": {
                "requests": self.required.requests,
                "tokens": self.required.tokens,
                "estimated_cost": self.required.estimated_cost,
            },
            "remaining": {
                "requests": self.remaining.requests,
                "tokens": self.remaining.tokens,
                "estimated_cost": self.remaining.estimated_cost,
            },
            "exceeded_dimensions": list(self.exceeded_dimensions),
            "pricing_version": self.pricing_version,
            "retryable": True,
            "user_action_hint": _hint(self.exceeded_dimensions, self.required, self.remaining),
            "details": {},
        }


def _hint(dims: list[str], required: BudgetAmounts, remaining: BudgetAmounts) -> str:
    parts: list[str] = []
    if "requests" in dims:
        parts.append(
            f"请求次数不足：预计需要{required.requests}次，当前剩余{remaining.requests}次。"
        )
    if "tokens" in dims:
        parts.append(
            f"Token不足：预计需要{required.tokens} Token，当前剩余{remaining.tokens} Token。"
        )
    if "estimated_cost" in dims:
        parts.append(
            f"费用不足：预计需要约{required.estimated_cost} CNY，"
            f"当前剩余约{remaining.estimated_cost} CNY。"
        )
    return " ".join(parts) or "请调整云端预算后重试。"


def active_reservation_totals(session: Session) -> tuple[int, int, float]:
    """Backward-compatible alias: returns active *remaining* totals."""
    return active_reservation_remaining_totals(session)


def available_remaining(
    *,
    remaining_requests: int,
    remaining_tokens: int,
    remaining_cost: float,
    reserved_requests: int,
    reserved_tokens: int,
    reserved_cost: float,
) -> BudgetAmounts:
    """available = usage_remaining - active_reservation_remaining (not initial)."""
    return BudgetAmounts(
        max(0, remaining_requests - reserved_requests),
        max(0, remaining_tokens - reserved_tokens),
        round(max(0.0, remaining_cost - reserved_cost), 6),
    )


def _assert_ledger_non_negative(reservation: CloudBudgetReservation) -> None:
    for name in (
        "remaining_requests",
        "consumed_requests",
        "released_requests",
        "remaining_tokens",
        "consumed_tokens",
        "released_tokens",
    ):
        if int(getattr(reservation, name)) < 0:
            raise RuntimeError(f"RESERVATION_LEDGER_NEGATIVE:{name}")
    for name in ("remaining_cost", "consumed_cost", "released_cost"):
        if float(getattr(reservation, name)) < -1e-9:
            raise RuntimeError(f"RESERVATION_LEDGER_NEGATIVE:{name}")


def _assert_ledger_identity(reservation: CloudBudgetReservation) -> None:
    if (
        int(reservation.remaining_requests)
        + int(reservation.consumed_requests)
        + int(reservation.released_requests)
        != int(reservation.reserved_requests)
    ):
        raise RuntimeError("RESERVATION_LEDGER_IDENTITY_REQUESTS")
    if (
        int(reservation.remaining_tokens)
        + int(reservation.consumed_tokens)
        + int(reservation.released_tokens)
        != int(reservation.reserved_tokens)
    ):
        raise RuntimeError("RESERVATION_LEDGER_IDENTITY_TOKENS")
    total_cost = (
        float(reservation.remaining_cost)
        + float(reservation.consumed_cost)
        + float(reservation.released_cost)
    )
    if abs(total_cost - float(reservation.reserved_cost)) > 1e-6:
        raise RuntimeError("RESERVATION_LEDGER_IDENTITY_COST")


def reserve_budget(
    session: Session,
    *,
    run_id: int | None,
    stage: str,
    required_requests: int,
    required_tokens: int,
    required_cost: float,
    remaining_requests: int,
    remaining_tokens: int,
    remaining_cost: float,
    expected_requests: int | None = None,
    worst_case_requests: int | None = None,
    pricing_version: str | None = None,
    ttl_minutes: int = 30,
) -> CloudBudgetReservation:
    now = datetime.now(timezone.utc)
    active_req, active_tok, active_cost = active_reservation_totals(session)
    remaining = available_remaining(
        remaining_requests=remaining_requests,
        remaining_tokens=remaining_tokens,
        remaining_cost=remaining_cost,
        reserved_requests=active_req,
        reserved_tokens=active_tok,
        reserved_cost=active_cost,
    )
    required = BudgetAmounts(required_requests, required_tokens, required_cost)
    exceeded = exceeded_dimensions(required, remaining)
    snapshot = {
        "stage": stage,
        "required_requests": required_requests,
        "required_tokens": required_tokens,
        "required_cost": required_cost,
        "remaining_requests": remaining.requests,
        "remaining_tokens": remaining.tokens,
        "remaining_cost": remaining.estimated_cost,
        "usage_remaining_requests": remaining_requests,
        "usage_remaining_tokens": remaining_tokens,
        "usage_remaining_cost": remaining_cost,
        "already_reserved_requests": active_req,
        "already_reserved_tokens": active_tok,
        "already_reserved_cost": active_cost,
        "exceeded_dimensions": exceeded,
        "pricing_version": pricing_version,
        "accounting": "committed=used+sum(active.remaining)",
    }
    allowed = not exceeded
    session.add(
        RequestGateDecision(
            run_id=run_id,
            allowed=allowed,
            reason_code="RESERVATION_ALLOWED" if allowed else "INSUFFICIENT_BUDGET_RESERVATION",
            budget_snapshot_json=json.dumps(snapshot, sort_keys=True),
            estimated_request_cost=required_cost,
        )
    )
    if not allowed:
        session.commit()
        raise InsufficientBudgetReservation(
            stage=stage,
            required=required,
            remaining=remaining,
            exceeded=exceeded,
            pricing_version=pricing_version,
        )
    existing_active = session.scalar(
        select(CloudBudgetReservation).where(
            CloudBudgetReservation.run_id == run_id,
            CloudBudgetReservation.stage == stage,
            CloudBudgetReservation.status == "active",
            CloudBudgetReservation.expires_at > now,
        )
    )
    if existing_active is not None:
        session.commit()
        return existing_active
    reservation = CloudBudgetReservation(
        run_id=run_id,
        stage=stage,
        reserved_requests=required_requests,
        reserved_tokens=required_tokens,
        reserved_cost=required_cost,
        remaining_requests=required_requests,
        consumed_requests=0,
        released_requests=0,
        remaining_tokens=required_tokens,
        consumed_tokens=0,
        released_tokens=0,
        remaining_cost=required_cost,
        consumed_cost=0.0,
        released_cost=0.0,
        expected_requests=expected_requests if expected_requests is not None else required_requests,
        worst_case_requests=(
            worst_case_requests if worst_case_requests is not None else required_requests
        ),
        status="active",
        expires_at=now + timedelta(minutes=ttl_minutes),
    )
    session.add(reservation)
    session.commit()
    session.refresh(reservation)
    return reservation


@dataclass
class CloudAttemptClaim:
    """One atomic request-slot claim for a single HTTP attempt."""

    run_id: int
    reservation_id: int | None
    claimed_from_reservation: bool
    requested_amount: int = 1


def _active_run_reservations(
    session: Session, run_id: int
) -> list[CloudBudgetReservation]:
    now = datetime.now(timezone.utc)
    return list(
        session.scalars(
            select(CloudBudgetReservation)
            .where(
                CloudBudgetReservation.run_id == run_id,
                CloudBudgetReservation.status == "active",
                CloudBudgetReservation.expires_at > now,
                CloudBudgetReservation.remaining_requests > 0,
            )
            .order_by(CloudBudgetReservation.id.asc())
        )
    )


def claim_cloud_request_slot(
    session: Session,
    *,
    run_id: int,
    available_requests: int,
    used_requests: int,
    daily_limit: int,
) -> CloudAttemptClaim:
    """Atomically claim one request slot before HTTP send.

    Prefer the current run's reservation remaining; otherwise require global
    available_requests >= 1 (re-check daily gate after reservation exhaustion).
    """
    for reservation in _active_run_reservations(session, run_id):
        if int(reservation.remaining_requests) < 1:
            continue
        reservation.remaining_requests = int(reservation.remaining_requests) - 1
        reservation.consumed_requests = int(reservation.consumed_requests) + 1
        _assert_ledger_non_negative(reservation)
        _assert_ledger_identity(reservation)
        session.commit()
        return CloudAttemptClaim(
            run_id=run_id,
            reservation_id=reservation.id,
            claimed_from_reservation=True,
            requested_amount=1,
        )

    if int(available_requests) < 1:
        raise RequestBlockedError(
            "CLOUD_BUDGET_EXCEEDED",
            details={
                "error_type": "RequestBlockedError",
                "error_code": "CLOUD_BUDGET_EXCEEDED",
                "used": used_requests,
                "used_requests": used_requests,
                "reserved_initial": None,
                "reserved_remaining": 0,
                "daily_limit": daily_limit,
                "requested_amount": 1,
                "run_id": run_id,
                "dimension": "requests",
            },
        )
    # Unreserved attempt still gated by daily available.
    return CloudAttemptClaim(
        run_id=run_id,
        reservation_id=None,
        claimed_from_reservation=False,
        requested_amount=1,
    )


def rollback_cloud_request_claim(session: Session, claim: CloudAttemptClaim | None) -> None:
    """Roll back a pre-HTTP claim. Idempotent when claim is None or already rolled back."""
    if claim is None or not claim.claimed_from_reservation or claim.reservation_id is None:
        return
    reservation = session.get(CloudBudgetReservation, claim.reservation_id)
    if reservation is None or reservation.status != "active":
        return
    # Avoid double-rollback: only reverse if consumed still covers this claim.
    if int(reservation.consumed_requests) < 1:
        return
    reservation.remaining_requests = int(reservation.remaining_requests) + 1
    reservation.consumed_requests = int(reservation.consumed_requests) - 1
    _assert_ledger_non_negative(reservation)
    _assert_ledger_identity(reservation)
    session.commit()


def settle_cloud_attempt_usage(
    session: Session,
    claim: CloudAttemptClaim | None,
    *,
    http_request_sent: bool,
    total_tokens: int | None,
    estimated_cost: float | None,
) -> None:
    """After HTTP outcome: keep request claim if sent; settle tokens/cost; else rollback."""
    if claim is None:
        return
    if not http_request_sent:
        rollback_cloud_request_claim(session, claim)
        return
    if not claim.claimed_from_reservation or claim.reservation_id is None:
        return
    reservation = session.get(CloudBudgetReservation, claim.reservation_id)
    if reservation is None or reservation.status != "active":
        return
    tokens = max(0, int(total_tokens or 0))
    cost = max(0.0, float(estimated_cost or 0.0))
    token_take = min(int(reservation.remaining_tokens), tokens)
    cost_take = min(float(reservation.remaining_cost), cost)
    reservation.remaining_tokens = int(reservation.remaining_tokens) - token_take
    reservation.consumed_tokens = int(reservation.consumed_tokens) + token_take
    reservation.remaining_cost = round(float(reservation.remaining_cost) - cost_take, 6)
    reservation.consumed_cost = round(float(reservation.consumed_cost) + cost_take, 6)
    _assert_ledger_non_negative(reservation)
    _assert_ledger_identity(reservation)
    # Caller typically commits with ModelInvocation; flush is enough if shared txn.
    session.flush()


def release_reservation(session: Session, reservation_id: int) -> None:
    reservation = session.get(CloudBudgetReservation, reservation_id)
    if reservation is None:
        return
    if reservation.status != "active":
        return  # idempotent
    # Release only remaining; consumed stays consumed.
    reservation.released_requests = int(reservation.released_requests) + int(
        reservation.remaining_requests
    )
    reservation.released_tokens = int(reservation.released_tokens) + int(
        reservation.remaining_tokens
    )
    reservation.released_cost = round(
        float(reservation.released_cost) + float(reservation.remaining_cost), 6
    )
    reservation.remaining_requests = 0
    reservation.remaining_tokens = 0
    reservation.remaining_cost = 0.0
    reservation.status = "released"
    reservation.released_at = datetime.now(timezone.utc)
    _assert_ledger_non_negative(reservation)
    _assert_ledger_identity(reservation)
    session.commit()


def release_run_reservation(
    session: Session, run_id: int, stage: str | None = None
) -> None:
    query = select(CloudBudgetReservation).where(
        CloudBudgetReservation.run_id == run_id,
        CloudBudgetReservation.status == "active",
    )
    if stage is not None:
        query = query.where(CloudBudgetReservation.stage == stage)
    reservations = list(session.scalars(query))
    now = datetime.now(timezone.utc)
    for reservation in reservations:
        reservation.released_requests = int(reservation.released_requests) + int(
            reservation.remaining_requests
        )
        reservation.released_tokens = int(reservation.released_tokens) + int(
            reservation.remaining_tokens
        )
        reservation.released_cost = round(
            float(reservation.released_cost) + float(reservation.remaining_cost), 6
        )
        reservation.remaining_requests = 0
        reservation.remaining_tokens = 0
        reservation.remaining_cost = 0.0
        reservation.status = "released"
        reservation.released_at = now
        _assert_ledger_non_negative(reservation)
        _assert_ledger_identity(reservation)
    if reservations:
        session.commit()
