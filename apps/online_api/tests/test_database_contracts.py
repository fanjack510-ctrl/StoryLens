from sqlalchemy import UniqueConstraint
from storylens_online.db.models import OnlineBase


def _unique_column_sets(table_name: str) -> set[tuple[str, ...]]:
    table = OnlineBase.metadata.tables[table_name]
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_online_tables_are_namespaced_and_do_not_reference_desktop_tables() -> None:
    assert OnlineBase.metadata.tables
    assert all(name.startswith("online_") for name in OnlineBase.metadata.tables)
    assert all(not table.foreign_keys for table in OnlineBase.metadata.tables.values())


def test_recharge_and_ledger_idempotency_keys_are_unique() -> None:
    recharge_unique = _unique_column_sets("online_recharge_orders")
    transaction_unique = _unique_column_sets("online_wallet_transactions")
    usage_unique = _unique_column_sets("online_model_usage_ledger")
    job_unique = _unique_column_sets("online_analysis_jobs")

    assert ("external_order_no",) in recharge_unique
    assert ("idempotency_key",) in transaction_unique
    assert ("invocation_id",) in usage_unique
    assert ("analysis_run_id", "attempt_no") in usage_unique
    assert ("user_id", "idempotency_key") in job_unique
