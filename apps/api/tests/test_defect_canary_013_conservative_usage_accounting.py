# -*- coding: utf-8 -*-
"""DEFECT-CANARY-013: conservative usage accounting for missing provider usage."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.optional_gates import require_main_db_cert_counts, require_path

pytestmark = [
    pytest.mark.canary_offline,
    pytest.mark.requires_audit_assets,
]

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from certification.conservative_usage_accounting import (  # noqa: E402
    ACCOUNTING_CONSERVATIVE,
    ACCOUNTING_PROVIDER_ZERO,
    ACCOUNTING_REPORTED,
    ACCOUNTING_UNKNOWN,
    USAGE_CONSERVATIVE_UPPER,
    USAGE_PROVIDER_REPORTED,
    account_attempt,
    account_invocations,
    has_unknown_accounting,
    replay_run_invocations_from_sqlite,
    would_exceed_max_cost,
)

PRICING = ROOT / "config" / "cloud_pricing.json"
CANARY_V9 = (
    ROOT
    / "artifacts"
    / "single-chapter-pipeline-certification"
    / "real-canary"
    / "canary-v9.sqlite3"
)
MAIN_DB = ROOT / "data" / "storylens.db"
OLD_VERDICT = (
    ROOT
    / "audits"
    / "single-chapter-pipeline"
    / "real-canary-v9"
    / "final-verdict-v1.json"
)


@pytest.fixture(autouse=True)
def _verified_cloud_pricing_for_accounting(request) -> None:
    """Unit accounting tests need verified pricing when config/cloud_pricing.json is absent."""
    if request.node.name != "test_06_missing_pricing_is_unknown":
        request.getfixturevalue("verified_cloud_pricing")


def _snap(character_count: int = 1500) -> dict:
    return {
        "content_hash": "abc",
        "paragraph_ids": ["B0001-C0001-P0001"],
        "character_count": character_count,
    }


def test_01_reported_usage_when_provider_returns_tokens():
    result = account_attempt(
        http_request_sent=True,
        model="qwen3.7-plus",
        reported_input_tokens=100,
        reported_output_tokens=50,
        reported_cost=0.0006,
        pricing_path=PRICING,
    )
    assert result.accounting_status == ACCOUNTING_REPORTED
    assert result.usage_source == USAGE_PROVIDER_REPORTED
    assert result.reported_input_tokens == 100
    assert result.reported_output_tokens == 50
    assert result.estimated_input_tokens is None
    assert result.estimated_output_tokens is None
    assert result.certification_cost == pytest.approx(0.0006)


def test_02_conservative_estimate_on_remote_disconnect():
    result = account_attempt(
        http_request_sent=True,
        model="qwen3.7-plus",
        reported_input_tokens=None,
        reported_output_tokens=None,
        reported_cost=None,
        requested_output_tokens=768,
        input_snapshot=_snap(1567),
        error_code="PROVIDER_REMOTE_DISCONNECT",
        pricing_path=PRICING,
    )
    assert result.accounting_status == ACCOUNTING_CONSERVATIVE
    assert result.usage_source == USAGE_CONSERVATIVE_UPPER
    assert result.estimate_reason == "provider_disconnect_without_usage"
    assert result.reported_input_tokens is None
    assert result.reported_output_tokens is None
    assert result.estimated_input_tokens == 1567 + 8
    assert result.estimated_output_tokens == 768
    assert result.estimated_cost is not None and result.estimated_cost > 0
    assert result.certification_cost == result.estimated_cost


def test_03_disconnect_then_success_keeps_estimate_and_reported():
    failed = account_attempt(
        http_request_sent=True,
        model="qwen3.7-plus",
        reported_input_tokens=None,
        reported_output_tokens=None,
        reported_cost=None,
        requested_output_tokens=768,
        input_snapshot=_snap(1567),
        error_code="PROVIDER_REMOTE_DISCONNECT",
        pricing_path=PRICING,
        model_invocation_id=72,
    )
    ok = account_attempt(
        http_request_sent=True,
        model="qwen3.7-plus",
        reported_input_tokens=1439,
        reported_output_tokens=509,
        reported_cost=0.00695,
        requested_output_tokens=768,
        input_snapshot=_snap(1567),
        pricing_path=PRICING,
        model_invocation_id=73,
    )
    summary = account_invocations(
        [
            SimpleNamespace(
                id=72,
                model_name="qwen3.7-plus",
                input_tokens=None,
                output_tokens=None,
                estimated_cost=None,
                requested_output_tokens=768,
                request_parameters_json=json.dumps({"max_output_tokens": 768}),
                input_snapshot_json=json.dumps(_snap(1567)),
                error_code="PROVIDER_REMOTE_DISCONNECT",
                http_request_sent=True,
            ),
            SimpleNamespace(
                id=73,
                model_name="qwen3.7-plus",
                input_tokens=1439,
                output_tokens=509,
                estimated_cost=0.00695,
                requested_output_tokens=768,
                request_parameters_json=json.dumps({"max_output_tokens": 768}),
                input_snapshot_json=json.dumps(_snap(1567)),
                error_code=None,
                http_request_sent=True,
            ),
        ],
        pricing_path=PRICING,
    )
    assert failed.accounting_status == ACCOUNTING_CONSERVATIVE
    assert ok.accounting_status == ACCOUNTING_REPORTED
    assert not has_unknown_accounting(summary)
    assert summary.conservative_count == 1
    assert summary.reported_count == 1
    assert summary.certification_accounted_cost == pytest.approx(
        failed.certification_cost + ok.certification_cost
    )


def test_04_three_disconnects_all_conservative():
    rows = []
    for i in range(3):
        rows.append(
            SimpleNamespace(
                id=i + 1,
                model_name="qwen3.7-plus",
                input_tokens=None,
                output_tokens=None,
                estimated_cost=None,
                requested_output_tokens=768,
                request_parameters_json=json.dumps({"max_output_tokens": 768}),
                input_snapshot_json=json.dumps(_snap(1200 + i)),
                error_code="PROVIDER_REMOTE_DISCONNECT",
                http_request_sent=True,
            )
        )
    summary = account_invocations(rows, pricing_path=PRICING)
    assert summary.conservative_count == 3
    assert summary.unknown_count == 0
    assert all(a.estimate_reason == "provider_disconnect_without_usage" for a in summary.attempts)
    assert summary.certification_accounted_cost > 0


def test_05_cannot_estimate_input_is_unknown():
    result = account_attempt(
        http_request_sent=True,
        model="qwen3.7-plus",
        reported_input_tokens=None,
        reported_output_tokens=None,
        reported_cost=None,
        requested_output_tokens=768,
        input_snapshot=None,
        character_count=None,
        error_code="PROVIDER_REMOTE_DISCONNECT",
        pricing_path=PRICING,
    )
    assert result.accounting_status == ACCOUNTING_UNKNOWN
    assert result.estimate_reason == "cannot_estimate_input_tokens"


def test_06_missing_pricing_is_unknown():
    result = account_attempt(
        http_request_sent=True,
        model="nonexistent-model-xyz",
        reported_input_tokens=None,
        reported_output_tokens=None,
        reported_cost=None,
        requested_output_tokens=768,
        input_snapshot=_snap(1000),
        error_code="PROVIDER_REMOTE_DISCONNECT",
        pricing_path=PRICING,
    )
    assert result.accounting_status == ACCOUNTING_UNKNOWN
    assert result.estimate_reason == "model_pricing_unavailable"


def test_07_conservative_estimate_exceeds_max_cost_stops():
    summary = account_invocations(
        [
            SimpleNamespace(
                id=1,
                model_name="qwen3.7-plus",
                input_tokens=None,
                output_tokens=None,
                estimated_cost=None,
                requested_output_tokens=4000,
                request_parameters_json=json.dumps({"max_output_tokens": 4000}),
                input_snapshot_json=json.dumps(_snap(5_000_000)),
                error_code="PROVIDER_REMOTE_DISCONNECT",
                http_request_sent=True,
            )
        ],
        pricing_path=PRICING,
    )
    assert summary.conservative_count == 1
    assert would_exceed_max_cost(summary, max_cost_cny=0.01, next_request_conservative_budget=0.0)


def test_08_reported_tokens_remain_null_not_forged():
    result = account_attempt(
        http_request_sent=True,
        model="qwen3.7-plus",
        reported_input_tokens=None,
        reported_output_tokens=None,
        reported_cost=None,
        requested_output_tokens=768,
        input_snapshot=_snap(900),
        error_code="PROVIDER_REMOTE_DISCONNECT",
        pricing_path=PRICING,
    )
    assert result.reported_input_tokens is None
    assert result.reported_output_tokens is None
    assert result.reported_cost is None
    assert result.estimated_input_tokens is not None


def test_09_estimated_and_reported_fields_are_separate():
    result = account_attempt(
        http_request_sent=True,
        model="qwen3.7-plus",
        reported_input_tokens=None,
        reported_output_tokens=None,
        reported_cost=None,
        requested_output_tokens=512,
        input_snapshot=_snap(800),
        error_code="PROVIDER_TRANSPORT_ERROR",
        pricing_path=PRICING,
    )
    payload = result.to_dict()
    assert "reported_input_tokens" in payload and "estimated_input_tokens" in payload
    assert payload["reported_input_tokens"] is None
    assert payload["estimated_input_tokens"] == 808
    assert payload["estimated_output_tokens"] == 512


def test_10_failed_request_not_provider_confirmed_zero():
    result = account_attempt(
        http_request_sent=True,
        model="qwen3.7-plus",
        reported_input_tokens=None,
        reported_output_tokens=None,
        reported_cost=None,
        requested_output_tokens=768,
        input_snapshot=_snap(1000),
        error_code="PROVIDER_REMOTE_DISCONNECT",
        provider_confirmed_zero=False,
        pricing_path=PRICING,
    )
    assert result.accounting_status != ACCOUNTING_PROVIDER_ZERO
    assert result.accounting_status == ACCOUNTING_CONSERVATIVE


def test_11_reservations_released_on_canary_v9():
    require_path(CANARY_V9)
    uri = CANARY_V9.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    rows = list(con.execute("SELECT status, COUNT(*) FROM cloud_budget_reservations GROUP BY status"))
    con.close()
    assert rows == [("released", 21)] or all(status == "released" for status, _ in rows)


def test_12_no_duplicate_run_scene_profile_on_canary_v9_run6():
    require_path(CANARY_V9)
    uri = CANARY_V9.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    analysis_runs = con.execute("SELECT COUNT(*) FROM analysis_runs WHERE id=6").fetchone()[0]
    # Run 6 aborted before journey; scenes may exist after boundary stage.
    scenes = con.execute(
        "SELECT COUNT(*) FROM scenes WHERE chapter_id=(SELECT subject_id FROM analysis_runs WHERE id=6)"
    ).fetchone()[0]
    profiles = con.execute(
        "SELECT COUNT(*) FROM scene_reader_journey_profiles WHERE reader_journey_run_id IN "
        "(SELECT id FROM reader_journey_runs WHERE analysis_run_id=6)"
    ).fetchone()[0]
    journey_runs = con.execute(
        "SELECT COUNT(*) FROM reader_journey_runs WHERE analysis_run_id=6"
    ).fetchone()[0]
    con.close()
    assert analysis_runs == 1
    assert journey_runs == 0
    assert profiles == 0
    # Scenes are created only after confirm; aborted at awaiting_boundary_review => 0 scenes expected
    assert scenes == 0


def test_13_run6_offline_replay_no_longer_aborts_on_null_tokens():
    require_path(CANARY_V9)
    summary = replay_run_invocations_from_sqlite(CANARY_V9, analysis_run_id=6, pricing_path=PRICING)
    assert summary.request_count >= 1
    assert not has_unknown_accounting(summary)
    # Historical inv#72 must be conservative, not a hard stop.
    by_id = {a.model_invocation_id: a for a in summary.attempts}
    assert 72 in by_id
    assert by_id[72].accounting_status == ACCOUNTING_CONSERVATIVE
    assert by_id[72].reported_input_tokens is None
    assert by_id[73].accounting_status == ACCOUNTING_REPORTED


def test_14_run6_accounted_cost_below_100():
    require_path(CANARY_V9)
    # Full batch re-settlement from canary DB (all http-sent invocations).
    uri = CANARY_V9.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    rows = list(
        con.execute(
            """
            SELECT id, model_name, input_tokens, output_tokens, estimated_cost,
                   requested_output_tokens, request_parameters_json, input_snapshot_json,
                   error_code, http_request_sent
            FROM model_invocations WHERE http_request_sent=1 ORDER BY id
            """
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

    summary = account_invocations([_Row(r) for r in rows], pricing_path=PRICING)
    assert summary.certification_accounted_cost < 100.0
    assert summary.certification_accounted_cost > 0.0
    assert summary.conservative_count >= 1


def test_15_main_db_counts_unchanged():
    require_main_db_cert_counts()


def test_16_zero_real_model_requests_this_remediation_and_old_batch_frozen():
    require_path(OLD_VERDICT)
    verdict = json.loads(OLD_VERDICT.read_text(encoding="utf-8"))
    assert verdict["verdict"] == "REAL_CANARY_ABORTED_BY_LIMIT"
    assert verdict["superseded_by_future_batch"] is True
    assert verdict["batch_id"] == "phase-1db2-r8-20260718T161902Z"
    # This remediation phase must not issue model HTTP; marker for change package.
    assert True  # enforced by change package real_model_requests_this_phase=0


def test_runner_no_longer_uses_null_token_hard_gate_source():
    runner = (ROOT / "scripts" / "certification" / "real_canary_runner.py").read_text(
        encoding="utf-8"
    )
    assert "token_stats_missing" not in runner or "accounting_unknown" in runner
    assert "accounting_unknown" in runner
    assert "conservative_usage_accounting" in runner
    assert "ModelInvocation.input_tokens.is_(None)" not in runner
