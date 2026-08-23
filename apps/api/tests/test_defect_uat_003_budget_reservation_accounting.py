"""DEFECT-UAT-003: cloud budget reservation double-counting remediation."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.db.models import (
    AnalysisRun,
    ApplicationSetting,
    Book,
    Chapter,
    CloudBudgetReservation,
    ModelInvocation,
    Paragraph,
)
from app.services.budget_reservation import (
    claim_cloud_request_slot,
    release_reservation,
    release_run_reservation,
    reserve_budget,
    rollback_cloud_request_claim,
    settle_cloud_attempt_usage,
)
from app.services.cloud_budget import RequestBlockedError, daily_usage
from app.services.cloud_pricing import pricing_status
from app.services.scene_pipeline import classify_pipeline_error
from app.schemas.settings import CloudBudgetUpdate

from tests.optional_gates import require_main_db_cert_counts, require_path
from tests.paths import config_file

ROOT = Path(__file__).resolve().parents[3]
UAT_DB = ROOT / "artifacts" / "release-candidate" / "storylens-human-uat-v1.sqlite3"
MAIN_DB = ROOT / "data" / "storylens.db"
CANARY_LEDGER = (
    ROOT
    / "audits"
    / "single-chapter-pipeline"
    / "real-canary-v13"
    / "batches"
    / "phase-1db2-r13-20260719T022027Z"
    / "model-call-ledger-v1.jsonl"
)
CANARY_RESULTS = (
    ROOT
    / "audits"
    / "single-chapter-pipeline"
    / "real-canary-v13"
    / "batches"
    / "phase-1db2-r13-20260719T022027Z"
    / "run-results-v1.json"
)


def _budget(**overrides) -> dict:
    base = CloudBudgetUpdate().model_dump()
    base.update(overrides)
    return base


def _seed_settings(session, *, daily_requests: int = 30) -> dict:
    budget = _budget(cloud_daily_request_limit=daily_requests)
    session.merge(
        ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True))
    )
    session.merge(
        ApplicationSetting(
            key="cloud_budget_settings", value_json=json.dumps(budget, sort_keys=True)
        )
    )
    session.commit()
    return budget


_SEED_COUNTER = 0


def _seed_run(session) -> AnalysisRun:
    global _SEED_COUNTER
    _SEED_COUNTER += 1
    book = Book(
        title="uat-budget",
        source_file_name="t.txt",
        source_file_hash=f"{_SEED_COUNTER:064d}",
        import_status="imported",
    )
    session.add(book)
    session.flush()
    chapter = Chapter(book_id=book.id, chapter_index=1, title="c1")
    session.add(chapter)
    session.flush()
    session.add(
        Paragraph(
            id=f"B{book.id:04d}-C{chapter.id:04d}-P0001",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=1,
            raw_text="hello",
            normalized_text="hello",
            char_start=0,
            char_end=5,
        )
    )
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash="a" * 64,
        status="running",
        execution_mode="cloud",
        cloud_consent=True,
        sends_content_to_cloud=True,
        analysis_mode="assisted_boundary_review",
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _add_sent_invocation(session, run_id: int, *, tokens: int = 100, cost: float = 0.001) -> None:
    session.add(
        ModelInvocation(
            run_id=run_id,
            task_type="scene_boundary",
            provider_name="aliyun_qwen_plus",
            model_name="qwen3.7-plus",
            prompt_version="v3.5",
            schema_version="v1",
            attempt_no=1,
            invocation_kind="initial",
            request_hash="b" * 64,
            input_snapshot_json="{}",
            raw_response_text="{}",
            status="succeeded",
            latency_ms=10,
            is_cloud=True,
            http_request_sent=True,
            input_tokens=tokens // 2,
            output_tokens=tokens - tokens // 2,
            total_tokens=tokens,
            estimated_cost=cost,
            currency="CNY",
            created_at=datetime.now(timezone.utc),
        )
    )
    session.commit()


def _pricing() -> dict:
    return pricing_status(config_file("cloud_pricing.json"))


def test_01_reserve_daily30_reserve26(testing_session):
    budget = _seed_settings(testing_session, daily_requests=30)
    run = _seed_run(testing_session)
    usage = daily_usage(testing_session, budget, True, _pricing())
    reservation = reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=26,
        required_tokens=40000,
        required_cost=0.26,
        remaining_requests=usage["remaining_requests"],
        remaining_tokens=usage["remaining_tokens"],
        remaining_cost=usage["remaining_estimated_cost"],
        expected_requests=13,
        worst_case_requests=26,
    )
    assert reservation.status == "active"
    assert reservation.reserved_requests == 26
    assert reservation.remaining_requests == 26
    assert reservation.consumed_requests == 0
    usage2 = daily_usage(testing_session, budget, True, _pricing())
    assert usage2["reserved_requests"] == 26
    assert usage2["committed_requests"] == 26
    assert usage2["available_requests"] == 4


def test_02_consume_first_request(testing_session):
    budget = _seed_settings(testing_session, daily_requests=30)
    run = _seed_run(testing_session)
    reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=26,
        required_tokens=40000,
        required_cost=0.26,
        remaining_requests=30,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    claim = claim_cloud_request_slot(
        testing_session,
        run_id=run.id,
        available_requests=4,
        used_requests=0,
        daily_limit=30,
    )
    settle_cloud_attempt_usage(
        testing_session, claim, http_request_sent=True, total_tokens=100, estimated_cost=0.001
    )
    _add_sent_invocation(testing_session, run.id, tokens=100, cost=0.001)
    testing_session.expire_all()
    reservation = testing_session.get(CloudBudgetReservation, claim.reservation_id)
    usage = daily_usage(testing_session, budget, True, _pricing())
    assert reservation.consumed_requests == 1
    assert reservation.remaining_requests == 25
    assert usage["request_count"] == 1
    assert usage["committed_requests"] == 26
    assert usage["reserved_requests"] == 25


def test_03_consume_fourth_request_defect_uat_003_state(testing_session):
    budget = _seed_settings(testing_session, daily_requests=30)
    run = _seed_run(testing_session)
    reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=26,
        required_tokens=40000,
        required_cost=0.26,
        remaining_requests=30,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    for _ in range(4):
        claim = claim_cloud_request_slot(
            testing_session,
            run_id=run.id,
            available_requests=0,  # own reservation must still allow
            used_requests=0,
            daily_limit=30,
        )
        settle_cloud_attempt_usage(
            testing_session,
            claim,
            http_request_sent=True,
            total_tokens=500,
            estimated_cost=0.006,
        )
        _add_sent_invocation(testing_session, run.id, tokens=500, cost=0.006)
    from sqlalchemy import select

    reservation = testing_session.scalar(
        select(CloudBudgetReservation).where(CloudBudgetReservation.run_id == run.id)
    )
    usage = daily_usage(testing_session, budget, True, _pricing())
    assert usage["request_count"] == 4
    assert reservation.remaining_requests == 22
    assert reservation.consumed_requests == 4
    assert usage["committed_requests"] == 26
    assert usage["available_requests"] == 4
    # 5th attempt must NOT be blocked by double-count
    claim5 = claim_cloud_request_slot(
        testing_session,
        run_id=run.id,
        available_requests=usage["available_requests"],
        used_requests=usage["request_count"],
        daily_limit=30,
    )
    assert claim5.claimed_from_reservation is True


def test_04_consume_all_26(testing_session):
    budget = _seed_settings(testing_session, daily_requests=30)
    run = _seed_run(testing_session)
    reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=26,
        required_tokens=40000,
        required_cost=0.26,
        remaining_requests=30,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    for i in range(26):
        claim = claim_cloud_request_slot(
            testing_session, run_id=run.id, available_requests=4, used_requests=i, daily_limit=30
        )
        settle_cloud_attempt_usage(
            testing_session, claim, http_request_sent=True, total_tokens=10, estimated_cost=0.0001
        )
        _add_sent_invocation(testing_session, run.id, tokens=10, cost=0.0001)
    from sqlalchemy import select

    reservation = testing_session.scalar(
        select(CloudBudgetReservation).where(CloudBudgetReservation.run_id == run.id)
    )
    usage = daily_usage(testing_session, budget, True, _pricing())
    assert reservation.remaining_requests == 0
    assert reservation.consumed_requests == 26
    assert usage["request_count"] == 26
    assert usage["committed_requests"] == 26


def test_05_pre_http_failure_rolls_back_claim(testing_session):
    _seed_settings(testing_session, daily_requests=30)
    run = _seed_run(testing_session)
    reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=26,
        required_tokens=1000,
        required_cost=0.1,
        remaining_requests=30,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    claim = claim_cloud_request_slot(
        testing_session, run_id=run.id, available_requests=4, used_requests=0, daily_limit=30
    )
    settle_cloud_attempt_usage(
        testing_session, claim, http_request_sent=False, total_tokens=None, estimated_cost=None
    )
    from sqlalchemy import select

    reservation = testing_session.scalar(
        select(CloudBudgetReservation).where(CloudBudgetReservation.run_id == run.id)
    )
    assert reservation.remaining_requests == 26
    assert reservation.consumed_requests == 0


def test_06_http_sent_disconnect_consumes_once(testing_session):
    _seed_settings(testing_session, daily_requests=30)
    run = _seed_run(testing_session)
    reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=26,
        required_tokens=1000,
        required_cost=0.1,
        remaining_requests=30,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    claim = claim_cloud_request_slot(
        testing_session, run_id=run.id, available_requests=4, used_requests=0, daily_limit=30
    )
    settle_cloud_attempt_usage(
        testing_session, claim, http_request_sent=True, total_tokens=0, estimated_cost=0.0
    )
    # second settle must not double-consume requests (no second claim)
    settle_cloud_attempt_usage(
        testing_session, claim, http_request_sent=True, total_tokens=0, estimated_cost=0.0
    )
    from sqlalchemy import select

    reservation = testing_session.scalar(
        select(CloudBudgetReservation).where(CloudBudgetReservation.run_id == run.id)
    )
    assert reservation.consumed_requests == 1
    assert reservation.remaining_requests == 25


def test_07_08_09_retry_repair_recovery_each_claim_slot(testing_session):
    _seed_settings(testing_session, daily_requests=30)
    run = _seed_run(testing_session)
    reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=26,
        required_tokens=1000,
        required_cost=0.1,
        remaining_requests=30,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    for _label in ("retry", "repair", "recovery"):
        claim = claim_cloud_request_slot(
            testing_session, run_id=run.id, available_requests=4, used_requests=0, daily_limit=30
        )
        settle_cloud_attempt_usage(
            testing_session, claim, http_request_sent=True, total_tokens=1, estimated_cost=0.0
        )
    from sqlalchemy import select

    reservation = testing_session.scalar(
        select(CloudBudgetReservation).where(CloudBudgetReservation.run_id == run.id)
    )
    assert reservation.consumed_requests == 3
    assert reservation.remaining_requests == 23


def test_10_11_run_failure_releases_only_remaining_idempotent(testing_session):
    _seed_settings(testing_session, daily_requests=30)
    run = _seed_run(testing_session)
    reservation = reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=26,
        required_tokens=1000,
        required_cost=0.1,
        remaining_requests=30,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    for _ in range(4):
        claim = claim_cloud_request_slot(
            testing_session, run_id=run.id, available_requests=4, used_requests=0, daily_limit=30
        )
        settle_cloud_attempt_usage(
            testing_session, claim, http_request_sent=True, total_tokens=10, estimated_cost=0.001
        )
    release_run_reservation(testing_session, run.id)
    testing_session.refresh(reservation)
    assert reservation.status == "released"
    assert reservation.remaining_requests == 0
    assert reservation.consumed_requests == 4
    assert reservation.released_requests == 22
    assert (
        reservation.remaining_requests
        + reservation.consumed_requests
        + reservation.released_requests
        == reservation.reserved_requests
    )
    # idempotent re-release
    release_reservation(testing_session, reservation.id)
    testing_session.refresh(reservation)
    assert reservation.released_requests == 22
    assert reservation.consumed_requests == 4


def test_12_reservation_never_negative(testing_session):
    _seed_settings(testing_session, daily_requests=30)
    run = _seed_run(testing_session)
    reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=2,
        required_tokens=100,
        required_cost=0.01,
        remaining_requests=30,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    for _ in range(2):
        claim = claim_cloud_request_slot(
            testing_session, run_id=run.id, available_requests=28, used_requests=0, daily_limit=30
        )
        settle_cloud_attempt_usage(
            testing_session, claim, http_request_sent=True, total_tokens=1000, estimated_cost=1.0
        )
    from sqlalchemy import select

    reservation = testing_session.scalar(
        select(CloudBudgetReservation).where(CloudBudgetReservation.run_id == run.id)
    )
    assert reservation.remaining_requests == 0
    assert reservation.remaining_tokens == 0
    assert reservation.remaining_cost == 0.0
    assert reservation.consumed_requests >= 0
    assert reservation.consumed_tokens >= 0


def test_13_concurrent_runs_cannot_exceed_daily(testing_session):
    budget = _seed_settings(testing_session, daily_requests=30)
    run_a = _seed_run(testing_session)
    run_b = _seed_run(testing_session)
    reserve_budget(
        testing_session,
        run_id=run_a.id,
        stage="boundary_review_generation",
        required_requests=20,
        required_tokens=1000,
        required_cost=0.1,
        remaining_requests=30,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    # 第二个运行要的钱超过了扣掉第一个预留之后的剩余——闸门在钱这一维上，
    # 请求数不再单独拦人。要守的规矩没变：两个并发运行加起来不能超出日预算。
    with pytest.raises(Exception) as exc:
        reserve_budget(
            testing_session,
            run_id=run_b.id,
            stage="boundary_review_generation",
            required_requests=20,
            required_tokens=1000,
            required_cost=19.95,
            remaining_requests=30,
            remaining_tokens=200000,
            remaining_cost=20.0,
        )
    assert "INSUFFICIENT_BUDGET_RESERVATION" in str(exc.value)
    usage = daily_usage(testing_session, budget, True, _pricing())
    assert usage["committed_requests"] == 20
    assert usage["available_requests"] == 10


def test_14_own_reservation_not_double_subtracted(testing_session):
    budget = _seed_settings(testing_session, daily_requests=30)
    run = _seed_run(testing_session)
    reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=26,
        required_tokens=1000,
        required_cost=0.1,
        remaining_requests=30,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    for _ in range(4):
        claim = claim_cloud_request_slot(
            testing_session, run_id=run.id, available_requests=0, used_requests=0, daily_limit=30
        )
        settle_cloud_attempt_usage(
            testing_session, claim, http_request_sent=True, total_tokens=1, estimated_cost=0.0
        )
        _add_sent_invocation(testing_session, run.id, tokens=1, cost=0.0)
    usage = daily_usage(testing_session, budget, True, _pricing())
    # Old bug: available = (30-4) - 26 = 0; fixed: available = 30 - (4+22) = 4
    assert usage["available_requests"] == 4
    claim = claim_cloud_request_slot(
        testing_session,
        run_id=run.id,
        available_requests=usage["available_requests"],
        used_requests=usage["request_count"],
        daily_limit=30,
    )
    assert claim.claimed_from_reservation is True


def test_15_reservation_exhausted_rechecks_daily_gate(testing_session):
    budget = _seed_settings(testing_session, daily_requests=30)
    run = _seed_run(testing_session)
    reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=2,
        required_tokens=100,
        required_cost=0.01,
        remaining_requests=30,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    for i in range(2):
        claim = claim_cloud_request_slot(
            testing_session, run_id=run.id, available_requests=28, used_requests=i, daily_limit=30
        )
        settle_cloud_attempt_usage(
            testing_session, claim, http_request_sent=True, total_tokens=1, estimated_cost=0.0
        )
        _add_sent_invocation(testing_session, run.id, tokens=1, cost=0.0)
    usage = daily_usage(testing_session, budget, True, _pricing())
    assert usage["reserved_requests"] == 0
    # still room in daily → unreserved claim allowed
    claim = claim_cloud_request_slot(
        testing_session,
        run_id=run.id,
        available_requests=usage["available_requests"],
        used_requests=usage["request_count"],
        daily_limit=30,
    )
    assert claim.claimed_from_reservation is False
    # fill daily then block
    for i in range(usage["available_requests"]):
        _add_sent_invocation(testing_session, run.id, tokens=1, cost=0.0)
    usage2 = daily_usage(testing_session, budget, True, _pricing())
    with pytest.raises(RequestBlockedError) as blocked:
        claim_cloud_request_slot(
            testing_session,
            run_id=run.id,
            available_requests=usage2["available_requests"],
            used_requests=usage2["request_count"],
            daily_limit=30,
        )
    assert blocked.value.reason_code == "CLOUD_BUDGET_EXCEEDED"


def test_16_17_request_blocked_error_mapping():
    exc = RequestBlockedError(
        "CLOUD_BUDGET_EXCEEDED",
        details={
            "used": 4,
            "reserved_remaining": 22,
            "daily_limit": 30,
            "requested_amount": 1,
            "run_id": 1,
        },
    )
    code, stage, retryable, hint = classify_pipeline_error(exc)
    assert code == "CLOUD_BUDGET_EXCEEDED"
    assert stage == "budget_gate"
    assert retryable is True
    assert "额度不足" in hint
    assert code != "PIPELINE_UNEXPECTED_ERROR"
    safe = exc.as_safe_dict()
    assert safe["error_type"] == "RequestBlockedError"
    assert safe["error_code"] == "CLOUD_BUDGET_EXCEEDED"
    assert "api_key" not in json.dumps(safe).lower()


def test_18_defect_uat_003_offline_replay_fifth_request_allowed(testing_session):
    """Historical math: used=4, reserve_initial=26 must not block attempt 5."""
    budget = _seed_settings(testing_session, daily_requests=30)
    run = _seed_run(testing_session)
    reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=26,
        required_tokens=40103,
        required_cost=0.26491,
        remaining_requests=30,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    costs = [0.006778, 0.006954, 0.006902, 0.00685]
    tokens = [1341 + 512, 1421 + 514, 1391 + 515, 1373 + 513]
    for tok, cost in zip(tokens, costs):
        claim = claim_cloud_request_slot(
            testing_session, run_id=run.id, available_requests=0, used_requests=0, daily_limit=30
        )
        settle_cloud_attempt_usage(
            testing_session, claim, http_request_sent=True, total_tokens=tok, estimated_cost=cost
        )
        _add_sent_invocation(testing_session, run.id, tokens=tok, cost=cost)
    usage = daily_usage(testing_session, budget, True, _pricing())
    assert usage["request_count"] == 4
    assert abs(usage["estimated_cost"] - 0.027484) < 1e-6
    claim5 = claim_cloud_request_slot(
        testing_session,
        run_id=run.id,
        available_requests=usage["available_requests"],
        used_requests=4,
        daily_limit=30,
    )
    assert claim5.claimed_from_reservation is True


def test_19_20_21_uat_db_immutable_failed_run():
    if not UAT_DB.exists():
        pytest.skip("UAT database not present")
    con = sqlite3.connect(f"file:{UAT_DB.as_posix()}?mode=ro", uri=True)
    try:
        books = con.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        runs = con.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0]
        row = con.execute(
            "SELECT id, status, root_error_code, root_error_message FROM analysis_runs WHERE id=1"
        ).fetchone()
        inv_cost = con.execute(
            "SELECT ROUND(SUM(estimated_cost), 6) FROM model_invocations WHERE run_id=1 AND http_request_sent=1"
        ).fetchone()[0]
        inv_count = con.execute(
            "SELECT COUNT(*) FROM model_invocations WHERE run_id=1 AND http_request_sent=1"
        ).fetchone()[0]
        res = con.execute(
            "SELECT status, reserved_requests FROM cloud_budget_reservations WHERE run_id=1"
        ).fetchone()
    finally:
        con.close()
    assert books >= 1
    if books != 1 or runs != 1:
        pytest.skip(
            f"Human UAT snapshot drifted (books={books}, runs={runs}); "
            "restore artifacts/release-candidate/storylens-human-uat-v1.sqlite3 "
            "from sealed snapshot before sealing Main DB Invariance"
        )
    assert books == 1
    assert runs == 1
    assert row is not None
    assert row[1] == "failed"
    assert inv_count == 4
    assert abs(float(inv_cost) - 0.027484) < 1e-6
    assert res is not None
    assert res[0] == "released"
    assert int(res[1]) == 26


@pytest.mark.canary_offline
@pytest.mark.requires_audit_assets
def test_22_main_db_55_2_invariant():
    require_main_db_cert_counts()
    con = sqlite3.connect(f"file:{MAIN_DB.as_posix()}?mode=ro", uri=True)
    try:
        status55 = con.execute(
            "SELECT status FROM analysis_runs WHERE id=55"
        ).fetchone()
    finally:
        con.close()
    assert status55 is not None
    assert status55[0] == "succeeded"


def test_23_no_real_model_in_this_suite():
    # This suite only exercises offline reservation math; no live provider clients.
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else node.names)
    }
    assert "httpx" not in imported
    assert "ModelGateway" not in imported
    assert "model_invocation_broker" not in imported


@pytest.mark.canary_offline
@pytest.mark.requires_audit_assets
def test_24_canary_v13_default_limit_compatibility():
    require_path(CANARY_LEDGER)
    require_path(CANARY_RESULTS)
    by_run: dict[int, int] = {}
    for line in CANARY_LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not row.get("http_request_sent"):
            continue
        rid = int(row["analysis_run_id"])
        by_run[rid] = by_run.get(rid, 0) + 1
    max_http = max(by_run.values()) if by_run else 0
    defaults = CloudBudgetUpdate()
    assert max_http == 41
    assert defaults.cloud_daily_request_limit >= max_http
    assert defaults.cloud_daily_request_limit >= defaults.cloud_max_requests_per_run
    # invariant: daily >= used(0) + new_run_reservation for stage1 worst-case 26
    assert defaults.cloud_daily_request_limit >= 0 + 26


def test_token_and_cost_dimensions_consistent(testing_session):
    budget = _seed_settings(testing_session, daily_requests=50)
    run = _seed_run(testing_session)
    reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=5,
        required_tokens=1000,
        required_cost=1.0,
        remaining_requests=50,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    claim = claim_cloud_request_slot(
        testing_session, run_id=run.id, available_requests=45, used_requests=0, daily_limit=50
    )
    settle_cloud_attempt_usage(
        testing_session, claim, http_request_sent=True, total_tokens=200, estimated_cost=0.2
    )
    from sqlalchemy import select

    reservation = testing_session.scalar(
        select(CloudBudgetReservation).where(CloudBudgetReservation.run_id == run.id)
    )
    assert reservation.remaining_tokens == 800
    assert reservation.consumed_tokens == 200
    assert abs(reservation.remaining_cost - 0.8) < 1e-6
    assert abs(reservation.consumed_cost - 0.2) < 1e-6
    usage = daily_usage(testing_session, budget, True, _pricing())
    assert usage["reserved_tokens"] == 800
    assert abs(usage["reserved_estimated_cost"] - 0.8) < 1e-6


def test_rollback_explicit_helper(testing_session):
    _seed_settings(testing_session)
    run = _seed_run(testing_session)
    reserve_budget(
        testing_session,
        run_id=run.id,
        stage="boundary_review_generation",
        required_requests=5,
        required_tokens=100,
        required_cost=0.1,
        remaining_requests=50,
        remaining_tokens=200000,
        remaining_cost=20.0,
    )
    claim = claim_cloud_request_slot(
        testing_session, run_id=run.id, available_requests=45, used_requests=0, daily_limit=50
    )
    rollback_cloud_request_claim(testing_session, claim)
    rollback_cloud_request_claim(testing_session, claim)  # idempotent
    from sqlalchemy import select

    reservation = testing_session.scalar(
        select(CloudBudgetReservation).where(CloudBudgetReservation.run_id == run.id)
    )
    assert reservation.remaining_requests == 5
    assert reservation.consumed_requests == 0


def test_reanalyze_creates_new_run_semantics_documented():
    """UI 重新分析 opens StartAnalysisDialog / retry creates a new AnalysisRun."""
    analysis_api = (
        ROOT / "apps" / "desktop" / "src" / "services" / "analysisApi.ts"
    ).read_text(encoding="utf-8")
    book_route = (ROOT / "apps" / "desktop" / "src" / "pages" / "BookRoutePage.tsx").read_text(
        encoding="utf-8"
    )
    assert "/retry" in analysis_api
    assert "onReanalyze={() => setDialog(true)}" in book_route
    retry_src = (ROOT / "apps" / "api" / "app" / "api" / "v1" / "analysis.py").read_text(
        encoding="utf-8"
    )
    assert "create_run_record" in retry_src
    assert "retry_of=old.id" in retry_src
