from __future__ import annotations

import hashlib
import logging
import time

from storylens_online.config import OnlineSettings
from storylens_online.contracts.beta import Phase2AResult
from storylens_online.db.session import OnlineDatabase
from storylens_online.services.queue import RedisJobQueue
from storylens_online.services.repository import OnlineRepository
from storylens_online.services.storage import SecureUploadStorage

LOGGER = logging.getLogger("storylens_online.worker")


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


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    settings = OnlineSettings()
    database = OnlineDatabase(settings.database_url)
    storage = SecureUploadStorage(settings.upload_dir, settings.upload_max_bytes)
    queue = RedisJobQueue(settings.redis_url, settings.job_queue_name)
    worker = Phase2AWorker(
        database,
        storage,
        lease_seconds=settings.worker_lease_seconds,
    )
    try:
        for recovered_job_id in queue.recover_inflight():
            with database.session() as session:
                worker.repository.reset_recovered_job(session, recovered_job_id)
        while True:
            job_id = queue.dequeue(settings.worker_poll_seconds)
            if job_id:
                worker.process_job(job_id)
                queue.acknowledge(job_id)
    except KeyboardInterrupt:
        return 0
    finally:
        queue.close()
        database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
