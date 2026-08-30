from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from storylens_online.config import OnlineSettings
from storylens_online.db import init_schema
from storylens_online.db.models import OnlineBase


EXPECTED_TABLES = {
    "online_billing_reservations",
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


def test_initialize_schema_creates_five_tables_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'online-schema.db'}"
    disposed_engines = []

    def make_test_engine(_database_url: str):
        engine = create_engine(database_url)
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
    assert len(disposed_engines) == 2


def test_initialize_schema_disposes_engine_and_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingEngine:
        disposed = False

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
