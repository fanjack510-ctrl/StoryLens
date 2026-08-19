"""Frozen narrative migration IDs and checksum helpers (Phase 1P + Phase 1B-P).

Agent A owns bodies of 001–003; Agent B owns bodies of 004–005.
Phase 1B-P freezes 006–010 IDs/order/DDL skeleton.
Agent D owns 006 body refinements; Agent E owns 007–008; Agent F owns 009–010.
IDs and order are frozen — do not renumber or insert between.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

# Logical migration_id values (stable; used as schema_migrations.migration_id).
MIGRATION_SCHEMA_MIGRATIONS = "20260723_001_schema_migrations"
MIGRATION_CONTENT_HASHES = "20260723_002_content_hashes"
MIGRATION_BOOK_SNAPSHOTS = "20260723_003_book_snapshots"
MIGRATION_ANALYSIS_RUN_SCOPE = "20260723_004_analysis_run_scope"
MIGRATION_ANALYSIS_RUN_STAGES = "20260723_005_analysis_run_stages"
MIGRATION_NARRATIVE_ENTITIES_ALIASES = "20260723_006_narrative_entities_aliases"
MIGRATION_NARRATIVE_ASSETS_VERSIONS = "20260723_007_narrative_assets_versions"
MIGRATION_NARRATIVE_ASSET_EVIDENCE = "20260723_008_narrative_asset_evidence"
MIGRATION_NARRATIVE_RELATIONS_VERSIONS_EVIDENCE = (
    "20260723_009_narrative_relations_versions_evidence"
)
MIGRATION_ANALYSIS_CONFLICTS = "20260723_010_analysis_conflicts"
MIGRATION_WHOLE_BOOK_OVERVIEW_RUNTIME = "20260725_011_whole_book_overview_runtime"
MIGRATION_WHOLE_BOOK_FOUNDATION_V1 = "20260728_012_whole_book_foundation_v1"
MIGRATION_WHOLE_BOOK_SNAPSHOT_IMMUTABILITY = "20260728_013_whole_book_snapshot_immutability"
MIGRATION_WHOLE_BOOK_MINIMAL_ANALYSIS_RESULTS = (
    "20260728_014_whole_book_minimal_analysis_results"
)
MIGRATION_WHOLE_BOOK_RUNTIME_CONTROL = "20260728_015_whole_book_runtime_control"
MIGRATION_WHOLE_BOOK_NATIVE_INPUT_AUDIT = "20260728_016_whole_book_native_input_audit"
MIGRATION_WHOLE_BOOK_RUN_PROVIDER_PINNING = "20260808_017_whole_book_run_provider_pinning"
MIGRATION_LONG_NOVEL_FOUNDATION = "20260812_018_long_novel_foundation"
MIGRATION_BOOK_PROFILE = "20260813_019_book_profile"
MIGRATION_SHORT_FORM_RESULTS = "20260818_020_short_form_results"
MIGRATION_BOOK_ANALYSIS_FORM = "20260819_021_book_analysis_form"

BASELINE_MARKER_ID = "baseline_1_0_5"

NARRATIVE_MIGRATION_ORDER: tuple[str, ...] = (
    MIGRATION_SCHEMA_MIGRATIONS,
    MIGRATION_CONTENT_HASHES,
    MIGRATION_BOOK_SNAPSHOTS,
    MIGRATION_ANALYSIS_RUN_SCOPE,
    MIGRATION_ANALYSIS_RUN_STAGES,
    MIGRATION_NARRATIVE_ENTITIES_ALIASES,
    MIGRATION_NARRATIVE_ASSETS_VERSIONS,
    MIGRATION_NARRATIVE_ASSET_EVIDENCE,
    MIGRATION_NARRATIVE_RELATIONS_VERSIONS_EVIDENCE,
    MIGRATION_ANALYSIS_CONFLICTS,
    MIGRATION_WHOLE_BOOK_OVERVIEW_RUNTIME,
    MIGRATION_WHOLE_BOOK_FOUNDATION_V1,
    MIGRATION_WHOLE_BOOK_SNAPSHOT_IMMUTABILITY,
    MIGRATION_WHOLE_BOOK_MINIMAL_ANALYSIS_RESULTS,
    MIGRATION_WHOLE_BOOK_RUNTIME_CONTROL,
    MIGRATION_WHOLE_BOOK_NATIVE_INPUT_AUDIT,
    MIGRATION_WHOLE_BOOK_RUN_PROVIDER_PINNING,
    MIGRATION_LONG_NOVEL_FOUNDATION,
    MIGRATION_BOOK_PROFILE,
    MIGRATION_SHORT_FORM_RESULTS,
    MIGRATION_BOOK_ANALYSIS_FORM,
)

# Ownership for parallel Agents (documentation + tooling).
MIGRATION_OWNER: dict[str, str] = {
    MIGRATION_SCHEMA_MIGRATIONS: "agent_a",
    MIGRATION_CONTENT_HASHES: "agent_a",
    MIGRATION_BOOK_SNAPSHOTS: "agent_a",
    MIGRATION_ANALYSIS_RUN_SCOPE: "agent_b",
    MIGRATION_ANALYSIS_RUN_STAGES: "agent_b",
    MIGRATION_NARRATIVE_ENTITIES_ALIASES: "agent_d",
    MIGRATION_NARRATIVE_ASSETS_VERSIONS: "agent_e",
    MIGRATION_NARRATIVE_ASSET_EVIDENCE: "agent_e",
    MIGRATION_NARRATIVE_RELATIONS_VERSIONS_EVIDENCE: "agent_f",
    MIGRATION_ANALYSIS_CONFLICTS: "agent_f",
    MIGRATION_WHOLE_BOOK_OVERVIEW_RUNTIME: "integration",
    MIGRATION_WHOLE_BOOK_FOUNDATION_V1: "integration",
    MIGRATION_WHOLE_BOOK_SNAPSHOT_IMMUTABILITY: "integration",
    MIGRATION_WHOLE_BOOK_MINIMAL_ANALYSIS_RESULTS: "integration",
    MIGRATION_WHOLE_BOOK_RUNTIME_CONTROL: "integration",
    MIGRATION_WHOLE_BOOK_NATIVE_INPUT_AUDIT: "integration",
    MIGRATION_WHOLE_BOOK_RUN_PROVIDER_PINNING: "integration",
    MIGRATION_LONG_NOVEL_FOUNDATION: "integration",
}


def migration_checksum(source: str) -> str:
    """SHA-256 of canonical UTF-8 source used as migration checksum input."""
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def assert_unique_migration_ids(ids: Sequence[str] = NARRATIVE_MIGRATION_ORDER) -> None:
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate migration_id in NARRATIVE_MIGRATION_ORDER")
