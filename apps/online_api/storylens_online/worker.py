from __future__ import annotations

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
from storylens_online.db.session import OnlineDatabase
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
    ) -> None:
        self.database = database
        self.storage = storage
        self.lease_seconds = lease_seconds
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
            result = Phase2AResult(
                character_count=len(text),
                nonempty_line_count=sum(1 for line in text.splitlines() if line.strip()),
                file_size_bytes=len(content),
                sha256=digest,
                processing_duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
            )
            with self.database.session() as session:
                self.repository.mark_succeeded(
                    session,
                    job.id,
                    result.model_dump(mode="json"),
                )
            return True
        except FileNotFoundError:
            self._record_failure(job.id, "upload_missing")
        except ProcessingFailure as exc:
            self._record_failure(job.id, exc.public_code)
        # A worker must convert unexpected per-job failures into a stable public state;
        # the process loop remains alive and never exposes exception details to users.
        except Exception:  # noqa: BLE001
            self._record_failure(job.id, "processing_failed")
        return False

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
    worker = Phase2AWorker(
        database,
        storage,
        lease_seconds=settings.worker_lease_seconds,
    )
    stop_event = Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    def recover_job(job_id: str) -> None:
        with database.session() as session:
            worker.repository.reset_recovered_job(session, job_id)

    runner = WorkerRunner(
        queue,
        worker,
        recover_job,
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
        queue.close()
        database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
