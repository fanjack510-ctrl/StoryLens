from __future__ import annotations

import threading
import time
from contextlib import AbstractContextManager
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect
from storylens_online.config import OnlineSettings
from storylens_online.db import init_schema
from storylens_online.db.models import OnlineBase

EXPECTED_TABLES = {
    "online_analysis_jobs",
    "online_billing_reservations",
    "online_book_uploads",
    "online_model_usage_ledger",
    "online_recharge_orders",
    "online_wallet_accounts",
    "online_wallet_transactions",
}


def _settings() -> OnlineSettings:
    return OnlineSettings(
        database_url="postgresql+psycopg://storylens@postgres:5432/storylens_online",
        frontend_origin="https://storylens.example.com",
    )


def test_initialize_schema_creates_all_online_tables_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'online-schema.db'}"
    disposed_engines = []
    executed_sql: list[str] = []

    def make_test_engine(_database_url: str):
        engine = create_engine(database_url)
        event.listen(
            engine,
            "before_cursor_execute",
            lambda _connection, _cursor, statement, _parameters, _context, _many: (
                executed_sql.append(statement)
            ),
        )
        original_dispose = engine.dispose

        def tracked_dispose() -> None:
            disposed_engines.append(engine)
            original_dispose()

        monkeypatch.setattr(engine, "dispose", tracked_dispose)
        return engine

    monkeypatch.setattr(init_schema, "create_engine", make_test_engine)

    init_schema.initialize_schema(_settings())
    init_schema.initialize_schema(_settings())

    verification_engine = create_engine(database_url)
    try:
        created_tables = set(inspect(verification_engine).get_table_names())
    finally:
        verification_engine.dispose()

    assert created_tables == EXPECTED_TABLES
    assert created_tables == set(OnlineBase.metadata.tables)
    assert {
        "online_billing_reservations",
        "online_model_usage_ledger",
        "online_recharge_orders",
        "online_wallet_accounts",
        "online_wallet_transactions",
    }.issubset(created_tables)
    assert len(disposed_engines) == 2
    assert not any("pg_advisory" in statement.lower() for statement in executed_sql)


def test_initialize_schema_disposes_engine_and_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingEngine:
        disposed = False

        class Connection:
            class Dialect:
                name = "sqlite"

            dialect = Dialect()

        class Transaction(AbstractContextManager):
            def __enter__(self):
                return FailingEngine.Connection()

            def __exit__(self, exc_type, exc_value, traceback) -> None:
                return None

        def begin(self):
            return self.Transaction()

        def dispose(self) -> None:
            self.disposed = True

    engine = FailingEngine()
    monkeypatch.setattr(init_schema, "create_engine", lambda _database_url: engine)

    def fail_create_all(_engine) -> None:
        raise RuntimeError("schema initialization failed")

    monkeypatch.setattr(OnlineBase.metadata, "create_all", fail_create_all)

    with pytest.raises(RuntimeError, match="schema initialization failed"):
        init_schema.initialize_schema(_settings())

    assert engine.disposed is True


def test_postgresql_advisory_lock_precedes_all_schema_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    lock_parameters: list[dict[str, int]] = []

    class FakeConnection:
        class Dialect:
            name = "postgresql"

        dialect = Dialect()

        def execute(self, statement, parameters=None):
            events.append(str(statement))
            lock_parameters.append(dict(parameters))

    class FakeTransaction(AbstractContextManager):
        connection = FakeConnection()

        def __enter__(self):
            return self.connection

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            return None

    class FakeEngine:
        disposed = False

        def begin(self):
            return FakeTransaction()

        def dispose(self) -> None:
            self.disposed = True

    engine = FakeEngine()
    monkeypatch.setattr(init_schema, "create_engine", lambda _url: engine)
    monkeypatch.setattr(
        OnlineBase.metadata,
        "create_all",
        lambda connection: events.append(f"create_all:{id(connection)}"),
    )
    monkeypatch.setattr(
        init_schema,
        "migrate_phase2b1_usage_ledger",
        lambda connection: events.append(f"migrate:{id(connection)}"),
    )

    init_schema.initialize_schema(_settings())

    assert "pg_advisory_xact_lock" in events[0]
    assert events[1].startswith("create_all:")
    assert events[2].startswith("migrate:")
    assert events[1].split(":", 1)[1] == events[2].split(":", 1)[1]
    assert lock_parameters == [
        {
            "storylens_schema_namespace": init_schema.POSTGRES_SCHEMA_LOCK_NAMESPACE,
            "storylens_schema_resource": init_schema.POSTGRES_SCHEMA_LOCK_RESOURCE,
        }
    ]
    assert engine.disposed is True


def test_two_postgresql_initializers_serialize_and_recheck_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    advisory_lock = threading.Lock()
    both_started = threading.Barrier(2)
    state = {"column_exists": False, "actual_adds": 0}
    failures: list[Exception] = []
    observed: list[str] = []

    class FakeConnection:
        class Dialect:
            name = "postgresql"

        dialect = Dialect()
        holds_lock = False

        def execute(self, statement, _parameters=None):
            assert "pg_advisory_xact_lock" in str(statement)
            advisory_lock.acquire()
            self.holds_lock = True
            observed.append("lock")

    class FakeTransaction(AbstractContextManager):
        def __init__(self) -> None:
            self.connection = FakeConnection()

        def __enter__(self):
            both_started.wait(timeout=5)
            return self.connection

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            if self.connection.holds_lock:
                self.connection.holds_lock = False
                advisory_lock.release()

    class FakeEngine:
        def begin(self):
            return FakeTransaction()

        def dispose(self) -> None:
            return None

    monkeypatch.setattr(init_schema, "create_engine", lambda _url: FakeEngine())

    def create_all(connection) -> None:
        assert connection.holds_lock
        observed.append("create_all")

    def migrate(connection) -> None:
        assert connection.holds_lock
        observed.append("check")
        if not state["column_exists"]:
            time.sleep(0.05)
            state["column_exists"] = True
            state["actual_adds"] += 1
            observed.append("add")

    monkeypatch.setattr(OnlineBase.metadata, "create_all", create_all)
    monkeypatch.setattr(init_schema, "migrate_phase2b1_usage_ledger", migrate)

    def initialize() -> None:
        try:
            init_schema.initialize_schema(_settings())
        except (AssertionError, RuntimeError, threading.BrokenBarrierError) as exc:
            failures.append(exc)

    threads = [threading.Thread(target=initialize) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not failures
    assert not any(thread.is_alive() for thread in threads)
    assert state == {"column_exists": True, "actual_adds": 1}
    assert observed.count("lock") == 2
    assert observed.count("check") == 2
    assert observed.count("add") == 1
