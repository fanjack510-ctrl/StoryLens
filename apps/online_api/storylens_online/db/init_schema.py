from __future__ import annotations

from typing import Final

from sqlalchemy import Connection, create_engine, text

from storylens_online.config import OnlineSettings
from storylens_online.db.models import OnlineBase
from storylens_online.db.phase2b1_migration import migrate_phase2b1_usage_ledger

POSTGRES_SCHEMA_LOCK_NAMESPACE: Final[int] = 0x53544F52  # STOR
POSTGRES_SCHEMA_LOCK_RESOURCE: Final[int] = 0x594C454E  # YLEN


def _acquire_schema_initialization_lock(connection: Connection) -> None:
    """Serialize all StoryLens schema initialization in PostgreSQL transactions."""

    if connection.dialect.name != "postgresql":
        return
    connection.execute(
        text(
            "SELECT pg_advisory_xact_lock(:storylens_schema_namespace, :storylens_schema_resource)"
        ),
        {
            "storylens_schema_namespace": POSTGRES_SCHEMA_LOCK_NAMESPACE,
            "storylens_schema_resource": POSTGRES_SCHEMA_LOCK_RESOURCE,
        },
    )


def initialize_schema(settings: OnlineSettings | None = None) -> None:
    """Create missing online tables without altering or deleting existing data."""

    active_settings = settings or OnlineSettings()
    engine = create_engine(active_settings.database_url)
    try:
        with engine.begin() as connection:
            _acquire_schema_initialization_lock(connection)
            OnlineBase.metadata.create_all(connection)
            migrate_phase2b1_usage_ledger(connection)
    finally:
        engine.dispose()


def main() -> int:
    initialize_schema()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
