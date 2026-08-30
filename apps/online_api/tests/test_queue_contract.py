from __future__ import annotations

from typing import cast

from redis import Redis
from storylens_online.services.queue import RedisJobQueue


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}

    def lpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).insert(0, value)

    def brpoplpush(self, source: str, destination: str, timeout: int) -> str | None:
        del timeout
        source_items = self.lists.setdefault(source, [])
        if not source_items:
            return None
        value = source_items.pop()
        self.lists.setdefault(destination, []).insert(0, value)
        return value

    def rpoplpush(self, source: str, destination: str) -> str | None:
        return self.brpoplpush(source, destination, timeout=0)

    def lrem(self, key: str, count: int, value: str) -> None:
        del count
        items = self.lists.setdefault(key, [])
        if value in items:
            items.remove(value)

    def close(self) -> None:
        pass


def test_redis_queue_uses_inflight_list_for_recovery_and_acknowledgement() -> None:
    redis = FakeRedis()
    queue = RedisJobQueue(
        "redis://not-used",
        "storylens:phase2a:jobs",
        client=cast(Redis, redis),
    )
    queue.enqueue("job-1")
    queue.enqueue("job-2")

    assert queue.dequeue(1) == "job-1"
    assert redis.lists[queue.processing_name] == ["job-1"]
    assert queue.recover_inflight() == ["job-1"]
    assert queue.dequeue(1) == "job-2"
    queue.acknowledge("job-2")
    assert redis.lists[queue.processing_name] == []
    assert queue.dequeue(1) == "job-1"
