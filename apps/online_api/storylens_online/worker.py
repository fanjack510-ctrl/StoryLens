from __future__ import annotations

import asyncio
import hashlib
import logging
import signal
import time
from collections.abc import Callable
from functools import partial
from threading import Event
from types import FrameType
from typing import Protocol, TypeVar

from redis.exceptions import (
    AuthenticationError,
)
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)

from storylens_online.config import OnlineSettings
from storylens_online.contracts.beta import Phase2AResult
from storylens_online.contracts.billing import ModelAttemptStatus, ModelPricingSnapshot
from storylens_online.db.models import OnlineAnalysisJob
from storylens_online.db.session import OnlineDatabase
from storylens_online.providers.base import (
    ModelProvider,
    ModelResponse,
    ModelUsage,
    ProviderRequestError,
)
from storylens_online.providers.factory import create_phase2b1_provider
from storylens_online.services.model_cost import calculate_internal_model_cost
from storylens_online.services.phase2b1_analysis import (
    build_phase2b1_request,
    phase2b1_pricing_snapshot,
    split_evidence_paragraphs,
    validate_phase2b1_provider_output,
)
from storylens_online.services.queue import RedisJobQueue, WorkerJobQueue
from storylens_online.services.repository import OnlineRepository
from storylens_online.services.storage import SecureUploadStorage

LOGGER = logging.getLogger("storylens_online.worker")
QueueResult = TypeVar("QueueResult")


class JobProcessor(Protocol):
    def process_job(self, job_id: str) -> bool: ...


class ProcessingFailure(Exception):
    def __init__(self, public_code: str) -> None:
        super().__init__(public_code)
        self.public_code = public_code


class Phase2AWorker:
    def __init__(
        self,
        database: OnlineDatabase,
        storage: SecureUploadStorage,
        *,
        lease_seconds: int,
        settings: OnlineSettings | None = None,
        provider: ModelProvider | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.database = database
        self.storage = storage
        self.lease_seconds = lease_seconds
        self.settings = settings
        self.provider = provider
        self.sleep = sleep
        self.repository = OnlineRepository()

    def process_job(self, job_id: str) -> bool:
        with self.database.session() as session:
            claimed = self.repository.claim_job(session, job_id, self.lease_seconds)
        if claimed is None:
            return False
        job, upload = claimed

        started = time.perf_counter()
        try:
            content = self.storage.read(upload.storage_key)
            digest = hashlib.sha256(content).hexdigest()
            if digest != upload.sha256:
                raise ProcessingFailure("upload_integrity_mismatch")
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ProcessingFailure("upload_invalid_encoding") from exc
            if job.pipeline == "phase2a_smoke":
                return self._process_phase2a(job, content, text, digest, started)
            if job.pipeline == "phase2b1_txt_evidence_summary":
                return self._process_phase2b1(job, content, text)
            raise ProcessingFailure("pipeline_not_supported")
        except FileNotFoundError:
            self._record_failure(job.id, "upload_missing")
        except ProcessingFailure as exc:
            self._record_failure(job.id, exc.public_code)
        # A worker must convert unexpected per-job failures into a stable public state;
        # the process loop remains alive and never exposes exception details to users.
        except Exception:  # noqa: BLE001
            self._record_failure(job.id, "processing_failed")
        return False

    def _process_phase2a(
        self,
        job: OnlineAnalysisJob,
        content: bytes,
        text: str,
        digest: str,
        started: float,
    ) -> bool:
        result = Phase2AResult(
            character_count=len(text),
            nonempty_line_count=sum(1 for line in text.splitlines() if line.strip()),
            file_size_bytes=len(content),
            sha256=digest,
            processing_duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
        )
        with self.database.session() as session:
            self.repository.mark_succeeded(session, job.id, result.model_dump(mode="json"))
        return True

    def _process_phase2b1(
        self,
        job: OnlineAnalysisJob,
        content: bytes,
        text: str,
    ) -> bool:
        settings = self.settings
        if (
            settings is None
            or not settings.phase2b1_enabled
            or job.user_id not in settings.phase2b1_allowlisted_user_ids
            or self.provider is None
        ):
            raise ProcessingFailure("phase2b1_not_available")
        if len(content) > settings.phase2b1_text_max_bytes:
            raise ProcessingFailure("phase2b1_text_bytes_exceeded")
        if not text or len(text) > settings.phase2b1_text_max_characters:
            raise ProcessingFailure("phase2b1_text_characters_exceeded")

        paragraphs = split_evidence_paragraphs(text)
        if not paragraphs:
            raise ProcessingFailure("phase2b1_text_empty")
        request, prompt_token_upper_bound = build_phase2b1_request(
            paragraphs,
            max_completion_tokens=settings.phase2b1_max_completion_tokens,
        )
        if prompt_token_upper_bound > settings.phase2b1_prompt_max_tokens:
            raise ProcessingFailure("phase2b1_prompt_tokens_exceeded")

        pricing = phase2b1_pricing_snapshot(
            provider=settings.phase2b1_provider,
            model=settings.phase2b1_model,
            pricing_version=settings.phase2b1_pricing_version,
            input_per_million_cny=settings.phase2b1_input_per_million_cny,
            cached_input_per_million_cny=settings.phase2b1_cached_per_million_cny,
            output_per_million_cny=settings.phase2b1_output_per_million_cny,
        )
        valid_ids = frozenset(paragraph_id for paragraph_id, _ in paragraphs)

        with self.database.session() as session:
            if self.repository.recover_started_model_attempts(session, job.id):
                self.repository.mark_failed(session, job.id, "provider_outcome_unknown")
                return False
            attempts = self.repository.list_model_attempts(session, job.id)
            if any(
                attempt.status
                in {
                    ModelAttemptStatus.UNKNOWN.value,
                    ModelAttemptStatus.ACCOUNTING_INCOMPLETE.value,
                }
                for attempt in attempts
            ):
                self.repository.mark_failed(session, job.id, "provider_accounting_incomplete")
                return False
            next_attempt = max((attempt.attempt_no for attempt in attempts), default=0) + 1

        while next_attempt <= settings.phase2b1_max_provider_calls:
            if not self._provider_attempt_within_cost_cap(
                job.id,
                prompt_token_upper_bound,
                pricing,
            ):
                raise ProcessingFailure("provider_cost_cap_exceeded")

            with self.database.session() as session:
                attempt, created = self.repository.begin_model_attempt(
                    session,
                    job_id=job.id,
                    user_id=job.user_id,
                    attempt_no=next_attempt,
                    pricing=pricing,
                )
                if not created or attempt.status != ModelAttemptStatus.STARTED.value:
                    raise ProcessingFailure("provider_attempt_conflict")

            try:
                response = asyncio.run(self.provider.generate(request))
            except ProviderRequestError as exc:
                should_retry = self._record_provider_error(job.id, next_attempt, exc)
                if not should_retry:
                    return False
                if next_attempt >= settings.phase2b1_max_provider_calls:
                    self._record_failure(job.id, "provider_attempt_limit_exceeded")
                    return False
                self.sleep(self._retry_delay(next_attempt, exc.retry_after_seconds))
                next_attempt += 1
                continue

            if self._usage_exceeds_limits(response.usage):
                self._finish_response_attempt(
                    job.id,
                    next_attempt,
                    response,
                    status=ModelAttemptStatus.FAILED,
                    error_code="provider_usage_limit_exceeded",
                )
                self._record_failure(job.id, "provider_usage_limit_exceeded")
                return False

            try:
                result = validate_phase2b1_provider_output(
                    response.text,
                    valid_paragraph_ids=valid_ids,
                    paragraph_count=len(paragraphs),
                    character_count=len(text),
                )
            except ValueError as exc:
                error_code = str(exc)
                self._finish_response_attempt(
                    job.id,
                    next_attempt,
                    response,
                    status=ModelAttemptStatus.INVALID_RESPONSE,
                    error_code=error_code,
                )
                if not self._aggregate_within_cost_cap(job.id):
                    self._record_failure(job.id, "provider_cost_cap_exceeded")
                    return False
                if next_attempt >= settings.phase2b1_max_provider_calls:
                    self._record_failure(job.id, "provider_response_invalid")
                    return False
                self.sleep(self._retry_delay(next_attempt, None))
                next_attempt += 1
                continue

            with self.database.session() as session:
                self.repository.finish_model_attempt(
                    session,
                    job_id=job.id,
                    attempt_no=next_attempt,
                    status=ModelAttemptStatus.SUCCEEDED,
                    http_request_sent=True,
                    usage_reported=True,
                    total_tokens=response.usage.total_tokens,
                    input_tokens=response.usage.input_tokens,
                    cached_tokens=response.usage.cached_tokens,
                    output_tokens=response.usage.output_tokens,
                    provider_request_id=response.provider_request_id,
                )
                aggregate = self.repository.aggregate_model_usage(session, job.id)
                if aggregate.provider_cost_cny > settings.phase2b1_cost_cap_cny:
                    self.repository.mark_failed(session, job.id, "provider_cost_cap_exceeded")
                    return False
                self.repository.mark_succeeded(
                    session,
                    job.id,
                    result.model_dump(mode="json"),
                )
            return True

        self._record_failure(job.id, "provider_attempt_limit_exceeded")
        return False

    def _provider_attempt_within_cost_cap(
        self,
        job_id: str,
        prompt_token_upper_bound: int,
        pricing: ModelPricingSnapshot,
    ) -> bool:
        assert self.settings is not None
        worst_case = calculate_internal_model_cost(
            input_tokens=prompt_token_upper_bound,
            cached_tokens=0,
            output_tokens=self.settings.phase2b1_max_completion_tokens,
            pricing=pricing,
        ).provider_cost_cny
        with self.database.session() as session:
            aggregate = self.repository.aggregate_model_usage(session, job_id)
        return aggregate.provider_cost_cny + worst_case <= self.settings.phase2b1_cost_cap_cny

    def _aggregate_within_cost_cap(self, job_id: str) -> bool:
        assert self.settings is not None
        with self.database.session() as session:
            aggregate = self.repository.aggregate_model_usage(session, job_id)
        return aggregate.provider_cost_cny <= self.settings.phase2b1_cost_cap_cny

    def _usage_exceeds_limits(self, usage: ModelUsage) -> bool:
        assert self.settings is not None
        return (
            usage.input_tokens > self.settings.phase2b1_prompt_max_tokens
            or usage.output_tokens > self.settings.phase2b1_max_completion_tokens
        )

    def _finish_response_attempt(
        self,
        job_id: str,
        attempt_no: int,
        response: ModelResponse,
        *,
        status: ModelAttemptStatus,
        error_code: str | None,
    ) -> None:
        with self.database.session() as session:
            self.repository.finish_model_attempt(
                session,
                job_id=job_id,
                attempt_no=attempt_no,
                status=status,
                http_request_sent=True,
                usage_reported=True,
                total_tokens=response.usage.total_tokens,
                input_tokens=response.usage.input_tokens,
                cached_tokens=response.usage.cached_tokens,
                output_tokens=response.usage.output_tokens,
                provider_request_id=response.provider_request_id,
                error_code=error_code,
            )

    def _record_provider_error(
        self,
        job_id: str,
        attempt_no: int,
        error: ProviderRequestError,
    ) -> bool:
        usage = error.usage
        is_unknown = error.http_request_sent and error.error_code in {
            "PROVIDER_READ_TIMEOUT",
            "PROVIDER_WRITE_TIMEOUT",
            "PROVIDER_CONNECTION_INTERRUPTED",
        }
        is_retryable = (
            not error.http_request_sent
            and error.error_code in {"PROVIDER_CONNECT_ERROR", "PROVIDER_CONNECT_TIMEOUT"}
        ) or error.error_code in {"PROVIDER_RATE_LIMITED", "PROVIDER_RESPONSE_INVALID"}
        if is_unknown:
            status = ModelAttemptStatus.UNKNOWN
            public_code = "provider_outcome_unknown"
        elif (
            error.http_request_sent
            and usage is None
            and error.error_code != "PROVIDER_RATE_LIMITED"
        ):
            status = ModelAttemptStatus.ACCOUNTING_INCOMPLETE
            public_code = "provider_accounting_incomplete"
            is_retryable = False
        elif error.error_code == "PROVIDER_RESPONSE_INVALID":
            status = ModelAttemptStatus.INVALID_RESPONSE
            public_code = "provider_response_invalid"
        else:
            status = ModelAttemptStatus.FAILED
            public_code = "provider_request_failed"

        with self.database.session() as session:
            self.repository.finish_model_attempt(
                session,
                job_id=job_id,
                attempt_no=attempt_no,
                status=status,
                http_request_sent=error.http_request_sent,
                usage_reported=usage is not None,
                total_tokens=usage.total_tokens if usage is not None else 0,
                input_tokens=usage.input_tokens if usage is not None else 0,
                cached_tokens=usage.cached_tokens if usage is not None else 0,
                output_tokens=usage.output_tokens if usage is not None else 0,
                provider_request_id=error.provider_request_id,
                error_code=error.error_code.lower(),
            )
        if not self._aggregate_within_cost_cap(job_id):
            self._record_failure(job_id, "provider_cost_cap_exceeded")
            return False
        if not is_retryable:
            self._record_failure(job_id, public_code)
        return is_retryable

    def _retry_delay(self, attempt_no: int, retry_after_seconds: float | None) -> float:
        assert self.settings is not None
        if retry_after_seconds is not None:
            return min(retry_after_seconds, self.settings.phase2b1_retry_max_seconds)
        return min(
            self.settings.phase2b1_retry_initial_seconds * (2 ** (attempt_no - 1)),
            self.settings.phase2b1_retry_max_seconds,
        )

    def recover_job(self, job_id: str) -> None:
        with self.database.session() as session:
            job = session.get(OnlineAnalysisJob, job_id)
            if job is None or job.status != "running":
                return
            if job.pipeline != "phase2b1_txt_evidence_summary":
                self.repository.reset_recovered_job(session, job_id)
                return
            recovered = self.repository.recover_started_model_attempts(session, job_id)
            attempts = self.repository.list_model_attempts(session, job_id)
            ambiguous = recovered > 0 or any(
                attempt.status
                in {
                    ModelAttemptStatus.UNKNOWN.value,
                    ModelAttemptStatus.ACCOUNTING_INCOMPLETE.value,
                }
                for attempt in attempts
            )
            if ambiguous:
                self.repository.mark_failed(session, job_id, "provider_outcome_unknown")
            else:
                self.repository.reset_recovered_job(session, job_id)

    def _record_failure(self, job_id: str, error_code: str) -> None:
        with self.database.session() as session:
            self.repository.mark_failed(session, job_id, error_code)
        LOGGER.error("Phase 2A job %s failed with public code %s", job_id, error_code)


class WorkerRunner:
    """Keep queue transport failures separate from deterministic job execution."""

    def __init__(
        self,
        queue: WorkerJobQueue,
        processor: JobProcessor,
        recover_job: Callable[[str], None],
        *,
        poll_seconds: int,
        retry_initial_seconds: float,
        retry_max_seconds: float,
        stop_event: Event | None = None,
        wait_for_retry: Callable[[float], bool] | None = None,
    ) -> None:
        self.queue = queue
        self.processor = processor
        self.recover_job = recover_job
        self.poll_seconds = poll_seconds
        self.retry_initial_seconds = retry_initial_seconds
        self.retry_max_seconds = retry_max_seconds
        self.stop_event = stop_event or Event()
        self.wait_for_retry = wait_for_retry or self.stop_event.wait
        self._needs_recovery = True
        self._outage_logged = False
        self._next_retry_delay = retry_initial_seconds

    def run(self, *, max_idle_polls: int | None = None) -> None:
        if max_idle_polls is not None and max_idle_polls < 1:
            raise ValueError("max_idle_polls must be positive")
        idle_polls = 0
        while not self.stop_event.is_set():
            if self._needs_recovery:
                recovered_ok, recovered_job_ids = self._queue_call(
                    self.queue.recover_inflight,
                    mark_healthy=False,
                )
                if not recovered_ok:
                    continue
                self._needs_recovery = False
                for recovered_job_id in recovered_job_ids or []:
                    self.recover_job(recovered_job_id)

            if self.stop_event.is_set():
                break
            dequeued_ok, job_id = self._queue_call(lambda: self.queue.dequeue(self.poll_seconds))
            if not dequeued_ok:
                continue
            if job_id is None:
                idle_polls += 1
                if max_idle_polls is not None and idle_polls >= max_idle_polls:
                    return
                continue

            # Task execution is intentionally outside the Redis exception boundary.
            # A real job/database failure must remain visible and unacknowledged.
            self.processor.process_job(job_id)
            acknowledged, _ = self._queue_call(partial(self.queue.acknowledge, job_id))
            if not acknowledged:
                continue

    def _queue_call(
        self,
        operation: Callable[[], QueueResult],
        *,
        mark_healthy: bool = True,
    ) -> tuple[bool, QueueResult | None]:
        try:
            result = operation()
        except AuthenticationError:
            LOGGER.error("Redis queue authentication failed; worker is stopping.")
            raise
        except (RedisTimeoutError, RedisConnectionError):
            self._handle_transient_redis_failure()
            return False, None
        if mark_healthy:
            self._mark_redis_healthy()
        return True, result

    def _handle_transient_redis_failure(self) -> None:
        self._needs_recovery = True
        try:
            self.queue.reset_connections()
        except Exception:  # noqa: BLE001
            # Best-effort pool cleanup must not replace the original transient state.
            LOGGER.debug("Redis connection pool cleanup could not complete.")
        if not self._outage_logged:
            LOGGER.warning(
                "Redis queue temporarily unavailable; worker will retry with bounded backoff."
            )
            self._outage_logged = True
        delay = self._next_retry_delay
        self._next_retry_delay = min(delay * 2, self.retry_max_seconds)
        if self.wait_for_retry(delay):
            self.stop_event.set()

    def _mark_redis_healthy(self) -> None:
        if self._outage_logged:
            LOGGER.info("Redis queue connection recovered; worker resumed polling.")
        self._outage_logged = False
        self._next_retry_delay = self.retry_initial_seconds


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    settings = OnlineSettings()
    database = OnlineDatabase(settings.database_url)
    storage = SecureUploadStorage(settings.upload_dir, settings.upload_max_bytes)
    queue = RedisJobQueue(
        settings.redis_url,
        settings.job_queue_name,
        socket_timeout_seconds=settings.redis_socket_timeout_seconds,
        connect_timeout_seconds=settings.redis_connect_timeout_seconds,
    )
    provider = create_phase2b1_provider(settings) if settings.phase2b1_enabled else None
    worker = Phase2AWorker(
        database,
        storage,
        lease_seconds=settings.worker_lease_seconds,
        settings=settings,
        provider=provider,
    )
    stop_event = Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    runner = WorkerRunner(
        queue,
        worker,
        worker.recover_job,
        poll_seconds=settings.worker_poll_seconds,
        retry_initial_seconds=settings.worker_redis_retry_initial_seconds,
        retry_max_seconds=settings.worker_redis_retry_max_seconds,
        stop_event=stop_event,
    )
    try:
        runner.run()
    except KeyboardInterrupt:
        return 0
    except AuthenticationError:
        return 2
    finally:
        if provider is not None:
            asyncio.run(provider.aclose())
        queue.close()
        database.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
