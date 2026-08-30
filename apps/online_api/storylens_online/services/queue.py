from __future__ import annotations

from typing import Protocol

from redis import Redis


class JobQueue(Protocol):
    def enqueue(self, job_id: str) -> None: ...


class RedisJobQueue:
    def __init__(self, redis_url: str, queue_name: str, *, client: Redis | None = None) -> None:
        self.queue_name = queue_name
        self.processing_name = f"{queue_name}:processing"
        self._redis = client or Redis.from_url(redis_url, decode_responses=True)

    def enqueue(self, job_id: str) -> None:
        self._redis.lpush(self.queue_name, job_id)

    def dequeue(self, timeout_seconds: int) -> str | None:
        return self._redis.brpoplpush(
            self.queue_name,
            self.processing_name,
            timeout=timeout_seconds,
        )

    def acknowledge(self, job_id: str) -> None:
        self._redis.lrem(self.processing_name, 1, job_id)

    def recover_inflight(self) -> list[str]:
        recovered: list[str] = []
        while True:
            job_id = self._redis.rpoplpush(self.processing_name, self.queue_name)
            if job_id is None:
                return recovered
            recovered.append(job_id)

    def close(self) -> None:
        self._redis.close()
