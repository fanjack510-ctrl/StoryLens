"""Frozen narrative migration IDs and checksum helpers (Phase 1P).

Agent A owns bodies of 001–003; Agent B owns bodies of 004–005.
IDs and order are frozen — do not renumber.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence

from sqlalchemy.engine import Engine

# Logical migration_id values (stable; used as schema_migrations.migration_id).
MIGRATION_SCHEMA_MIGRATIONS = "20260723_001_schema_migrations"
MIGRATION_CONTENT_HASHES = "20260723_002_content_hashes"
MIGRATION_BOOK_SNAPSHOTS = "20260723_003_book_snapshots"
MIGRATION_ANALYSIS_RUN_SCOPE = "20260723_004_analysis_run_scope"
MIGRATION_ANALYSIS_RUN_STAGES = "20260723_005_analysis_run_stages"

BASELINE_MARKER_ID = "baseline_1_0_5"

NARRATIVE_MIGRATION_ORDER: tuple[str, ...] = (
    MIGRATION_SCHEMA_MIGRATIONS,
    MIGRATION_CONTENT_HASHES,
    MIGRATION_BOOK_SNAPSHOTS,
    MIGRATION_ANALYSIS_RUN_SCOPE,
    MIGRATION_ANALYSIS_RUN_STAGES,
)

# Ownership for parallel Agents (documentation + tooling).
MIGRATION_OWNER: dict[str, str] = {
    MIGRATION_SCHEMA_MIGRATIONS: "agent_a",
    MIGRATION_CONTENT_HASHES: "agent_a",
    MIGRATION_BOOK_SNAPSHOTS: "agent_a",
    MIGRATION_ANALYSIS_RUN_SCOPE: "agent_b",
    MIGRATION_ANALYSIS_RUN_STAGES: "agent_b",
}


def migration_checksum(source: str) -> str:
    """SHA-256 of canonical UTF-8 source used as migration checksum input."""
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def assert_unique_migration_ids(ids: Sequence[str] = NARRATIVE_MIGRATION_ORDER) -> None:
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate migration_id in NARRATIVE_MIGRATION_ORDER")
