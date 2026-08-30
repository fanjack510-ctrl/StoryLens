from __future__ import annotations

import logging
from collections import deque
from threading import Event

import pytest
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from storylens_online.config import OnlineSettings
from storylens_online.worker import WorkerRunner


class ScriptedQueue:
    def __init__(
        self,
        *,
        dequeues: list[str | None | BaseException],
        recoveries: list[list[str] | BaseException] | None = None,
        stop_event: Event | None = None,
        stop_after_dequeues: int | None = None,
    ) -> None:
        self.dequeues = deque(dequeues)
        self.recoveries = deque(recoveries or [[]])
        self.stop_event = stop_event
        self.stop_after_dequeues = stop_after_dequeues
        self.dequeue_calls = 0
        self.recover_calls = 0
        self.acknowledged: list[str] = []
        self.reset_calls = 0

    def enqueue(self, job_id: str) -> None:
        raise AssertionError(f"worker must not enqueue {job_id}")

    def dequeue(self, timeout_seconds: int) -> str | None:
        assert timeout_seconds == 5
        self.dequeue_calls += 1
        if self.stop_after_dequeues == self.dequeue_calls and self.stop_event is not None:
            self.stop_event.set()
        value = self.dequeues.popleft() if self.dequeues else None
        if isinstance(value, BaseException):
            raise value
        return value

    def acknowledge(self, job_id: str) -> None:
        self.acknowledged.append(job_id)

    def recover_inflight(self) -> list[str]:
        self.recover_calls += 1
        value = self.recoveries.popleft() if self.recoveries else []
        if isinstance(value, BaseException):
            raise value
        return value

    def reset_connections(self) -> None:
        self.reset_calls += 1


class RecordingProcessor:
    def __init__(self, failure: BaseException | None = None) -> None:
        self.job_ids: list[str] = []
        self.failure = failure

    def process_job(self, job_id: str) -> bool:
        self.job_ids.append(job_id)
        if self.failure is not None:
            raise self.failure
        return True


def make_runner(
    queue: ScriptedQueue,
    processor: RecordingProcessor,
    recovered: list[str],
    *,
    stop_event: Event | None = None,
    waits: list[float] | None = None,
) -> WorkerRunner:
    recorded_waits = waits if waits is not None else []

    def wait_for_retry(delay: float) -> bool:
        recorded_waits.append(delay)
        return False

    return WorkerRunner(
        queue,
        processor,
        recovered.append,
        poll_seconds=5,
        retry_initial_seconds=1,
        retry_max_seconds=4,
        stop_event=stop_event,
        wait_for_retry=wait_for_retry,
    )


def test_empty_queue_survives_three_poll_cycles_without_touching_jobs() -> None:
    stop_event = Event()
    queue = ScriptedQueue(
        dequeues=[None, None, None],
        stop_event=stop_event,
        stop_after_dequeues=3,
    )
    processor = RecordingProcessor()
    recovered: list[str] = []

    make_runner(queue, processor, recovered, stop_event=stop_event).run()

    assert queue.dequeue_calls == 3
    assert processor.job_ids == []
    assert recovered == []
    assert queue.acknowledged == []
    assert queue.reset_calls == 0


def test_socket_timeouts_are_transient_bounded_and_not_log_flooded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queue = ScriptedQueue(
        dequeues=[
            RedisTimeoutError("socket timeout"),
            RedisTimeoutError("socket timeout"),
            RedisTimeoutError("socket timeout"),
            None,
        ],
    )
    processor = RecordingProcessor()
    recovered: list[str] = []
    waits: list[float] = []

    with caplog.at_level(logging.INFO, logger="storylens_online.worker"):
        make_runner(queue, processor, recovered, waits=waits).run(max_idle_polls=1)

    assert waits == [1, 2, 4]
    assert queue.reset_calls == 3
    assert processor.job_ids == []
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].exc_info is None
    assert "socket timeout" not in warnings[0].getMessage()
    assert sum("connection recovered" in record.getMessage() for record in caplog.records) == 1


def test_ambiguous_dequeue_is_recovered_then_consumed_after_connection_returns() -> None:
    queue = ScriptedQueue(
        dequeues=[RedisConnectionError("connection dropped"), "job-1", None],
        recoveries=[[], ["job-1"]],
    )
    processor = RecordingProcessor()
    recovered: list[str] = []
    waits: list[float] = []

    make_runner(queue, processor, recovered, waits=waits).run(max_idle_polls=1)

    assert waits == [1]
    assert recovered == ["job-1"]
    assert processor.job_ids == ["job-1"]
    assert queue.acknowledged == ["job-1"]
    assert queue.recover_calls == 2


def test_task_execution_error_is_not_swallowed_or_acknowledged() -> None:
    queue = ScriptedQueue(dequeues=["job-1"])
    processor = RecordingProcessor(RedisTimeoutError("task failure, not queue failure"))

    with pytest.raises(RedisTimeoutError, match="task failure"):
        make_runner(queue, processor, []).run(max_idle_polls=1)

    assert processor.job_ids == ["job-1"]
    assert queue.acknowledged == []
    assert queue.reset_calls == 0


def test_stop_signal_interrupts_retry_backoff_without_busy_loop() -> None:
    stop_event = Event()
    queue = ScriptedQueue(dequeues=[RedisConnectionError("temporarily unavailable")])
    processor = RecordingProcessor()
    waits: list[float] = []

    def stop_during_wait(delay: float) -> bool:
        waits.append(delay)
        return True

    runner = WorkerRunner(
        queue,
        processor,
        lambda _job_id: None,
        poll_seconds=5,
        retry_initial_seconds=1,
        retry_max_seconds=4,
        stop_event=stop_event,
        wait_for_retry=stop_during_wait,
    )
    runner.run()

    assert waits == [1]
    assert stop_event.is_set()
    assert queue.dequeue_calls == 1


def test_settings_require_socket_margin_and_ordered_retry_delays() -> None:
    redacted_password = "DUMMY_PASSWORD_MUST_NOT_APPEAR"
    with pytest.raises(ValidationError, match="socket timeout") as invalid_socket:
        OnlineSettings(
            redis_url=f"redis://:{redacted_password}@private-host:6379/0",
            worker_poll_seconds=5,
            redis_socket_timeout_seconds=6.9,
        )
    assert redacted_password not in str(invalid_socket.value)

    with pytest.raises(ValidationError, match="maximum retry delay"):
        OnlineSettings(
            worker_redis_retry_initial_seconds=5,
            worker_redis_retry_max_seconds=4,
        )

    settings = OnlineSettings(
        worker_poll_seconds=5,
        redis_socket_timeout_seconds=7,
        worker_redis_retry_initial_seconds=1,
        worker_redis_retry_max_seconds=4,
    )
    assert settings.redis_socket_timeout_seconds >= settings.worker_poll_seconds + 2
