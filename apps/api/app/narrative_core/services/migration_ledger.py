"""Migration ledger service (Agent A).

Implements Phase 1P ``MigrationLedger`` Protocol against ``schema_migrations``.
Does not renumber migrations or introduce Alembic.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.migrations import BASELINE_MARKER_ID, migration_checksum
from app.narrative_core.migrations.runner import (
    SQL_001,
    SQL_002,
    SQL_003,
    _ensure_schema_migrations_table,
    migrate_narrative_20260723_001_schema_migrations,
    migrate_narrative_20260723_002_content_hashes,
    migrate_narrative_20260723_003_book_snapshots,
    register_baseline_1_0_5 as runner_register_baseline,
)

BASELINE_SOURCE = "StoryLens baseline 1.0.5 narrative phase1 prelude"

# Agent A owned migration SQL bodies (checksum sources frozen in runner).
AGENT_A_SQL: dict[str, str] = {
    "20260723_001_schema_migrations": SQL_001,
    "20260723_002_content_hashes": SQL_002,
    "20260723_003_book_snapshots": SQL_003,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class MigrationLedgerService:
    """SQLite-backed migration ledger with checksum conflict detection."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_ledger_table(self) -> None:
        _ensure_schema_migrations_table(self._engine)

    def get_applied_migration(self, migration_id: str) -> dict | None:
        self.ensure_ledger_table()
        with self._engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT migration_id, checksum, app_version, applied_at "
                    "FROM schema_migrations WHERE migration_id = :migration_id"
                ),
                {"migration_id": migration_id},
            ).fetchone()
        if row is None:
            return None
        return {
            "migration_id": str(row[0]),
            "checksum": str(row[1]),
            "app_version": str(row[2]),
            "applied_at": str(row[3]),
        }

    def record_applied_migration(
        self,
        migration_id: str,
        checksum: str,
        *,
        app_version: str = "1.0.5",
    ) -> None:
        self.ensure_ledger_table()
        existing = self.get_applied_migration(migration_id)
        if existing is not None:
            if existing["checksum"] != checksum:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.MIGRATION_CHECKSUM_MISMATCH,
                    (
                        f"{migration_id} stored={existing['checksum']} "
                        f"expected={checksum}"
                    ),
                )
            return
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO schema_migrations
                        (migration_id, checksum, app_version, applied_at)
                    VALUES
                        (:migration_id, :checksum, :app_version, :applied_at)
                    """
                ),
                {
                    "migration_id": migration_id,
                    "checksum": checksum,
                    "app_version": app_version,
                    "applied_at": _utc_now_iso(),
                },
            )

    def validate_migration_checksum(self, migration_id: str, checksum: str) -> bool:
        existing = self.get_applied_migration(migration_id)
        if existing is None:
            return True
        if existing["checksum"] == checksum:
            return True
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.MIGRATION_CHECKSUM_MISMATCH,
            f"{migration_id} stored={existing['checksum']} expected={checksum}",
        )

    def register_baseline_1_0_5(self) -> None:
        """Register legal baseline marker; reject checksum drift as invalid baseline."""
        self.ensure_ledger_table()
        expected = migration_checksum(BASELINE_SOURCE)
        existing = self.get_applied_migration(BASELINE_MARKER_ID)
        if existing is not None:
            if existing["checksum"] != expected:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.MIGRATION_BASELINE_INVALID,
                    "baseline_1_0_5 checksum mismatch",
                )
            return
        self.record_applied_migration(BASELINE_MARKER_ID, expected, app_version="1.0.5")

    def expected_checksum(self, migration_id: str) -> str:
        if migration_id == BASELINE_MARKER_ID:
            return migration_checksum(BASELINE_SOURCE)
        if migration_id not in AGENT_A_SQL:
            raise KeyError(f"unknown Agent A migration_id: {migration_id}")
        return migration_checksum(AGENT_A_SQL[migration_id])

    def apply_agent_a_migrations(self) -> None:
        """Apply Agent A migrations (001–003) with ledger registration on success only."""
        runner_register_baseline(self._engine)
        migrate_narrative_20260723_001_schema_migrations(self._engine)
        migrate_narrative_20260723_002_content_hashes(self._engine)
        migrate_narrative_20260723_003_book_snapshots(self._engine)


def migration_ledger_from_session(session: Session) -> MigrationLedgerService:
    bind = session.get_bind()
    if bind is None:
        raise RuntimeError("Session has no bind")
    return MigrationLedgerService(bind)  # type: ignore[arg-type]
