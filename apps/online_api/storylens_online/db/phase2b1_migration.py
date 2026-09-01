from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Boolean, Connection, DateTime, Integer, Numeric, String, inspect, text

MIGRATION_VERSION: Final[str] = "phase2b1-deepseek-usage-ledger-v2"
TABLE_NAME: Final[str] = "online_model_usage_ledger"
UNIQUE_INDEX_NAME: Final[str] = "uq_online_usage_run_attempt"
SCHEMA_DEFINITION_ERROR: Final[str] = "Online database schema is incompatible."
POSTGRES_CONTRACT_TABLE: Final[str] = "storylens_phase2b1_contract_check"


class SchemaDefinitionError(RuntimeError):
    """Fixed, credential-free failure for an incompatible persisted schema."""

    def __init__(self) -> None:
        super().__init__(SCHEMA_DEFINITION_ERROR)


@dataclass(frozen=True)
class ColumnContract:
    family: str
    nullable: bool
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    transitional_defaults: frozenset[str | None] = frozenset({None})


def _defaults(*values: str | None) -> frozenset[str | None]:
    return frozenset(values)


PHASE2B1_COLUMN_CONTRACTS: Final[dict[str, ColumnContract]] = {
    "attempt_no": ColumnContract("integer", False, transitional_defaults=_defaults(None, "1")),
    "status": ColumnContract(
        "string", False, length=32, transitional_defaults=_defaults(None, "'succeeded'")
    ),
    "provider_request_id": ColumnContract("string", True, length=255),
    "provider_response_model": ColumnContract("string", True, length=128),
    "system_fingerprint": ColumnContract("string", True, length=255),
    "request_sent_at": ColumnContract(
        "datetime", False, transitional_defaults=_defaults("current_timestamp")
    ),
    "total_tokens": ColumnContract("integer", False, transitional_defaults=_defaults(None, "0")),
    "cached_tokens": ColumnContract("integer", False, transitional_defaults=_defaults(None, "0")),
    "prompt_cache_miss_tokens": ColumnContract(
        "integer", False, transitional_defaults=_defaults(None, "0")
    ),
    "usage_reported": ColumnContract(
        "boolean", False, transitional_defaults=_defaults(None, "false", "0")
    ),
    "http_request_sent": ColumnContract(
        "boolean", False, transitional_defaults=_defaults(None, "false", "0")
    ),
    "error_code": ColumnContract("string", True, length=64),
    "pricing_currency": ColumnContract(
        "string", False, length=3, transitional_defaults=_defaults(None, "'cny'")
    ),
    "pricing_tier": ColumnContract(
        "string", False, length=16, transitional_defaults=_defaults(None, "'legacy'")
    ),
    "cache_hit_usd_per_million": ColumnContract(
        "numeric", False, precision=18, scale=9, transitional_defaults=_defaults(None, "0")
    ),
    "cache_miss_usd_per_million": ColumnContract(
        "numeric", False, precision=18, scale=9, transitional_defaults=_defaults(None, "0")
    ),
    "output_usd_per_million": ColumnContract(
        "numeric", False, precision=18, scale=9, transitional_defaults=_defaults(None, "0")
    ),
    "provider_cost_usd": ColumnContract(
        "numeric", False, precision=18, scale=9, transitional_defaults=_defaults(None, "0")
    ),
    "fx_rate_to_cny": ColumnContract(
        "numeric", False, precision=18, scale=6, transitional_defaults=_defaults(None, "0")
    ),
    "fx_rate_version": ColumnContract(
        "string",
        False,
        length=64,
        transitional_defaults=_defaults(None, "'legacy-no-fx'"),
    ),
    "input_per_million_cny": ColumnContract(
        "numeric", False, precision=18, scale=6, transitional_defaults=_defaults(None, "0")
    ),
    "cached_input_per_million_cny": ColumnContract(
        "numeric", False, precision=18, scale=6, transitional_defaults=_defaults(None, "0")
    ),
    "output_per_million_cny": ColumnContract(
        "numeric", False, precision=18, scale=6, transitional_defaults=_defaults(None, "0")
    ),
    "completed_at": ColumnContract("datetime", True),
}

POSTGRES_TEMPORARY_DEFAULT_COLUMNS: Final[tuple[str, ...]] = tuple(
    column_name
    for column_name, contract in PHASE2B1_COLUMN_CONTRACTS.items()
    if column_name != "request_sent_at" and contract.transitional_defaults != frozenset({None})
)


def migrate_phase2b1_usage_ledger(connection: Connection) -> None:
    """Apply the additive Phase 2B1 usage-ledger migration.

    The migration deliberately owns no migration table: the schema itself is the
    idempotency boundary, so an interrupted startup can safely run it again.
    The caller owns one transaction and one connection across create_all and this
    function. Existing rows are retained and assigned deterministic attempt numbers.
    """

    if TABLE_NAME not in inspect(connection).get_table_names():
        return
    _validate_phase2b1_columns(connection, final=False)
    _add_missing_columns(connection)
    _validate_phase2b1_columns(connection, final=False)
    _backfill_legacy_rows(connection)
    _create_unique_boundary(connection)
    if connection.dialect.name == "postgresql":
        _canonicalize_postgresql_defaults(connection)
        _add_postgresql_checks(connection)
        _validate_postgresql_checks(connection)
    _validate_phase2b1_columns(connection, final=True)
    _validate_unique_boundary(connection)


def _normalized_default(value: object) -> str | None:
    if value is None:
        return None
    normalized = "".join(str(value).strip().lower().split())
    while normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1]
    normalized = re.sub(
        r"::(?:charactervarying|varchar|text|numeric|integer|boolean)",
        "",
        normalized,
    )
    while normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1]
    if normalized in {"now()", "current_timestamp", "current_timestamp()"}:
        return "current_timestamp"
    return normalized


def _column_family(column_type: object, dialect_name: str) -> tuple[object, ...]:
    if isinstance(column_type, Boolean):
        return ("boolean",)
    if isinstance(column_type, Integer):
        return ("integer",)
    if isinstance(column_type, String):
        return ("string", column_type.length)
    if isinstance(column_type, Numeric):
        return ("numeric", column_type.precision, column_type.scale)
    if isinstance(column_type, DateTime):
        timezone = bool(column_type.timezone) if dialect_name == "postgresql" else None
        return ("datetime", timezone)
    return ("unsupported", type(column_type).__name__)


def _expected_family(contract: ColumnContract, dialect_name: str) -> tuple[object, ...]:
    if contract.family == "string":
        return ("string", contract.length)
    if contract.family == "numeric":
        return ("numeric", contract.precision, contract.scale)
    if contract.family == "datetime":
        return ("datetime", True if dialect_name == "postgresql" else None)
    return (contract.family,)


def _validate_phase2b1_columns(connection: Connection, *, final: bool) -> None:
    dialect_name = connection.dialect.name
    columns = {column["name"]: column for column in inspect(connection).get_columns(TABLE_NAME)}
    for column_name, contract in PHASE2B1_COLUMN_CONTRACTS.items():
        column = columns.get(column_name)
        if column is None:
            if final:
                raise SchemaDefinitionError
            continue
        if _column_family(column["type"], dialect_name) != _expected_family(contract, dialect_name):
            raise SchemaDefinitionError
        actual_nullable = bool(column["nullable"])
        nullable_is_compatible = actual_nullable == contract.nullable
        if dialect_name == "sqlite" and column_name == "request_sent_at":
            nullable_is_compatible = actual_nullable in {False, True}
        if not nullable_is_compatible:
            raise SchemaDefinitionError

        actual_default = _normalized_default(column.get("default"))
        allowed_defaults = contract.transitional_defaults
        if dialect_name == "sqlite" and column_name == "request_sent_at":
            allowed_defaults = allowed_defaults | frozenset({None})
        if final and dialect_name == "postgresql" and column_name != "request_sent_at":
            allowed_defaults = frozenset({None})
        if actual_default not in allowed_defaults:
            raise SchemaDefinitionError


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
            if_not_exists = " IF NOT EXISTS" if is_postgresql else ""
            connection.execute(
                text(
                    f"ALTER TABLE {TABLE_NAME} ADD COLUMN{if_not_exists} "
                    f'"{column_name}" {definition}'
                )
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
    if _unique_boundary_definitions(connection):
        _validate_unique_boundary(connection)
        return
    connection.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX_NAME} "
            f"ON {TABLE_NAME} (analysis_run_id, attempt_no)"
        )
    )


def _unique_boundary_definitions(connection: Connection) -> list[tuple[bool, tuple[str, ...]]]:
    inspector = inspect(connection)
    definitions: list[tuple[bool, tuple[str, ...]]] = []
    for constraint in inspector.get_unique_constraints(TABLE_NAME):
        if constraint.get("name") == UNIQUE_INDEX_NAME:
            definitions.append((True, tuple(constraint.get("column_names") or ())))
    for index in inspector.get_indexes(TABLE_NAME):
        if index.get("name") == UNIQUE_INDEX_NAME:
            definitions.append((bool(index.get("unique")), tuple(index.get("column_names") or ())))
            dialect_options = index.get("dialect_options") or {}
            if dialect_options.get("postgresql_where") is not None:
                raise SchemaDefinitionError
    return definitions


def _validate_unique_boundary(connection: Connection) -> None:
    definitions = _unique_boundary_definitions(connection)
    expected = ("analysis_run_id", "attempt_no")
    if not definitions or any(not unique or columns != expected for unique, columns in definitions):
        raise SchemaDefinitionError


def _canonicalize_postgresql_defaults(connection: Connection) -> None:
    for column_name in POSTGRES_TEMPORARY_DEFAULT_COLUMNS:
        connection.execute(
            text(f'ALTER TABLE {TABLE_NAME} ALTER COLUMN "{column_name}" DROP DEFAULT')
        )


def _add_postgresql_checks(connection: Connection) -> None:
    for constraint_name, expression in _postgresql_checks().items():
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


def _postgresql_checks() -> dict[str, str]:
    return {
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


def _validate_postgresql_checks(connection: Connection) -> None:
    connection.execute(
        text(
            f"CREATE TEMP TABLE {POSTGRES_CONTRACT_TABLE} "
            f"(LIKE {TABLE_NAME} INCLUDING DEFAULTS) ON COMMIT DROP"
        )
    )
    for ordinal, (constraint_name, expression) in enumerate(_postgresql_checks().items(), start=1):
        expected_name = f"storylens_expected_check_{ordinal}"
        connection.execute(
            text(
                f"ALTER TABLE {POSTGRES_CONTRACT_TABLE} ADD CONSTRAINT "
                f"{expected_name} CHECK ({expression})"
            )
        )
        actual = (
            connection.execute(
                text(
                    "SELECT pg_get_constraintdef(oid, true) AS definition, "
                    "convalidated, contype "
                    "FROM pg_constraint "
                    "WHERE conrelid = to_regclass(:table_name) AND conname = :constraint_name"
                ),
                {"table_name": TABLE_NAME, "constraint_name": constraint_name},
            )
            .mappings()
            .all()
        )
        expected = (
            connection.execute(
                text(
                    "SELECT pg_get_constraintdef(oid, true) AS definition, "
                    "convalidated, contype "
                    "FROM pg_constraint "
                    "WHERE conrelid = to_regclass(:table_name) AND conname = :constraint_name"
                ),
                {
                    "table_name": f"pg_temp.{POSTGRES_CONTRACT_TABLE}",
                    "constraint_name": expected_name,
                },
            )
            .mappings()
            .all()
        )
        if (
            len(actual) != 1
            or len(expected) != 1
            or actual[0]["contype"] != "c"
            or not actual[0]["convalidated"]
            or actual[0]["definition"] != expected[0]["definition"]
        ):
            raise SchemaDefinitionError
