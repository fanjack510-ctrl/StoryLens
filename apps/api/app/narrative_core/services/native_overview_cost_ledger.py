"""STEP 2.5 provider cost ledger helpers (project evidence only; no secrets)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_LEDGER = {
    "currency": "CNY",
    "absolute_limit_cny": 10.0,
    "execution_limit_cny": 9.0,
    "actual_cost_cny": 0.0,
    "reserved_cost_cny": 0.0,
    "attempts": [],
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        data = dict(DEFAULT_LEDGER)
        data["attempts"] = []
        path.parent.mkdir(parents=True, exist_ok=True)
        save_ledger(path, data)
        return data
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("attempts", [])
    return data


def save_ledger(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def worst_case_cost_cny(
    *,
    estimated_input_tokens: int,
    maximum_output_tokens: int,
    input_per_million: float,
    output_per_million: float,
) -> float:
    return (
        estimated_input_tokens * input_per_million / 1_000_000.0
        + maximum_output_tokens * output_per_million / 1_000_000.0
    )


def begin_attempt(
    ledger: dict[str, Any],
    *,
    attempt_id: str,
    run_id: str | None,
    stage_key: str,
    window_index: int | None,
    provider: str,
    model: str,
    estimated_input_tokens: int,
    maximum_output_tokens: int,
    input_price: float,
    output_price: float,
) -> dict[str, Any]:
    actual_before = float(ledger.get("actual_cost_cny") or 0.0)
    reserved_before = float(ledger.get("reserved_cost_cny") or 0.0)
    worst = worst_case_cost_cny(
        estimated_input_tokens=estimated_input_tokens,
        maximum_output_tokens=maximum_output_tokens,
        input_per_million=input_price,
        output_per_million=output_price,
    )
    projected = actual_before + reserved_before + worst
    limit = float(ledger.get("execution_limit_cny") or 9.0)
    allowed = projected <= limit + 1e-12
    row = {
        "attempt_id": attempt_id,
        "run_id": run_id,
        "stage_key": stage_key,
        "window_index": window_index,
        "provider": provider,
        "model": model,
        "estimated_input_tokens": estimated_input_tokens,
        "maximum_output_tokens": maximum_output_tokens,
        "input_price": input_price,
        "output_price": output_price,
        "worst_case_cost_cny": round(worst, 8),
        "actual_before_cny": round(actual_before, 8),
        "reserved_before_cny": round(reserved_before, 8),
        "projected_total_cny": round(projected, 8),
        "allowed": allowed,
        "created_at": utc_now_iso(),
        "status": "reserved" if allowed else "blocked",
    }
    if allowed:
        ledger["reserved_cost_cny"] = round(reserved_before + worst, 8)
    ledger["attempts"].append(row)
    return row


def finish_attempt(
    ledger: dict[str, Any],
    *,
    attempt_id: str,
    actual_input_tokens: int,
    actual_output_tokens: int,
    actual_cost_cny: float,
    status: str,
    error_code: str | None = None,
) -> dict[str, Any]:
    row = next(
        (a for a in ledger["attempts"] if a.get("attempt_id") == attempt_id),
        None,
    )
    if row is None:
        raise KeyError(attempt_id)
    reserved_delta = float(row.get("worst_case_cost_cny") or 0.0)
    if row.get("status") == "reserved":
        ledger["reserved_cost_cny"] = max(
            0.0, round(float(ledger.get("reserved_cost_cny") or 0.0) - reserved_delta, 8)
        )
    if status == "succeeded":
        ledger["actual_cost_cny"] = round(
            float(ledger.get("actual_cost_cny") or 0.0) + float(actual_cost_cny), 8
        )
    row.update(
        {
            "actual_input_tokens": actual_input_tokens,
            "actual_output_tokens": actual_output_tokens,
            "actual_cost_cny": round(float(actual_cost_cny), 8),
            "status": status,
            "error_code": error_code,
            "finished_at": utc_now_iso(),
            "cumulative_actual_cny": float(ledger.get("actual_cost_cny") or 0.0),
            "cumulative_reserved_cny": float(ledger.get("reserved_cost_cny") or 0.0),
        }
    )
    return row


__all__ = [
    "DEFAULT_LEDGER",
    "begin_attempt",
    "finish_attempt",
    "load_ledger",
    "save_ledger",
    "utc_now_iso",
    "worst_case_cost_cny",
]
