from __future__ import annotations

from collections import defaultdict
from typing import Final

from sqlalchemy import Connection, Engine, inspect, text

MIGRATION_VERSION: Final[str] = "phase2b1-deepseek-usage-ledger-v2"
TABLE_NAME: Final[str] = "online_model_usage_ledger"
UNIQUE_INDEX_NAME: Final[str] = "uq_online_usage_run_attempt"


def migrate_phase2b1_usage_ledger(engine: Engine) -> None:
    """Apply the additive Phase 2B1 usage-ledger migration.

    The migration deliberately owns no migration table: the schema itself is the
    idempotency boundary, so an interrupted startup can safely run it again.
    Existing rows are retained and assigned deterministic attempt numbers per run.
    """

    if TABLE_NAME not in inspect(engine).get_table_names():
        return
    with engine.begin() as connection:
        _add_missing_columns(connection)
        _backfill_legacy_rows(connection)
        _create_unique_boundary(connection)
        if connection.dialect.name == "postgresql":
            _harden_postgresql_columns(connection)
            _add_postgresql_checks(connection)


def _add_missing_columns(connection: Connection) -> None:
    existing = {column["name"] for column in inspect(connection).get_columns(TABLE_NAME)}
    is_postgresql = connection.dialect.name == "postgresql"
    bool_false = "FALSE" if is_postgresql else "0"
    timestamp_type = "TIMESTAMP WITH TIME ZONE" if is_postgresql else "DATETIME"
    request_sent_definition = (
        f"{timestamp_type} NOT NULL DEFAULT CURRENT_TIMESTAMP" if is_postgresql else timestamp_type
    )
    definitions = {
        "attempt_no": "INTEGER NOT NULL DEFAULT 1",
        "status": "VARCHAR(32) NOT NULL DEFAULT 'succeeded'",
        "provider_request_id": "VARCHAR(255)",
        "provider_response_model": "VARCHAR(128)",
        "system_fingerprint": "VARCHAR(255)",
        "request_sent_at": request_sent_definition,
        "total_tokens": "INTEGER NOT NULL DEFAULT 0",
        "cached_tokens": "INTEGER NOT NULL DEFAULT 0",
        "prompt_cache_miss_tokens": "INTEGER NOT NULL DEFAULT 0",
        "usage_reported": f"BOOLEAN NOT NULL DEFAULT {bool_false}",
        "http_request_sent": f"BOOLEAN NOT NULL DEFAULT {bool_false}",
        "error_code": "VARCHAR(64)",
        "pricing_currency": "VARCHAR(3) NOT NULL DEFAULT 'CNY'",
        "pricing_tier": "VARCHAR(16) NOT NULL DEFAULT 'legacy'",
        "cache_hit_usd_per_million": "NUMERIC(18, 9) NOT NULL DEFAULT 0",
        "cache_miss_usd_per_million": "NUMERIC(18, 9) NOT NULL DEFAULT 0",
        "output_usd_per_million": "NUMERIC(18, 9) NOT NULL DEFAULT 0",
        "provider_cost_usd": "NUMERIC(18, 9) NOT NULL DEFAULT 0",
        "fx_rate_to_cny": "NUMERIC(18, 6) NOT NULL DEFAULT 0",
        "fx_rate_version": "VARCHAR(64) NOT NULL DEFAULT 'legacy-no-fx'",
        "input_per_million_cny": "NUMERIC(18, 6) NOT NULL DEFAULT 0",
        "cached_input_per_million_cny": "NUMERIC(18, 6) NOT NULL DEFAULT 0",
        "output_per_million_cny": "NUMERIC(18, 6) NOT NULL DEFAULT 0",
        "completed_at": timestamp_type,
    }
    for column_name, definition in definitions.items():
        if column_name not in existing:
            connection.execute(
                text(f'ALTER TABLE {TABLE_NAME} ADD COLUMN "{column_name}" {definition}')
            )


def _backfill_legacy_rows(connection: Connection) -> None:
    rows = connection.execute(
        text(
            f"SELECT id, analysis_run_id FROM {TABLE_NAME} "
            "WHERE pricing_tier IS NULL OR pricing_tier = 'legacy' "
            "ORDER BY analysis_run_id, created_at, id"
        )
    ).mappings()
    next_attempt: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        run_id = str(row["analysis_run_id"])
        next_attempt[run_id] += 1
        connection.execute(
            text(f"UPDATE {TABLE_NAME} SET attempt_no = :attempt_no WHERE id = :row_id"),
            {"attempt_no": next_attempt[run_id], "row_id": row["id"]},
        )
    connection.execute(
        text(
            f"UPDATE {TABLE_NAME} SET "
            "status = COALESCE(status, 'succeeded'), "
            "provider_response_model = COALESCE(provider_response_model, model), "
            "request_sent_at = COALESCE(request_sent_at, created_at), "
            "total_tokens = COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0), "
            "cached_tokens = COALESCE(cached_tokens, 0), "
            "prompt_cache_miss_tokens = CASE "
            "WHEN COALESCE(input_tokens, 0) >= COALESCE(cached_tokens, 0) "
            "THEN COALESCE(input_tokens, 0) - COALESCE(cached_tokens, 0) ELSE 0 END, "
            "usage_reported = CASE WHEN usage_reported IS NULL OR usage_reported = FALSE "
            "THEN TRUE ELSE usage_reported END, "
            "http_request_sent = CASE WHEN http_request_sent IS NULL OR http_request_sent = FALSE "
            "THEN TRUE ELSE http_request_sent END, "
            "input_per_million_cny = COALESCE(input_per_million_cny, 0), "
            "cached_input_per_million_cny = COALESCE(cached_input_per_million_cny, 0), "
            "output_per_million_cny = COALESCE(output_per_million_cny, 0), "
            "pricing_currency = 'CNY', "
            "pricing_tier = 'legacy', "
            "cache_hit_usd_per_million = COALESCE(cache_hit_usd_per_million, 0), "
            "cache_miss_usd_per_million = COALESCE(cache_miss_usd_per_million, 0), "
            "output_usd_per_million = COALESCE(output_usd_per_million, 0), "
            "provider_cost_usd = COALESCE(provider_cost_usd, 0), "
            "fx_rate_to_cny = COALESCE(fx_rate_to_cny, 0), "
            "fx_rate_version = COALESCE(fx_rate_version, 'legacy-no-fx'), "
            "completed_at = COALESCE(completed_at, updated_at) "
            "WHERE pricing_tier IS NULL OR pricing_tier = 'legacy'"
        )
    )


def _create_unique_boundary(connection: Connection) -> None:
    connection.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX_NAME} "
            f"ON {TABLE_NAME} (analysis_run_id, attempt_no)"
        )
    )


def _harden_postgresql_columns(connection: Connection) -> None:
    connection.execute(
        text(f"ALTER TABLE {TABLE_NAME} ALTER COLUMN provider_request_id TYPE VARCHAR(255)")
    )
    for column_name in (
        "attempt_no",
        "status",
        "total_tokens",
        "cached_tokens",
        "prompt_cache_miss_tokens",
        "usage_reported",
        "http_request_sent",
        "request_sent_at",
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
    ):
        connection.execute(
            text(f'ALTER TABLE {TABLE_NAME} ALTER COLUMN "{column_name}" SET NOT NULL')
        )


def _add_postgresql_checks(connection: Connection) -> None:
    checks = {
        "ck_online_usage_attempt_positive": "attempt_no > 0",
        "ck_online_usage_status": (
            "status IN ('started', 'succeeded', 'failed', 'invalid_response', "
            "'unknown', 'accounting_incomplete')"
        ),
        "ck_online_usage_total_tokens_nonnegative": "total_tokens >= 0",
        "ck_online_usage_cached_tokens_nonnegative": "cached_tokens >= 0",
        "ck_online_usage_cache_miss_nonnegative": "prompt_cache_miss_tokens >= 0",
        "ck_online_usage_cached_not_above_input": "cached_tokens <= input_tokens",
        "ck_online_usage_cache_split_matches_input": (
            "cached_tokens + prompt_cache_miss_tokens = input_tokens"
        ),
        "ck_online_usage_input_price_nonnegative": "input_per_million_cny >= 0",
        "ck_online_usage_cached_price_nonnegative": "cached_input_per_million_cny >= 0",
        "ck_online_usage_output_price_nonnegative": "output_per_million_cny >= 0",
        "ck_online_usage_usd_hit_price_nonnegative": "cache_hit_usd_per_million >= 0",
        "ck_online_usage_usd_miss_price_nonnegative": "cache_miss_usd_per_million >= 0",
        "ck_online_usage_usd_output_price_nonnegative": "output_usd_per_million >= 0",
        "ck_online_usage_usd_cost_nonnegative": "provider_cost_usd >= 0",
        "ck_online_usage_fx_rate_nonnegative": "fx_rate_to_cny >= 0",
        "ck_online_usage_pricing_currency": "pricing_currency IN ('USD', 'CNY')",
        "ck_online_usage_pricing_tier": "pricing_tier IN ('peak', 'off_peak', 'legacy')",
        "ck_online_usage_usd_fx_positive": "pricing_currency <> 'USD' OR fx_rate_to_cny > 0",
        "ck_online_usage_charge_nonnegative": "customer_charge_cny >= 0",
        "ck_online_usage_not_billable_charge_zero": (
            "disposition <> 'not_billable' OR customer_charge_cny = 0"
        ),
    }
    for constraint_name, expression in checks.items():
        connection.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS ("
                f"SELECT 1 FROM pg_constraint WHERE conname = '{constraint_name}' "
                f"AND conrelid = to_regclass('{TABLE_NAME}')"
                ") THEN "
                f"ALTER TABLE {TABLE_NAME} ADD CONSTRAINT {constraint_name} CHECK ({expression}); "
                "END IF; END $$"
            ),
        )
