from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from storylens_online.contracts.beta import Phase2B1TxtEvidenceResult
from storylens_online.contracts.billing import ModelAttemptStatus, ModelPricingSnapshot
from storylens_online.db.models import (
    BillingReservation,
    ModelUsageLedger,
    OnlineAnalysisJob,
    RechargeOrder,
    WalletAccount,
    WalletTransaction,
)
from storylens_online.services.model_cost import calculate_internal_model_cost
from storylens_online.services.phase2b1_analysis import phase2b1_pricing_snapshot
from storylens_online.services.repository import OnlineRepository
from test_beta_vertical_slice import BetaHarness, beta_harness, create_job, register, upload

__all__ = ["beta_harness"]


def _pricing() -> ModelPricingSnapshot:
    return ModelPricingSnapshot(
        provider="deepseek",
        model="deepseek-v4-flash",
        pricing_version="deepseek-v4-flash@2026-08-30",
        pricing_currency="USD",
        pricing_tier="off_peak",
        cache_hit_usd_per_million=Decimal("0.007"),
        cache_miss_usd_per_million=Decimal("0.22"),
        output_usd_per_million=Decimal("0.66"),
        fx_rate_to_cny=Decimal("6.7811"),
        fx_rate_version="safe-usdcny-central-parity-2026-08-28",
        request_sent_at=datetime(2026, 8, 30, 12, tzinfo=UTC),
    )


def _pricing_at(request_sent_at: datetime) -> ModelPricingSnapshot:
    return phase2b1_pricing_snapshot(
        provider="deepseek",
        model="deepseek-v4-flash",
        pricing_version="deepseek-v4-flash@2026-08-30",
        request_sent_at=request_sent_at,
        fx_rate_to_cny=Decimal("6.7811"),
        fx_rate_version="safe-usdcny-central-parity-2026-08-28",
        off_peak_cache_hit_usd=Decimal("0.007"),
        off_peak_cache_miss_usd=Decimal("0.22"),
        off_peak_output_usd=Decimal("0.66"),
        peak_cache_hit_usd=Decimal("0.014"),
        peak_cache_miss_usd=Decimal("0.44"),
        peak_output_usd=Decimal("1.32"),
    )


@pytest.mark.parametrize(
    ("request_sent_at", "expected_tier"),
    [
        (datetime(2026, 8, 31, 0, 59, 59, tzinfo=UTC), "off_peak"),
        (datetime(2026, 8, 31, 1, 0, 0, tzinfo=UTC), "peak"),
        (datetime(2026, 8, 31, 3, 59, 59, tzinfo=UTC), "peak"),
        (datetime(2026, 8, 31, 4, 0, 0, tzinfo=UTC), "off_peak"),
        (datetime(2026, 8, 31, 6, 0, 0, tzinfo=UTC), "peak"),
        (datetime(2026, 8, 31, 9, 59, 59, tzinfo=UTC), "peak"),
        (datetime(2026, 8, 31, 10, 0, 0, tzinfo=UTC), "off_peak"),
        (datetime(2026, 8, 30, 2, 0, 0, tzinfo=UTC), "off_peak"),
    ],
)
def test_deepseek_peak_time_boundaries_are_left_closed_right_open(
    request_sent_at: datetime,
    expected_tier: str,
) -> None:
    assert _pricing_at(request_sent_at).pricing_tier == expected_tier


def test_peak_price_is_exactly_the_frozen_double_rate() -> None:
    peak = _pricing_at(datetime(2026, 8, 31, 1, tzinfo=UTC))
    off_peak = _pricing_at(datetime(2026, 8, 31, 4, tzinfo=UTC))
    assert peak.cache_hit_usd_per_million == off_peak.cache_hit_usd_per_million * 2
    assert peak.cache_miss_usd_per_million == off_peak.cache_miss_usd_per_million * 2
    assert peak.output_usd_per_million == off_peak.output_usd_per_million * 2


def test_internal_cost_uses_decimal_and_cached_input_price() -> None:
    cost = calculate_internal_model_cost(
        input_tokens=1_000_000,
        cached_tokens=250_000,
        output_tokens=100_000,
        total_tokens=1_234_567,
        prompt_cache_miss_tokens=750_000,
        pricing=_pricing(),
    )
    assert cost.provider_cost_usd == Decimal("0.232750000")
    assert cost.provider_cost_cny == Decimal("1.578301")
    assert cost.customer_charge_cny == Decimal("0.000000")
    assert cost.total_tokens == 1_234_567


def test_attempts_preserve_provider_totals_and_aggregate_all_retries(
    beta_harness: BetaHarness,
) -> None:
    repository = OnlineRepository()
    with beta_harness.database.session() as session:
        first, created = repository.begin_model_attempt(
            session,
            job_id="job-usage-1",
            user_id="user-1",
            attempt_no=1,
            pricing=_pricing(),
        )
        assert created is True
        assert first.invocation_id == "job-usage-1:1"
    with beta_harness.database.session() as session:
        repository.finish_model_attempt(
            session,
            job_id="job-usage-1",
            attempt_no=1,
            status=ModelAttemptStatus.INVALID_RESPONSE,
            http_request_sent=True,
            usage_reported=True,
            input_tokens=100_000,
            cached_tokens=20_000,
            prompt_cache_miss_tokens=80_000,
            output_tokens=10_000,
            total_tokens=115_000,
            provider_request_id="provider-request-1",
            error_code="invalid_schema",
        )
        repository.begin_model_attempt(
            session,
            job_id="job-usage-1",
            user_id="user-1",
            attempt_no=2,
            pricing=_pricing(),
        )
    with beta_harness.database.session() as session:
        repository.finish_model_attempt(
            session,
            job_id="job-usage-1",
            attempt_no=2,
            status=ModelAttemptStatus.SUCCEEDED,
            http_request_sent=True,
            usage_reported=True,
            input_tokens=80_000,
            cached_tokens=0,
            prompt_cache_miss_tokens=80_000,
            output_tokens=20_000,
            total_tokens=101_000,
            provider_request_id="provider-request-2",
        )
        aggregate = repository.aggregate_model_usage(session, "job-usage-1")
        assert aggregate.attempt_count == 2
        assert aggregate.input_tokens == 180_000
        assert aggregate.cached_tokens == 20_000
        assert aggregate.output_tokens == 30_000
        assert aggregate.total_tokens == 216_000
        assert aggregate.provider_cost_usd == Decimal("0.055140000")
        assert aggregate.provider_cost_cny == Decimal("0.373910")
        assert aggregate.customer_charge_cny == Decimal("0.000000")
        assert aggregate.usage_complete is True
        assert aggregate.has_unknown_attempt is False

        for model in (WalletAccount, RechargeOrder, WalletTransaction, BillingReservation):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_no_usage_transport_failure_is_complete_but_crash_recovery_is_unknown(
    beta_harness: BetaHarness,
) -> None:
    repository = OnlineRepository()
    with beta_harness.database.session() as session:
        repository.begin_model_attempt(
            session,
            job_id="job-usage-2",
            user_id="user-1",
            attempt_no=1,
            pricing=_pricing(),
        )
        repository.finish_model_attempt(
            session,
            job_id="job-usage-2",
            attempt_no=1,
            status=ModelAttemptStatus.FAILED,
            http_request_sent=False,
            usage_reported=False,
            total_tokens=0,
            error_code="connect_error",
        )
        assert repository.aggregate_model_usage(session, "job-usage-2").usage_complete is True
        repository.begin_model_attempt(
            session,
            job_id="job-usage-2",
            user_id="user-1",
            attempt_no=2,
            pricing=_pricing(),
        )
    with beta_harness.database.session() as session:
        assert repository.recover_started_model_attempts(session, "job-usage-2") == 1
        aggregate = repository.aggregate_model_usage(session, "job-usage-2")
        assert aggregate.usage_complete is False
        assert aggregate.has_unknown_attempt is True


def test_real_pipeline_requires_both_flag_and_user_allowlist(beta_harness: BetaHarness) -> None:
    client = beta_harness.client
    register(client)
    saved = upload(client)
    response = client.post(
        "/api/v1/jobs",
        json={
            "upload_id": saved["id"],
            "idempotency_key": "real-request-001",
            "pipeline": "phase2b1_txt_evidence_summary",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"] == {
        "code": "pipeline_unavailable",
        "message": "该分析任务尚未对当前账户开放。",
    }
    assert beta_harness.queue.job_ids == []

    beta_harness.client.app.state.settings.phase2b1_enabled = True
    beta_harness.client.app.state.settings.phase2b1_allowlisted_user_ids_csv = "user-2"
    assert (
        client.post(
            "/api/v1/jobs",
            json={
                "upload_id": saved["id"],
                "idempotency_key": "real-request-002",
                "pipeline": "phase2b1_txt_evidence_summary",
            },
        ).status_code
        == 403
    )

    beta_harness.client.app.state.settings.phase2b1_allowlisted_user_ids_csv = "user-1"
    allowed = client.post(
        "/api/v1/jobs",
        json={
            "upload_id": saved["id"],
            "idempotency_key": "real-request-003",
            "pipeline": "phase2b1_txt_evidence_summary",
        },
    )
    assert allowed.status_code == 201
    assert allowed.json()["pipeline"] == "phase2b1_txt_evidence_summary"
    me = client.get("/api/v1/auth/me").json()
    assert me["available_pipelines"] == [
        "phase2a_smoke",
        "phase2b1_txt_evidence_summary",
    ]


@pytest.mark.parametrize("forbidden_field", ["provider", "model", "base_url"])
def test_job_request_rejects_provider_policy_overrides(
    beta_harness: BetaHarness,
    forbidden_field: str,
) -> None:
    client = beta_harness.client
    register(client)
    saved = upload(client)
    response = client.post(
        "/api/v1/jobs",
        json={
            "upload_id": saved["id"],
            "idempotency_key": f"override-{forbidden_field}",
            "pipeline": "phase2a_smoke",
            forbidden_field: "attacker-controlled",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_idempotency_key_conflicts_across_upload_and_pipeline(beta_harness: BetaHarness) -> None:
    client = beta_harness.client
    register(client)
    first_upload = upload(client, filename="first.txt", content=b"first")
    second_upload = upload(client, filename="second.txt", content=b"second")
    create_job(client, first_upload["id"], key="shared-request-001")

    cross_upload = client.post(
        "/api/v1/jobs",
        json={
            "upload_id": second_upload["id"],
            "idempotency_key": "shared-request-001",
            "pipeline": "phase2a_smoke",
        },
    )
    assert cross_upload.status_code == 409
    assert cross_upload.json()["error"]["code"] == "idempotency_conflict"

    client.app.state.settings.phase2b1_enabled = True
    client.app.state.settings.phase2b1_allowlisted_user_ids_csv = "user-1"
    cross_pipeline = client.post(
        "/api/v1/jobs",
        json={
            "upload_id": first_upload["id"],
            "idempotency_key": "shared-request-001",
            "pipeline": "phase2b1_txt_evidence_summary",
        },
    )
    assert cross_pipeline.status_code == 409
    assert cross_pipeline.json()["error"]["code"] == "idempotency_conflict"


def test_public_result_contract_excludes_internal_usage_details() -> None:
    result = Phase2B1TxtEvidenceResult(
        overview={"text": "故事围绕一次失踪展开。", "evidence_paragraph_ids": ["P000001"]},
        findings=(
            {
                "text": "失踪发生前已有异常征兆。",
                "evidence_paragraph_ids": ("P000001",),
            },
        ),
        paragraph_count=2,
        character_count=20,
    ).model_dump(mode="json")
    assert result["real_ai_analysis"] is True
    assert result["billing_status"] == "not_billable"
    assert result["charged_cny"] == 0
    forbidden = {
        "provider",
        "model",
        "provider_request_id",
        "provider_cost_cny",
        "pricing_version",
        "error_code",
    }
    assert forbidden.isdisjoint(result)


def test_result_endpoint_returns_only_validated_public_evidence(beta_harness: BetaHarness) -> None:
    client = beta_harness.client
    register(client)
    client.app.state.settings.phase2b1_enabled = True
    client.app.state.settings.phase2b1_allowlisted_user_ids_csv = "user-1"
    saved = upload(client)
    job = client.post(
        "/api/v1/jobs",
        json={
            "upload_id": saved["id"],
            "idempotency_key": "real-result-001",
            "pipeline": "phase2b1_txt_evidence_summary",
        },
    ).json()
    public_result = Phase2B1TxtEvidenceResult(
        overview={"text": "故事围绕一次失踪展开。", "evidence_paragraph_ids": ["P000001"]},
        findings=(
            {
                "text": "失踪前出现异常征兆。",
                "evidence_paragraph_ids": ("P000001",),
            },
        ),
        paragraph_count=2,
        character_count=20,
    ).model_dump(mode="json")
    with beta_harness.database.session() as session:
        stored_job = session.get(OnlineAnalysisJob, job["id"])
        assert stored_job is not None
        stored_job.status = "succeeded"
        stored_job.progress = 100
        stored_job.result_json = public_result

    response = client.get(f"/api/v1/jobs/{job['id']}/result")
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"job_id": job["id"], "result": public_result}
    serialized = response.text
    for forbidden_value in (
        "deepseek",
        "deepseek-v4-flash",
        "provider_request_id",
        "provider_cost_cny",
        "pricing_version",
        "error_code",
    ):
        assert forbidden_value not in serialized


def test_attempt_unique_boundary_is_deterministic(beta_harness: BetaHarness) -> None:
    repository = OnlineRepository()
    with beta_harness.database.session() as session:
        first, first_created = repository.begin_model_attempt(
            session,
            job_id="job-usage-unique",
            user_id="user-1",
            attempt_no=1,
            pricing=_pricing(),
        )
        repeated, repeated_created = repository.begin_model_attempt(
            session,
            job_id="job-usage-unique",
            user_id="user-1",
            attempt_no=1,
            pricing=_pricing(),
        )
        assert first_created is True
        assert repeated_created is False
        assert first.id == repeated.id
        assert session.scalar(select(func.count()).select_from(ModelUsageLedger)) == 1
