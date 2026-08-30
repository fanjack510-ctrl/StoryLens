from __future__ import annotations

from sqlalchemy import create_engine

from storylens_online.config import OnlineSettings
from storylens_online.db.models import OnlineBase
from storylens_online.db.phase2b1_migration import migrate_phase2b1_usage_ledger


def initialize_schema(settings: OnlineSettings | None = None) -> None:
    """Create missing online tables without altering or deleting existing data."""

    active_settings = settings or OnlineSettings()
    engine = create_engine(active_settings.database_url)
    try:
        OnlineBase.metadata.create_all(engine)
        migrate_phase2b1_usage_ledger(engine)
    finally:
        engine.dispose()


def main() -> int:
    initialize_schema()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
