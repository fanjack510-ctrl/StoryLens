from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storylens_online.contracts.billing import (
    ModelAttemptStatus,
    ModelPricingSnapshot,
    ModelUsageAggregate,
)
from storylens_online.db.models import ModelUsageLedger, OnlineAnalysisJob, OnlineBookUpload
from storylens_online.services.model_cost import (
    ZERO_CNY,
    ZERO_USD,
    calculate_internal_model_cost,
)
from storylens_online.services.storage import StoredUpload


class OnlineRepository:
    @staticmethod
    def create_upload(session: Session, user_id: str, stored: StoredUpload) -> OnlineBookUpload:
        upload = OnlineBookUpload(
            user_id=user_id,
            original_filename=stored.original_filename,
            storage_key=stored.storage_key,
            sha256=stored.sha256,
            file_size_bytes=stored.file_size_bytes,
        )
        session.add(upload)
        session.flush()
        return upload

    @staticmethod
    def get_upload_for_user(
        session: Session,
        upload_id: str,
        user_id: str,
    ) -> OnlineBookUpload | None:
        return session.scalar(
            select(OnlineBookUpload).where(
                OnlineBookUpload.id == upload_id,
                OnlineBookUpload.user_id == user_id,
            )
        )

    @staticmethod
    def create_or_get_job(
        session: Session,
        *,
        user_id: str,
        upload_id: str,
        idempotency_key: str,
        pipeline: str = "phase2a_smoke",
    ) -> tuple[OnlineAnalysisJob, bool]:
        existing = session.scalar(
            select(OnlineAnalysisJob).where(
                OnlineAnalysisJob.user_id == user_id,
                OnlineAnalysisJob.idempotency_key == idempotency_key,
            )
        )
        if existing:
            return existing, False

        job = OnlineAnalysisJob(
            user_id=user_id,
            upload_id=upload_id,
            idempotency_key=idempotency_key,
            status="queued",
            progress=0,
            pipeline=pipeline,
        )
        session.add(job)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(
                select(OnlineAnalysisJob).where(
                    OnlineAnalysisJob.user_id == user_id,
                    OnlineAnalysisJob.idempotency_key == idempotency_key,
                )
            )
            if existing is None:
                raise
            return existing, False
        return job, True

    @staticmethod
    def list_jobs(session: Session, user_id: str) -> list[OnlineAnalysisJob]:
        return list(
            session.scalars(
                select(OnlineAnalysisJob)
                .where(OnlineAnalysisJob.user_id == user_id)
                .order_by(OnlineAnalysisJob.created_at.desc())
                .limit(100)
            )
        )

    @staticmethod
    def get_job_for_user(
        session: Session,
        job_id: str,
        user_id: str,
    ) -> OnlineAnalysisJob | None:
        return session.scalar(
            select(OnlineAnalysisJob).where(
                OnlineAnalysisJob.id == job_id,
                OnlineAnalysisJob.user_id == user_id,
            )
        )

    @staticmethod
    def claim_job(
        session: Session,
        job_id: str,
        lease_seconds: int,
    ) -> tuple[OnlineAnalysisJob, OnlineBookUpload] | None:
        now = datetime.now(UTC)
        eligible = or_(
            OnlineAnalysisJob.status == "queued",
            and_(
                OnlineAnalysisJob.status == "running",
                OnlineAnalysisJob.lease_expires_at.is_not(None),
                OnlineAnalysisJob.lease_expires_at < now,
            ),
        )
        claimed = session.execute(
            update(OnlineAnalysisJob)
            .where(OnlineAnalysisJob.id == job_id, eligible)
            .values(
                status="running",
                progress=10,
                public_error_code=None,
                started_at=now,
                finished_at=None,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                attempt_count=OnlineAnalysisJob.attempt_count + 1,
            )
        )
        if claimed.rowcount != 1:
            return None
        job = session.get(OnlineAnalysisJob, job_id)
        if job is None:
            return None
        upload = session.get(OnlineBookUpload, job.upload_id)
        if upload is None or upload.user_id != job.user_id:
            OnlineRepository.mark_failed(session, job.id, "upload_not_found")
            return None
        return job, upload

    @staticmethod
    def mark_succeeded(
        session: Session,
        job_id: str,
        result: dict[str, object],
    ) -> None:
        session.execute(
            update(OnlineAnalysisJob)
            .where(OnlineAnalysisJob.id == job_id, OnlineAnalysisJob.status == "running")
            .values(
                status="succeeded",
                progress=100,
                result_json=result,
                public_error_code=None,
                finished_at=datetime.now(UTC),
                lease_expires_at=None,
            )
        )

    @staticmethod
    def mark_failed(session: Session, job_id: str, error_code: str) -> None:
        session.execute(
            update(OnlineAnalysisJob)
            .where(
                OnlineAnalysisJob.id == job_id,
                OnlineAnalysisJob.status.in_(("queued", "running")),
            )
            .values(
                status="failed",
                progress=100,
                result_json=None,
                public_error_code=error_code,
                finished_at=datetime.now(UTC),
                lease_expires_at=None,
            )
        )

    @staticmethod
    def reset_recovered_job(session: Session, job_id: str) -> None:
        session.execute(
            update(OnlineAnalysisJob)
            .where(OnlineAnalysisJob.id == job_id, OnlineAnalysisJob.status == "running")
            .values(
                status="queued",
                progress=0,
                lease_expires_at=None,
                public_error_code=None,
            )
        )

    @staticmethod
    def begin_model_attempt(
        session: Session,
        *,
        job_id: str,
        user_id: str,
        attempt_no: int,
        pricing: ModelPricingSnapshot,
    ) -> tuple[ModelUsageLedger, bool]:
        """Persist the deterministic attempt boundary before any Provider I/O."""

        if attempt_no < 1:
            raise ValueError("Provider attempt number must be positive")
        invocation_id = f"{job_id}:{attempt_no}"
        if len(invocation_id) > 128:
            raise ValueError("Provider invocation id is too long")
        existing = session.scalar(
            select(ModelUsageLedger).where(
                ModelUsageLedger.analysis_run_id == job_id,
                ModelUsageLedger.attempt_no == attempt_no,
            )
        )
        if existing is not None:
            return existing, False
        attempt = ModelUsageLedger(
            invocation_id=invocation_id,
            analysis_run_id=job_id,
            attempt_no=attempt_no,
            user_id=user_id,
            provider=pricing.provider,
            model=pricing.model,
            pricing_version=pricing.pricing_version,
            status=ModelAttemptStatus.STARTED.value,
            request_sent_at=pricing.request_sent_at or datetime.now(UTC),
            input_tokens=0,
            cached_tokens=0,
            prompt_cache_miss_tokens=0,
            output_tokens=0,
            total_tokens=0,
            usage_reported=False,
            http_request_sent=False,
            pricing_currency=pricing.pricing_currency,
            pricing_tier=pricing.pricing_tier,
            cache_hit_usd_per_million=pricing.cache_hit_usd_per_million,
            cache_miss_usd_per_million=pricing.cache_miss_usd_per_million,
            output_usd_per_million=pricing.output_usd_per_million,
            provider_cost_usd=ZERO_USD,
            fx_rate_to_cny=pricing.fx_rate_to_cny,
            fx_rate_version=pricing.fx_rate_version,
            input_per_million_cny=pricing.input_per_million_cny,
            cached_input_per_million_cny=pricing.cached_input_per_million_cny,
            output_per_million_cny=pricing.output_per_million_cny,
            provider_cost_cny=ZERO_CNY,
            customer_charge_cny=ZERO_CNY,
            disposition="not_billable",
        )
        session.add(attempt)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            existing = session.scalar(
                select(ModelUsageLedger).where(
                    ModelUsageLedger.analysis_run_id == job_id,
                    ModelUsageLedger.attempt_no == attempt_no,
                )
            )
            if existing is None:
                raise
            return existing, False
        return attempt, True

    @staticmethod
    def finish_model_attempt(
        session: Session,
        *,
        job_id: str,
        attempt_no: int,
        status: ModelAttemptStatus,
        http_request_sent: bool,
        usage_reported: bool,
        total_tokens: int,
        input_tokens: int = 0,
        cached_tokens: int = 0,
        prompt_cache_miss_tokens: int | None = None,
        output_tokens: int = 0,
        provider_request_id: str | None = None,
        provider_response_model: str | None = None,
        system_fingerprint: str | None = None,
        error_code: str | None = None,
    ) -> ModelUsageLedger:
        if status is ModelAttemptStatus.STARTED:
            raise ValueError("a completed Provider attempt cannot remain started")
        attempt = session.scalar(
            select(ModelUsageLedger).where(
                ModelUsageLedger.analysis_run_id == job_id,
                ModelUsageLedger.attempt_no == attempt_no,
            )
        )
        if attempt is None:
            raise ValueError("Provider attempt does not exist")
        if attempt.status != ModelAttemptStatus.STARTED.value:
            return attempt
        if not usage_reported and any((input_tokens, cached_tokens, output_tokens, total_tokens)):
            raise ValueError("token counts require Provider-reported usage")
        request_sent_at = attempt.request_sent_at
        if request_sent_at is not None:
            request_sent_at = (
                request_sent_at.replace(tzinfo=UTC)
                if request_sent_at.tzinfo is None
                else request_sent_at.astimezone(UTC)
            )
        pricing = ModelPricingSnapshot(
            provider=attempt.provider,
            model=attempt.model,
            pricing_version=attempt.pricing_version,
            pricing_currency=attempt.pricing_currency,
            pricing_tier=attempt.pricing_tier,
            cache_hit_usd_per_million=attempt.cache_hit_usd_per_million,
            cache_miss_usd_per_million=attempt.cache_miss_usd_per_million,
            output_usd_per_million=attempt.output_usd_per_million,
            fx_rate_to_cny=attempt.fx_rate_to_cny,
            fx_rate_version=attempt.fx_rate_version,
            request_sent_at=request_sent_at,
            input_per_million_cny=attempt.input_per_million_cny,
            cached_input_per_million_cny=attempt.cached_input_per_million_cny,
            output_per_million_cny=attempt.output_per_million_cny,
        )
        cost = calculate_internal_model_cost(
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            pricing=pricing,
            prompt_cache_miss_tokens=prompt_cache_miss_tokens,
        )
        attempt.status = status.value
        attempt.provider_request_id = provider_request_id
        attempt.provider_response_model = provider_response_model
        attempt.system_fingerprint = system_fingerprint
        attempt.input_tokens = cost.input_tokens
        attempt.cached_tokens = cost.cached_tokens
        attempt.prompt_cache_miss_tokens = cost.prompt_cache_miss_tokens
        attempt.output_tokens = cost.output_tokens
        attempt.total_tokens = cost.total_tokens
        attempt.usage_reported = usage_reported
        attempt.http_request_sent = http_request_sent
        attempt.error_code = error_code
        attempt.provider_cost_usd = cost.provider_cost_usd if usage_reported else ZERO_USD
        attempt.provider_cost_cny = cost.provider_cost_cny if usage_reported else ZERO_CNY
        attempt.customer_charge_cny = ZERO_CNY
        attempt.disposition = "not_billable"
        attempt.completed_at = datetime.now(UTC)
        session.flush()
        return attempt

    @staticmethod
    def recover_started_model_attempts(session: Session, job_id: str) -> int:
        """Conservatively close crash-left attempts whose request state is ambiguous."""

        recovered = session.execute(
            update(ModelUsageLedger)
            .where(
                ModelUsageLedger.analysis_run_id == job_id,
                ModelUsageLedger.status == ModelAttemptStatus.STARTED.value,
            )
            .values(
                status=ModelAttemptStatus.UNKNOWN.value,
                http_request_sent=True,
                usage_reported=False,
                error_code="attempt_interrupted",
                completed_at=datetime.now(UTC),
                customer_charge_cny=ZERO_CNY,
                disposition="not_billable",
            )
        )
        return int(recovered.rowcount or 0)

    @staticmethod
    def list_model_attempts(session: Session, job_id: str) -> list[ModelUsageLedger]:
        return list(
            session.scalars(
                select(ModelUsageLedger)
                .where(ModelUsageLedger.analysis_run_id == job_id)
                .order_by(ModelUsageLedger.attempt_no)
            )
        )

    @staticmethod
    def aggregate_model_usage(session: Session, job_id: str) -> ModelUsageAggregate:
        attempts = OnlineRepository.list_model_attempts(session, job_id)
        return ModelUsageAggregate(
            analysis_run_id=job_id,
            attempt_count=len(attempts),
            input_tokens=sum(attempt.input_tokens for attempt in attempts),
            cached_tokens=sum(attempt.cached_tokens for attempt in attempts),
            output_tokens=sum(attempt.output_tokens for attempt in attempts),
            total_tokens=sum(attempt.total_tokens for attempt in attempts),
            provider_cost_usd=sum(
                (attempt.provider_cost_usd for attempt in attempts),
                start=Decimal("0.000000000"),
            ),
            provider_cost_cny=sum(
                (attempt.provider_cost_cny for attempt in attempts),
                start=Decimal("0.000000"),
            ),
            usage_complete=not any(
                attempt.status
                in {
                    ModelAttemptStatus.UNKNOWN.value,
                    ModelAttemptStatus.ACCOUNTING_INCOMPLETE.value,
                }
                or (
                    attempt.status
                    in {
                        ModelAttemptStatus.SUCCEEDED.value,
                        ModelAttemptStatus.INVALID_RESPONSE.value,
                    }
                    and not attempt.usage_reported
                )
                for attempt in attempts
            ),
            has_unknown_attempt=any(
                attempt.status == ModelAttemptStatus.UNKNOWN.value for attempt in attempts
            ),
            customer_charge_cny=ZERO_CNY,
        )
