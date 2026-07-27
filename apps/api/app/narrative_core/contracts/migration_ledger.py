"""Migration ledger Protocol (Agent A implements)."""

from __future__ import annotations

from typing import Protocol


class MigrationLedger(Protocol):
    def get_applied_migration(self, migration_id: str) -> dict | None:
        """Return ledger row dict or None if not applied."""

    def record_applied_migration(
        self,
        migration_id: str,
        checksum: str,
        *,
        app_version: str = "1.0.5",
    ) -> None:
        """Insert applied migration row. Raises on checksum conflict."""

    def validate_migration_checksum(self, migration_id: str, checksum: str) -> bool:
        """True if not applied yet or stored checksum matches."""

    def register_baseline_1_0_5(self) -> None:
        """Record that the database was upgraded from StoryLens 1.0.5 baseline."""
