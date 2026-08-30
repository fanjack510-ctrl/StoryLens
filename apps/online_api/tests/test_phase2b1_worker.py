# ruff: noqa: F811 - importing the shared pytest fixture is intentional.
from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from storylens_online.config import OnlineSettings
from storylens_online.contracts.billing import ModelAttemptStatus, ModelPricingSnapshot
from storylens_online.db.models import (
    BillingReservation,
    ModelUsageLedger,
    OnlineAnalysisJob,
    RechargeOrder,
    WalletAccount,
    WalletTransaction,
)
from storylens_online.providers.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ProviderRequestError,
)
from storylens_online.services.repository import OnlineRepository
from storylens_online.worker import Phase2AWorker
from test_beta_vertical_slice import (
    BetaHarness,
    beta_harness,  # noqa: F401 - imported so pytest registers the shared fixture
    create_job,
    register,
    upload,
)


class FakeProvider(ModelProvider):
    name = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, outcomes: list[ModelResponse | ProviderRequestError]) -> None:
        self.outcomes = outcomes
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, ProviderRequestError):
            raise outcome
        return outcome


def worker_settings(
    beta_harness: BetaHarness,
    **overrides: object,
) -> OnlineSettings:
    values: dict[str, object] = {
        "database_url": "postgresql+psycopg://storylens@postgres:5432/storylens_online",
        "frontend_origin": "https://storylens.example.com",
        "upload_dir": str(beta_harness.storage.root),
        "upload_max_bytes": 64,
        "phase2b1_enabled": True,
        "phase2b1_allowlisted_user_ids_csv": "user-1",
    }
    values.update(overrides)
    return OnlineSettings(**values)


def create_real_job(
    beta_harness: BetaHarness, content: bytes = "第一段。\n第二段。".encode()
) -> dict:
    client = beta_harness.client
    register(client)
    client.app.state.settings.phase2b1_enabled = True
    client.app.state.settings.phase2b1_allowlisted_user_ids_csv = "user-1"
    saved = upload(client, content=content)
    response = client.post(
        "/api/v1/jobs",
        json={
            "upload_id": saved["id"],
            "idempotency_key": "phase2b1-worker-001",
            "pipeline": "phase2b1_txt_evidence_summary",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def provider_response(
    *,
    body: dict | str | None = None,
    input_tokens: int = 100,
    output_tokens: int = 50,
    total_tokens: int = 150,
    request_id: str = "request-1",
) -> ModelResponse:
    if body is None:
        body = {
            "overview": {
                "text": "两段文字共同建立了事件背景。",
                "evidence_paragraph_ids": ["P000001", "P000002"],
            },
            "findings": [
                {
                    "text": "第二段推进了第一段提出的事件。",
                    "evidence_paragraph_ids": ["P000002"],
                }
            ],
        }
    return ModelResponse(
        text=json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else body,
        model="deepseek-v4-flash",
        usage=ModelUsage(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=total_tokens,
            prompt_cache_hit_tokens=0,
            prompt_cache_miss_tokens=input_tokens,
        ),
        provider_request_id=request_id,
        system_fingerprint="fp_test",
    )


def make_worker(
    beta_harness: BetaHarness,
    provider: FakeProvider,
    *,
    sleeps: list[float] | None = None,
    settings_overrides: dict[str, object] | None = None,
) -> Phase2AWorker:
    observed_sleeps = sleeps if sleeps is not None else []
    return Phase2AWorker(
        beta_harness.database,
        beta_harness.storage,
        lease_seconds=900,
        settings=worker_settings(beta_harness, **(settings_overrides or {})),
        provider=provider,
        sleep=observed_sleeps.append,
    )


def test_real_pipeline_succeeds_with_evidence_and_internal_usage_only(
    beta_harness: BetaHarness,
) -> None:
    job = create_real_job(beta_harness)
    provider = FakeProvider([provider_response()])
    worker = make_worker(beta_harness, provider)

    assert worker.process_job(job["id"]) is True
    assert worker.process_job(job["id"]) is False
    result = beta_harness.client.get(f"/api/v1/jobs/{job['id']}/result").json()["result"]
    assert result["pipeline"] == "phase2b1_txt_evidence_summary"
    assert result["overview"]["evidence_paragraph_ids"] == ["P000001", "P000002"]
    assert result["real_ai_analysis"] is True
    assert result["billing_status"] == "not_billable"
    assert result["charged_cny"] == 0
    assert "provider_request_id" not in result
    assert len(provider.requests) == 1
    payload = provider.requests[0]
    assert payload.max_completion_tokens == 2_048
    assert "P000001" in payload.messages[1]["content"]

    with beta_harness.database.session() as session:
        ledger = session.scalar(select(ModelUsageLedger))
        assert ledger is not None
        assert ledger.status == ModelAttemptStatus.SUCCEEDED.value
        assert ledger.provider_request_id == "request-1"
        assert ledger.provider_response_model == "deepseek-v4-flash"
        assert ledger.system_fingerprint == "fp_test"
        assert ledger.pricing_currency == "USD"
        assert ledger.pricing_tier in {"peak", "off_peak"}
        assert ledger.prompt_cache_miss_tokens == 100
        assert ledger.total_tokens == 150
        assert ledger.customer_charge_cny == 0
        for model in (WalletAccount, RechargeOrder, WalletTransaction, BillingReservation):
            assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize(
    ("first_outcome", "expected_first_status"),
    [
        (
            ProviderRequestError(
                error_code="PROVIDER_CONNECT_ERROR",
                http_request_sent=False,
            ),
            ModelAttemptStatus.FAILED.value,
        ),
        (
            ProviderRequestError(
                error_code="PROVIDER_RATE_LIMITED",
                http_request_sent=True,
                http_status_code=429,
                retry_after_seconds=3,
            ),
            ModelAttemptStatus.FAILED.value,
        ),
        (provider_response(body="", request_id="empty-content"), "invalid_response"),
        (provider_response(body="not-json", request_id="bad-json"), "invalid_response"),
        (
            provider_response(
                body={
                    "overview": {
                        "text": "引用了不存在的证据。",
                        "evidence_paragraph_ids": ["P999999"],
                    },
                    "findings": [
                        {
                            "text": "仍然是非法证据。",
                            "evidence_paragraph_ids": ["P999999"],
                        }
                    ],
                },
                request_id="bad-evidence",
            ),
            ModelAttemptStatus.INVALID_RESPONSE.value,
        ),
    ],
)
def test_retryable_failures_use_two_attempts_and_aggregate_usage(
    beta_harness: BetaHarness,
    first_outcome: ModelResponse | ProviderRequestError,
    expected_first_status: str,
) -> None:
    job = create_real_job(beta_harness)
    sleeps: list[float] = []
    provider = FakeProvider([first_outcome, provider_response(request_id="request-2")])
    worker = make_worker(beta_harness, provider, sleeps=sleeps)

    assert worker.process_job(job["id"]) is True
    assert len(provider.requests) == 2
    assert len(sleeps) == 1
    assert 0 < sleeps[0] <= 10
    with beta_harness.database.session() as session:
        attempts = OnlineRepository.list_model_attempts(session, job["id"])
        aggregate = OnlineRepository.aggregate_model_usage(session, job["id"])
        assert [attempt.attempt_no for attempt in attempts] == [1, 2]
        assert attempts[0].status == expected_first_status
        assert attempts[1].status == ModelAttemptStatus.SUCCEEDED.value
        expected_total = 300 if isinstance(first_outcome, ModelResponse) else 150
        assert aggregate.total_tokens == expected_total
        assert aggregate.customer_charge_cny == 0


def test_read_timeout_is_unknown_and_never_retried(beta_harness: BetaHarness) -> None:
    job = create_real_job(beta_harness)
    provider = FakeProvider(
        [
            ProviderRequestError(
                error_code="PROVIDER_READ_TIMEOUT",
                http_request_sent=True,
            ),
            provider_response(),
        ]
    )
    worker = make_worker(beta_harness, provider)

    assert worker.process_job(job["id"]) is False
    assert len(provider.requests) == 1
    with beta_harness.database.session() as session:
        stored = session.get(OnlineAnalysisJob, job["id"])
        attempts = OnlineRepository.list_model_attempts(session, job["id"])
        assert stored is not None and stored.public_error_code == "provider_outcome_unknown"
        assert attempts[0].status == ModelAttemptStatus.UNKNOWN.value
        assert OnlineRepository.aggregate_model_usage(session, job["id"]).usage_complete is False


def test_sent_failure_without_usage_is_accounting_incomplete(beta_harness: BetaHarness) -> None:
    job = create_real_job(beta_harness)
    provider = FakeProvider(
        [
            ProviderRequestError(
                error_code="PROVIDER_SERVER_ERROR",
                http_request_sent=True,
                http_status_code=503,
            )
        ]
    )
    worker = make_worker(beta_harness, provider)
    assert worker.process_job(job["id"]) is False
    with beta_harness.database.session() as session:
        attempts = OnlineRepository.list_model_attempts(session, job["id"])
        assert attempts[0].status == ModelAttemptStatus.ACCOUNTING_INCOMPLETE.value
        assert attempts[0].usage_reported is False


def test_server_error_with_usage_is_costed_but_not_retried(beta_harness: BetaHarness) -> None:
    job = create_real_job(beta_harness)
    provider = FakeProvider(
        [
            ProviderRequestError(
                error_code="PROVIDER_SERVER_ERROR",
                http_request_sent=True,
                http_status_code=503,
                provider_request_id="failed-request",
                usage=ModelUsage(
                    prompt_tokens=100,
                    completion_tokens=10,
                    total_tokens=110,
                    prompt_cache_hit_tokens=0,
                    prompt_cache_miss_tokens=100,
                ),
            ),
            provider_response(),
        ]
    )
    worker = make_worker(beta_harness, provider)
    assert worker.process_job(job["id"]) is False
    assert len(provider.requests) == 1
    with beta_harness.database.session() as session:
        attempts = OnlineRepository.list_model_attempts(session, job["id"])
        assert attempts[0].status == ModelAttemptStatus.FAILED.value
        assert attempts[0].usage_reported is True
        assert attempts[0].provider_cost_cny > 0


def test_preflight_cost_cap_stops_before_provider_io(beta_harness: BetaHarness) -> None:
    job = create_real_job(beta_harness)
    provider = FakeProvider([provider_response()])
    worker = make_worker(
        beta_harness,
        provider,
        settings_overrides={"phase2b1_cost_cap_cny": Decimal("0.000001")},
    )
    assert worker.process_job(job["id"]) is False
    assert provider.requests == []
    with beta_harness.database.session() as session:
        assert OnlineRepository.list_model_attempts(session, job["id"]) == []


def test_text_character_limit_stops_before_provider_io(beta_harness: BetaHarness) -> None:
    job = create_real_job(beta_harness)
    provider = FakeProvider([provider_response()])
    worker = make_worker(
        beta_harness,
        provider,
        settings_overrides={"phase2b1_text_max_characters": 1},
    )
    assert worker.process_job(job["id"]) is False
    assert provider.requests == []


def test_worker_defense_in_depth_rejects_removed_allowlist(beta_harness: BetaHarness) -> None:
    job = create_real_job(beta_harness)
    provider = FakeProvider([provider_response()])
    worker = make_worker(
        beta_harness,
        provider,
        settings_overrides={"phase2b1_allowlisted_user_ids_csv": ""},
    )
    assert worker.process_job(job["id"]) is False
    assert provider.requests == []


def test_crash_left_started_attempt_becomes_unknown_and_job_is_not_requeued(
    beta_harness: BetaHarness,
) -> None:
    job = create_real_job(beta_harness)
    pricing = ModelPricingSnapshot(
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
    with beta_harness.database.session() as session:
        claimed = OnlineRepository.claim_job(session, job["id"], lease_seconds=900)
        assert claimed is not None
        OnlineRepository.begin_model_attempt(
            session,
            job_id=job["id"],
            user_id="user-1",
            attempt_no=1,
            pricing=pricing,
        )

    worker = make_worker(beta_harness, FakeProvider([]))
    worker.recover_job(job["id"])
    with beta_harness.database.session() as session:
        stored = session.get(OnlineAnalysisJob, job["id"])
        attempts = OnlineRepository.list_model_attempts(session, job["id"])
        assert stored is not None and stored.status == "failed"
        assert stored.public_error_code == "provider_outcome_unknown"
        assert attempts[0].status == ModelAttemptStatus.UNKNOWN.value


def test_phase2a_smoke_never_calls_provider_or_writes_usage(beta_harness: BetaHarness) -> None:
    register(beta_harness.client)
    saved = upload(beta_harness.client)
    job = create_job(beta_harness.client, saved["id"])
    provider = FakeProvider([provider_response()])
    worker = make_worker(beta_harness, provider)
    assert worker.process_job(job["id"]) is True
    assert provider.requests == []
    with beta_harness.database.session() as session:
        assert session.scalar(select(func.count()).select_from(ModelUsageLedger)) == 0


def test_failure_logs_exclude_txt_prompt_and_secret(
    beta_harness: BetaHarness,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_text = "DO-NOT-LOG-TXT"
    job = create_real_job(beta_harness, content=f"{secret_text}\n第二段".encode())
    provider = FakeProvider(
        [ProviderRequestError(error_code="PROVIDER_READ_TIMEOUT", http_request_sent=True)]
    )
    worker = make_worker(beta_harness, provider)
    assert worker.process_job(job["id"]) is False
    log_text = caplog.text
    assert secret_text not in log_text
    assert "Bearer" not in log_text
    assert "messages" not in log_text
