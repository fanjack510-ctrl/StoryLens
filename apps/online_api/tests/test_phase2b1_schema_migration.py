from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from storylens_online.config import OnlineSettings
from storylens_online.db import init_schema


def test_phase2a_usage_snapshot_upgrades_additively_and_idempotently(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'phase2a-snapshot.db'}"
    legacy_engine = create_engine(database_url)
    with legacy_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE online_model_usage_ledger (
                    id VARCHAR(36) PRIMARY KEY,
                    invocation_id VARCHAR(128) NOT NULL UNIQUE,
                    analysis_run_id VARCHAR(64) NOT NULL,
                    user_id VARCHAR(64) NOT NULL,
                    provider VARCHAR(64) NOT NULL,
                    model VARCHAR(128) NOT NULL,
                    pricing_version VARCHAR(64) NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    provider_cost_cny NUMERIC(18, 6) NOT NULL,
                    customer_charge_cny NUMERIC(18, 6) NOT NULL,
                    disposition VARCHAR(32) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        for suffix in ("a", "b"):
            connection.execute(
                text(
                    """
                    INSERT INTO online_model_usage_ledger (
                        id, invocation_id, analysis_run_id, user_id, provider, model,
                        pricing_version, input_tokens, output_tokens, provider_cost_cny,
                        customer_charge_cny, disposition
                    ) VALUES (
                        :id, :invocation, 'legacy-run', 'legacy-user', 'legacy-provider',
                        'legacy-model', 'legacy-pricing', 10, 2, 0.1, 0.2, 'billable'
                    )
                    """
                ),
                {"id": f"legacy-{suffix}", "invocation": f"legacy-invocation-{suffix}"},
            )
        connection.execute(
            text(
                """
                INSERT INTO online_model_usage_ledger (
                    id, invocation_id, analysis_run_id, user_id, provider, model,
                    pricing_version, input_tokens, output_tokens, provider_cost_cny,
                    customer_charge_cny, disposition
                ) VALUES (
                    'legacy-c', 'legacy-invocation-c', 'legacy-run', 'legacy-user',
                    'legacy-provider', 'legacy-model', 'legacy-pricing', 10, 2, 0, 0,
                    'not_billable'
                )
                """
            )
        )
    legacy_engine.dispose()

    monkeypatch.setattr(init_schema, "create_engine", lambda _url: create_engine(database_url))
    settings = OnlineSettings(
        database_url="postgresql+psycopg://storylens@postgres:5432/storylens_online",
        frontend_origin="https://storylens.example.com",
    )
    init_schema.initialize_schema(settings)
    init_schema.initialize_schema(settings)

    verification_engine = create_engine(database_url)
    try:
        inspector = inspect(verification_engine)
        column_names = {
            column["name"] for column in inspector.get_columns("online_model_usage_ledger")
        }
        assert {
            "attempt_no",
            "status",
            "provider_request_id",
            "provider_response_model",
            "system_fingerprint",
            "request_sent_at",
            "total_tokens",
            "cached_tokens",
            "prompt_cache_miss_tokens",
            "usage_reported",
            "http_request_sent",
            "error_code",
            "pricing_currency",
            "pricing_tier",
            "cache_hit_usd_per_million",
            "cache_miss_usd_per_million",
            "output_usd_per_million",
            "provider_cost_usd",
            "fx_rate_to_cny",
            "fx_rate_version",
            "input_per_million_cny",
            "cached_input_per_million_cny",
            "output_per_million_cny",
            "completed_at",
        }.issubset(column_names)
        with verification_engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT attempt_no, status, total_tokens, cached_tokens, "
                        "prompt_cache_miss_tokens, pricing_currency, pricing_tier, "
                        "provider_cost_usd, fx_rate_to_cny, usage_reported, "
                        "http_request_sent, customer_charge_cny "
                        "FROM online_model_usage_ledger ORDER BY attempt_no"
                    )
                )
                .mappings()
                .all()
            )
        assert [row["attempt_no"] for row in rows] == [1, 2, 3]
        assert all(row["status"] == "succeeded" for row in rows)
        assert all(row["total_tokens"] == 12 for row in rows)
        assert all(row["cached_tokens"] == 0 for row in rows)
        assert all(row["prompt_cache_miss_tokens"] == 10 for row in rows)
        assert all(row["pricing_currency"] == "CNY" for row in rows)
        assert all(row["pricing_tier"] == "legacy" for row in rows)
        assert all(Decimal(str(row["provider_cost_usd"])) == 0 for row in rows)
        assert all(Decimal(str(row["fx_rate_to_cny"])) == 0 for row in rows)
        assert all(bool(row["usage_reported"]) for row in rows)
        assert all(bool(row["http_request_sent"]) for row in rows)
        assert [Decimal(str(row["customer_charge_cny"])) for row in rows] == [
            Decimal("0.2"),
            Decimal("0.2"),
            Decimal(0),
        ]
        unique_indexes = {
            tuple(index["column_names"])
            for index in inspector.get_indexes("online_model_usage_ledger")
            if index["unique"]
        }
        assert ("analysis_run_id", "attempt_no") in unique_indexes
    finally:
        verification_engine.dispose()


def test_partial_deepseek_columns_are_completed_without_rebuilding_table(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'partial-snapshot.db'}"
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE online_model_usage_ledger (
                    id VARCHAR(36) PRIMARY KEY,
                    invocation_id VARCHAR(128) NOT NULL UNIQUE,
                    analysis_run_id VARCHAR(64) NOT NULL,
                    user_id VARCHAR(64) NOT NULL,
                    provider VARCHAR(64) NOT NULL,
                    model VARCHAR(128) NOT NULL,
                    pricing_version VARCHAR(64) NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    provider_cost_cny NUMERIC(18, 6) NOT NULL,
                    customer_charge_cny NUMERIC(18, 6) NOT NULL,
                    disposition VARCHAR(32) NOT NULL,
                    pricing_currency VARCHAR(3),
                    prompt_cache_miss_tokens INTEGER,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO online_model_usage_ledger (
                    id, invocation_id, analysis_run_id, user_id, provider, model,
                    pricing_version, input_tokens, output_tokens, provider_cost_cny,
                    customer_charge_cny, disposition
                ) VALUES (
                    'partial-1', 'partial-invocation', 'partial-run', 'legacy-user',
                    'legacy-provider', 'legacy-model', 'legacy-pricing', 8, 3, 0, 0,
                    'not_billable'
                )
                """
            )
        )
    engine.dispose()

    monkeypatch.setattr(init_schema, "create_engine", lambda _url: create_engine(database_url))
    settings = OnlineSettings(
        database_url="postgresql+psycopg://storylens@postgres:5432/storylens_online",
        frontend_origin="https://storylens.example.com",
    )
    init_schema.initialize_schema(settings)
    init_schema.initialize_schema(settings)

    verification_engine = create_engine(database_url)
    try:
        columns = {
            column["name"]
            for column in inspect(verification_engine).get_columns("online_model_usage_ledger")
        }
        assert "provider_cost_usd" in columns
        assert "fx_rate_version" in columns
        with verification_engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT prompt_cache_miss_tokens, pricing_currency, pricing_tier "
                        "FROM online_model_usage_ledger WHERE id = 'partial-1'"
                    )
                )
                .mappings()
                .one()
            )
        assert row == {
            "prompt_cache_miss_tokens": 8,
            "pricing_currency": "CNY",
            "pricing_tier": "legacy",
        }
    finally:
        verification_engine.dispose()
