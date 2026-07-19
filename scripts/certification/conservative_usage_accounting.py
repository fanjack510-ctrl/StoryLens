# -*- coding: utf-8 -*-
"""Certification-only conservative usage accounting (DEFECT-CANARY-013).

Does not mutate production ModelInvocation reported tokens/costs.
Used by the real canary runner and offline ledger replay.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRICING_PATH = ROOT / "config" / "cloud_pricing.json"

ACCOUNTING_REPORTED = "reported"
ACCOUNTING_CONSERVATIVE = "conservative_estimate"
ACCOUNTING_PROVIDER_ZERO = "provider_confirmed_zero"
ACCOUNTING_UNKNOWN = "unknown"

USAGE_PROVIDER_REPORTED = "provider_reported"
USAGE_CONSERVATIVE_UPPER = "conservative_upper_bound"
USAGE_PROVIDER_CONFIRMED_ZERO = "provider_confirmed_zero"
USAGE_UNKNOWN = "unknown"

REASON_DISCONNECT = "provider_disconnect_without_usage"
REASON_TRANSPORT_NO_USAGE = "transport_error_without_usage"
REASON_MISSING_INPUT_BASIS = "cannot_estimate_input_tokens"
REASON_MISSING_OUTPUT_CAP = "cannot_resolve_max_output_tokens"
REASON_MISSING_PRICING = "model_pricing_unavailable"
REASON_NONE = None


@dataclass(frozen=True)
class AttemptAccounting:
    reported_input_tokens: int | None
    reported_output_tokens: int | None
    reported_cost: float | None
    estimated_input_tokens: int | None
    estimated_output_tokens: int | None
    estimated_cost: float | None
    accounting_status: str
    usage_source: str
    estimate_reason: str | None
    reservation_amount: float | None
    settled_amount: float | None
    certification_cost: float
    certification_input_tokens: int
    certification_output_tokens: int
    http_request_sent: bool
    model_invocation_id: int | None = None
    model: str | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BatchAccountingSummary:
    actual_reported_cost: float
    conservative_estimated_cost: float
    certification_accounted_cost: float
    reported_input_tokens: int
    reported_output_tokens: int
    certification_input_tokens: int
    certification_output_tokens: int
    request_count: int
    unknown_count: int
    conservative_count: int
    reported_count: int
    attempts: tuple[AttemptAccounting, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["attempts"] = [a.to_dict() for a in self.attempts]
        return payload


def conservative_token_estimate(value: object) -> int:
    """Same heuristic as app.services.transition_batch_planner.conservative_token_estimate."""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    ascii_count = sum(ord(char) < 128 for char in text)
    non_ascii_count = len(text) - ascii_count
    return math.ceil(ascii_count / 4 + non_ascii_count) + 8


def estimate_input_tokens_upper_bound(
    *,
    input_snapshot: Mapping[str, Any] | None = None,
    request_payload: object | None = None,
    character_count: int | None = None,
) -> int | None:
    """Conservative input token upper bound from request content evidence."""
    if request_payload is not None:
        return conservative_token_estimate(request_payload)
    if input_snapshot:
        # Redacted cloud snapshot stores only character_count of the original JSON.
        keys = set(input_snapshot.keys())
        redacted = keys <= {"content_hash", "paragraph_ids", "character_count"}
        if not redacted:
            return conservative_token_estimate(dict(input_snapshot))
        cc = input_snapshot.get("character_count")
        if isinstance(cc, int) and cc >= 0:
            # Worst case: every character is a non-ASCII token + estimator overhead.
            return int(cc) + 8
    if isinstance(character_count, int) and character_count >= 0:
        return int(character_count) + 8
    return None


def resolve_max_output_tokens(
    *,
    requested_output_tokens: int | None = None,
    request_parameters: Mapping[str, Any] | None = None,
) -> int | None:
    if isinstance(requested_output_tokens, int) and requested_output_tokens > 0:
        return requested_output_tokens
    if request_parameters:
        for key in ("max_output_tokens", "effective_limit", "configured_limit"):
            value = request_parameters.get(key)
            if isinstance(value, int) and value > 0:
                return value
    return None


def load_model_pricing(
    model: str, pricing_path: Path = DEFAULT_PRICING_PATH
) -> tuple[float, float, str, str] | None:
    if not pricing_path.exists():
        return None
    try:
        config = json.loads(pricing_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    models = config.get("models")
    if not isinstance(models, dict):
        return None
    pricing = models.get(model)
    if not isinstance(pricing, dict):
        return None
    input_price = pricing.get("input_per_million")
    output_price = pricing.get("output_per_million")
    if not isinstance(input_price, (int, float)) or not isinstance(output_price, (int, float)):
        return None
    currency = str(config.get("currency") or "CNY")
    version = str(config.get("version") or "")
    return float(input_price), float(output_price), currency, version


def estimate_cost_cny(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    pricing_path: Path = DEFAULT_PRICING_PATH,
) -> float | None:
    pricing = load_model_pricing(model, pricing_path)
    if pricing is None:
        return None
    input_price, output_price, _currency, _version = pricing
    return input_tokens * input_price / 1_000_000 + output_tokens * output_price / 1_000_000


def _parse_json_mapping(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _provider_confirmed_zero(
    *,
    http_request_sent: bool,
    reported_input: int | None,
    reported_output: int | None,
    reported_cost: float | None,
    error_code: str | None,
    provider_confirmed_zero: bool,
) -> bool:
    if provider_confirmed_zero:
        return True
    # Never treat transport failures as confirmed-zero.
    if error_code and "DISCONNECT" in error_code.upper():
        return False
    if error_code and "TRANSPORT" in error_code.upper():
        return False
    if not http_request_sent and reported_input == 0 and reported_output == 0:
        return reported_cost in (0, 0.0, None)
    return False


def account_attempt(
    *,
    http_request_sent: bool,
    model: str | None,
    reported_input_tokens: int | None,
    reported_output_tokens: int | None,
    reported_cost: float | None,
    requested_output_tokens: int | None = None,
    request_parameters: Mapping[str, Any] | None = None,
    input_snapshot: Mapping[str, Any] | None = None,
    request_payload: object | None = None,
    character_count: int | None = None,
    error_code: str | None = None,
    reservation_amount: float | None = None,
    provider_confirmed_zero: bool = False,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    model_invocation_id: int | None = None,
) -> AttemptAccounting:
    """Classify one model attempt for certification accounting."""
    if not http_request_sent:
        # Pre-send failures are not certification spend.
        return AttemptAccounting(
            reported_input_tokens=reported_input_tokens,
            reported_output_tokens=reported_output_tokens,
            reported_cost=reported_cost,
            estimated_input_tokens=None,
            estimated_output_tokens=None,
            estimated_cost=None,
            accounting_status=ACCOUNTING_REPORTED
            if reported_input_tokens is not None and reported_output_tokens is not None
            else ACCOUNTING_PROVIDER_ZERO,
            usage_source=USAGE_PROVIDER_REPORTED
            if reported_input_tokens is not None
            else USAGE_PROVIDER_CONFIRMED_ZERO,
            estimate_reason=REASON_NONE,
            reservation_amount=reservation_amount,
            settled_amount=0.0,
            certification_cost=float(reported_cost or 0.0),
            certification_input_tokens=int(reported_input_tokens or 0),
            certification_output_tokens=int(reported_output_tokens or 0),
            http_request_sent=False,
            model_invocation_id=model_invocation_id,
            model=model,
            error_code=error_code,
        )

    if (
        reported_input_tokens is not None
        and reported_output_tokens is not None
    ):
        cost = float(reported_cost) if reported_cost is not None else 0.0
        if reported_cost is None and model:
            estimated = estimate_cost_cny(
                model=model,
                input_tokens=reported_input_tokens,
                output_tokens=reported_output_tokens,
                pricing_path=pricing_path,
            )
            if estimated is not None:
                cost = estimated
        return AttemptAccounting(
            reported_input_tokens=reported_input_tokens,
            reported_output_tokens=reported_output_tokens,
            reported_cost=reported_cost if reported_cost is not None else cost,
            estimated_input_tokens=None,
            estimated_output_tokens=None,
            estimated_cost=None,
            accounting_status=ACCOUNTING_REPORTED,
            usage_source=USAGE_PROVIDER_REPORTED,
            estimate_reason=REASON_NONE,
            reservation_amount=reservation_amount,
            settled_amount=cost,
            certification_cost=cost,
            certification_input_tokens=int(reported_input_tokens),
            certification_output_tokens=int(reported_output_tokens),
            http_request_sent=True,
            model_invocation_id=model_invocation_id,
            model=model,
            error_code=error_code,
        )

    if _provider_confirmed_zero(
        http_request_sent=http_request_sent,
        reported_input=reported_input_tokens,
        reported_output=reported_output_tokens,
        reported_cost=reported_cost,
        error_code=error_code,
        provider_confirmed_zero=provider_confirmed_zero,
    ):
        return AttemptAccounting(
            reported_input_tokens=reported_input_tokens,
            reported_output_tokens=reported_output_tokens,
            reported_cost=reported_cost,
            estimated_input_tokens=0,
            estimated_output_tokens=0,
            estimated_cost=0.0,
            accounting_status=ACCOUNTING_PROVIDER_ZERO,
            usage_source=USAGE_PROVIDER_CONFIRMED_ZERO,
            estimate_reason=REASON_NONE,
            reservation_amount=reservation_amount,
            settled_amount=0.0,
            certification_cost=0.0,
            certification_input_tokens=0,
            certification_output_tokens=0,
            http_request_sent=True,
            model_invocation_id=model_invocation_id,
            model=model,
            error_code=error_code,
        )

    # Missing reported usage — attempt conservative upper bound.
    est_in = estimate_input_tokens_upper_bound(
        input_snapshot=input_snapshot,
        request_payload=request_payload,
        character_count=character_count,
    )
    est_out = resolve_max_output_tokens(
        requested_output_tokens=requested_output_tokens,
        request_parameters=request_parameters,
    )
    reason = REASON_DISCONNECT if (error_code or "").endswith("DISCONNECT") else REASON_TRANSPORT_NO_USAGE

    if est_in is None:
        return AttemptAccounting(
            reported_input_tokens=reported_input_tokens,
            reported_output_tokens=reported_output_tokens,
            reported_cost=reported_cost,
            estimated_input_tokens=None,
            estimated_output_tokens=est_out,
            estimated_cost=None,
            accounting_status=ACCOUNTING_UNKNOWN,
            usage_source=USAGE_UNKNOWN,
            estimate_reason=REASON_MISSING_INPUT_BASIS,
            reservation_amount=reservation_amount,
            settled_amount=None,
            certification_cost=0.0,
            certification_input_tokens=0,
            certification_output_tokens=0,
            http_request_sent=True,
            model_invocation_id=model_invocation_id,
            model=model,
            error_code=error_code,
        )
    if est_out is None:
        return AttemptAccounting(
            reported_input_tokens=reported_input_tokens,
            reported_output_tokens=reported_output_tokens,
            reported_cost=reported_cost,
            estimated_input_tokens=est_in,
            estimated_output_tokens=None,
            estimated_cost=None,
            accounting_status=ACCOUNTING_UNKNOWN,
            usage_source=USAGE_UNKNOWN,
            estimate_reason=REASON_MISSING_OUTPUT_CAP,
            reservation_amount=reservation_amount,
            settled_amount=None,
            certification_cost=0.0,
            certification_input_tokens=0,
            certification_output_tokens=0,
            http_request_sent=True,
            model_invocation_id=model_invocation_id,
            model=model,
            error_code=error_code,
        )
    if not model:
        return AttemptAccounting(
            reported_input_tokens=reported_input_tokens,
            reported_output_tokens=reported_output_tokens,
            reported_cost=reported_cost,
            estimated_input_tokens=est_in,
            estimated_output_tokens=est_out,
            estimated_cost=None,
            accounting_status=ACCOUNTING_UNKNOWN,
            usage_source=USAGE_UNKNOWN,
            estimate_reason=REASON_MISSING_PRICING,
            reservation_amount=reservation_amount,
            settled_amount=None,
            certification_cost=0.0,
            certification_input_tokens=0,
            certification_output_tokens=0,
            http_request_sent=True,
            model_invocation_id=model_invocation_id,
            model=model,
            error_code=error_code,
        )
    est_cost = estimate_cost_cny(
        model=model,
        input_tokens=est_in,
        output_tokens=est_out,
        pricing_path=pricing_path,
    )
    if est_cost is None:
        return AttemptAccounting(
            reported_input_tokens=reported_input_tokens,
            reported_output_tokens=reported_output_tokens,
            reported_cost=reported_cost,
            estimated_input_tokens=est_in,
            estimated_output_tokens=est_out,
            estimated_cost=None,
            accounting_status=ACCOUNTING_UNKNOWN,
            usage_source=USAGE_UNKNOWN,
            estimate_reason=REASON_MISSING_PRICING,
            reservation_amount=reservation_amount,
            settled_amount=None,
            certification_cost=0.0,
            certification_input_tokens=0,
            certification_output_tokens=0,
            http_request_sent=True,
            model_invocation_id=model_invocation_id,
            model=model,
            error_code=error_code,
        )

    return AttemptAccounting(
        reported_input_tokens=reported_input_tokens,
        reported_output_tokens=reported_output_tokens,
        reported_cost=reported_cost,
        estimated_input_tokens=est_in,
        estimated_output_tokens=est_out,
        estimated_cost=est_cost,
        accounting_status=ACCOUNTING_CONSERVATIVE,
        usage_source=USAGE_CONSERVATIVE_UPPER,
        estimate_reason=reason,
        reservation_amount=reservation_amount,
        settled_amount=est_cost,
        certification_cost=est_cost,
        certification_input_tokens=est_in,
        certification_output_tokens=est_out,
        http_request_sent=True,
        model_invocation_id=model_invocation_id,
        model=model,
        error_code=error_code,
    )


def account_invocation_row(
    inv: Any,
    *,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    reservation_amount: float | None = None,
    provider_confirmed_zero: bool = False,
    request_payload: object | None = None,
) -> AttemptAccounting:
    """Account a SQLAlchemy ModelInvocation or duck-typed object."""
    snapshot = _parse_json_mapping(getattr(inv, "input_snapshot_json", None))
    params = _parse_json_mapping(getattr(inv, "request_parameters_json", None))
    return account_attempt(
        http_request_sent=bool(getattr(inv, "http_request_sent", False)),
        model=getattr(inv, "model_name", None) or getattr(inv, "model", None),
        reported_input_tokens=getattr(inv, "input_tokens", None),
        reported_output_tokens=getattr(inv, "output_tokens", None),
        reported_cost=getattr(inv, "estimated_cost", None),
        requested_output_tokens=getattr(inv, "requested_output_tokens", None),
        request_parameters=params,
        input_snapshot=snapshot,
        request_payload=request_payload,
        error_code=getattr(inv, "error_code", None),
        reservation_amount=reservation_amount,
        provider_confirmed_zero=provider_confirmed_zero,
        pricing_path=pricing_path,
        model_invocation_id=getattr(inv, "id", None),
    )


def summarize_attempts(attempts: list[AttemptAccounting]) -> BatchAccountingSummary:
    sent = [a for a in attempts if a.http_request_sent]
    reported_cost = sum(
        float(a.reported_cost or 0.0)
        for a in sent
        if a.accounting_status == ACCOUNTING_REPORTED and a.reported_cost is not None
    )
    # If reported tokens exist but reported_cost was derived, certification_cost already holds it.
    reported_cost = sum(
        a.certification_cost for a in sent if a.accounting_status == ACCOUNTING_REPORTED
    )
    conservative_cost = sum(
        float(a.estimated_cost or 0.0)
        for a in sent
        if a.accounting_status == ACCOUNTING_CONSERVATIVE
    )
    accounted = sum(a.certification_cost for a in sent if a.accounting_status != ACCOUNTING_UNKNOWN)
    return BatchAccountingSummary(
        actual_reported_cost=reported_cost,
        conservative_estimated_cost=conservative_cost,
        certification_accounted_cost=accounted,
        reported_input_tokens=sum(int(a.reported_input_tokens or 0) for a in sent),
        reported_output_tokens=sum(int(a.reported_output_tokens or 0) for a in sent),
        certification_input_tokens=sum(
            a.certification_input_tokens for a in sent if a.accounting_status != ACCOUNTING_UNKNOWN
        ),
        certification_output_tokens=sum(
            a.certification_output_tokens for a in sent if a.accounting_status != ACCOUNTING_UNKNOWN
        ),
        request_count=len(sent),
        unknown_count=sum(1 for a in sent if a.accounting_status == ACCOUNTING_UNKNOWN),
        conservative_count=sum(1 for a in sent if a.accounting_status == ACCOUNTING_CONSERVATIVE),
        reported_count=sum(1 for a in sent if a.accounting_status == ACCOUNTING_REPORTED),
        attempts=tuple(attempts),
    )


def account_invocations(
    invocations: list[Any],
    *,
    pricing_path: Path = DEFAULT_PRICING_PATH,
) -> BatchAccountingSummary:
    attempts = [
        account_invocation_row(inv, pricing_path=pricing_path)
        for inv in invocations
        if bool(getattr(inv, "http_request_sent", False))
    ]
    return summarize_attempts(attempts)


def has_unknown_accounting(summary: BatchAccountingSummary) -> bool:
    return summary.unknown_count > 0


def would_exceed_max_cost(
    summary: BatchAccountingSummary,
    *,
    max_cost_cny: float,
    next_request_conservative_budget: float = 0.0,
) -> bool:
    return summary.certification_accounted_cost + next_request_conservative_budget > max_cost_cny


def replay_run_invocations_from_sqlite(
    db_path: Path,
    *,
    analysis_run_id: int,
    pricing_path: Path = DEFAULT_PRICING_PATH,
) -> BatchAccountingSummary:
    """Offline replay for a historical canary analysis run (zero model calls)."""
    import sqlite3

    uri = db_path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    rows = list(
        con.execute(
            """
            SELECT id, model_name, input_tokens, output_tokens, estimated_cost,
                   requested_output_tokens, request_parameters_json, input_snapshot_json,
                   error_code, http_request_sent
            FROM model_invocations
            WHERE run_id = ? AND http_request_sent = 1
            ORDER BY id
            """,
            (analysis_run_id,),
        )
    )
    con.close()

    class _Row:
        def __init__(self, row: sqlite3.Row) -> None:
            self.id = row["id"]
            self.model_name = row["model_name"]
            self.input_tokens = row["input_tokens"]
            self.output_tokens = row["output_tokens"]
            self.estimated_cost = row["estimated_cost"]
            self.requested_output_tokens = row["requested_output_tokens"]
            self.request_parameters_json = row["request_parameters_json"]
            self.input_snapshot_json = row["input_snapshot_json"]
            self.error_code = row["error_code"]
            self.http_request_sent = bool(row["http_request_sent"])

    return account_invocations([_Row(r) for r in rows], pricing_path=pricing_path)
