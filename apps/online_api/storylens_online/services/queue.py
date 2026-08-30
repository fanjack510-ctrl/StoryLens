from __future__ import annotations

from typing import Protocol

from redis import Redis


class JobQueue(Protocol):
    def enqueue(self, job_id: str) -> None: ...


class WorkerJobQueue(JobQueue, Protocol):
    def dequeue(self, timeout_seconds: int) -> str | None: ...

    def acknowledge(self, job_id: str) -> None: ...

    def recover_inflight(self) -> list[str]: ...

    def reset_connections(self) -> None: ...


class RedisJobQueue:
    def __init__(
        self,
        redis_url: str,
        queue_name: str,
        *,
        socket_timeout_seconds: float | None = None,
        connect_timeout_seconds: float | None = None,
        client: Redis | None = None,
    ) -> None:
        self.queue_name = queue_name
        self.processing_name = f"{queue_name}:processing"
        if client is not None:
            self._redis = client
            return
        connection_options: dict[str, object] = {
            "decode_responses": True,
            "retry_on_timeout": False,
        }
        if socket_timeout_seconds is not None:
            connection_options["socket_timeout"] = socket_timeout_seconds
        if connect_timeout_seconds is not None:
            connection_options["socket_connect_timeout"] = connect_timeout_seconds
        self._redis = Redis.from_url(redis_url, **connection_options)

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

    def reset_connections(self) -> None:
        self._redis.connection_pool.disconnect()

    def close(self) -> None:
        self._redis.close()
