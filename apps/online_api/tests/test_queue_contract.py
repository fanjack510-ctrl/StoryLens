from __future__ import annotations

from typing import cast

import pytest
from redis import Redis
from storylens_online.services import queue as queue_module
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


def test_worker_queue_uses_explicit_socket_and_connect_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    fake_client = FakeRedis()

    def from_url(redis_url: str, **options: object):
        captured["redis_url"] = redis_url
        captured.update(options)
        return cast(Redis, fake_client)

    monkeypatch.setattr(queue_module.Redis, "from_url", from_url)

    RedisJobQueue(
        "redis://private-host:6379/0",
        "storylens:phase2a:jobs",
        socket_timeout_seconds=15,
        connect_timeout_seconds=5,
    )

    assert captured == {
        "redis_url": "redis://private-host:6379/0",
        "decode_responses": True,
        "retry_on_timeout": False,
        "socket_timeout": 15,
        "socket_connect_timeout": 5,
    }
