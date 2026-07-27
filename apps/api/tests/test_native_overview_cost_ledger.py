"""Offline tests for STEP 2.5 cost ledger (no Live Provider)."""

from __future__ import annotations

from pathlib import Path

from app.narrative_core.services.native_overview_cost_ledger import (
    begin_attempt,
    finish_attempt,
    load_ledger,
    save_ledger,
    worst_case_cost_cny,
)


def test_worst_case_and_budget_gate(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = load_ledger(path)
    assert ledger["execution_limit_cny"] == 9.0
    worst = worst_case_cost_cny(
        estimated_input_tokens=1000,
        maximum_output_tokens=2000,
        input_per_million=1.2,
        output_per_million=7.2,
    )
    assert abs(worst - (0.0012 + 0.0144)) < 1e-9
    row = begin_attempt(
        ledger,
        attempt_id="a1",
        run_id="1",
        stage_key="analyze_window",
        window_index=0,
        provider="aliyun_qwen_plus",
        model="qwen3.6-flash",
        estimated_input_tokens=1000,
        maximum_output_tokens=2000,
        input_price=1.2,
        output_price=7.2,
    )
    assert row["allowed"] is True
    save_ledger(path, ledger)
    finish_attempt(
        ledger,
        attempt_id="a1",
        actual_input_tokens=800,
        actual_output_tokens=400,
        actual_cost_cny=0.003,
        status="succeeded",
    )
    save_ledger(path, ledger)
    again = load_ledger(path)
    assert again["actual_cost_cny"] == 0.003
    assert again["reserved_cost_cny"] == 0.0


def test_budget_blocks_when_projected_over_limit(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = load_ledger(path)
    ledger["actual_cost_cny"] = 8.5
    row = begin_attempt(
        ledger,
        attempt_id="a2",
        run_id="1",
        stage_key="synthesize_overview",
        window_index=None,
        provider="aliyun_qwen_plus",
        model="qwen3.6-flash",
        estimated_input_tokens=500_000,
        maximum_output_tokens=100_000,
        input_price=1.2,
        output_price=7.2,
    )
    assert row["allowed"] is False
    assert row["status"] == "blocked"
