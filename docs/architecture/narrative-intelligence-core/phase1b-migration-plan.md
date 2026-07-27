# Phase 1B-P — Migration Plan

Baseline: Phase 1A migrations `001–005` remain unchanged.

| # | migration_id | Owner | Precondition | Effect |
|---|--------------|-------|--------------|--------|
| 6 | `20260723_006_narrative_entities_aliases` | Agent D | 001–005 applied | `narrative_entities`, `narrative_entity_aliases` |
| 7 | `20260723_007_narrative_assets_versions` | Agent E | 006 optional for FK independence; ledger order after 006 | `narrative_assets`, `narrative_asset_versions` + partial unique canonical index |
| 8 | `20260723_008_narrative_asset_evidence` | Agent E | 007 + Snapshot tables | `narrative_asset_evidence` |
| 9 | `20260723_009_narrative_relations_versions_evidence` | Agent F | 007 (Asset FKs) | `narrative_relations`, `narrative_relation_versions`, `narrative_relation_evidence` |
| 10 | `20260723_010_analysis_conflicts` | Agent F | books / runs / snapshots | `analysis_conflicts` |

## Checksum

Reuse Phase 1A `migration_checksum()`: SHA-256 of LF-normalized `SQL_00N` body constants in `migrations/runner.py`.

Mismatch → `NarrativeCoreError(MIGRATION_CHECKSUM_MISMATCH)`.

## Idempotency

Each migrator skips CREATE when the primary table already exists (e.g. after `Base.metadata.create_all`), then records ledger row.

## Entry point

`apply_narrative_phase1bp_migrations(engine)` (calls Phase 1P then 006–010).  
Hooked from `apps/api/app/db/session.py` `create_db()`.

## Rules

1. Do not renumber 001–005 or 006–010.
2. Subsequent Agents must not invent new `migration_id` values between these.
3. Agents may refine **owned** SQL bodies only with checksum-compatible discipline (prefer Integration coordination).
4. No historical data backfill in Phase 1B-P.
5. ORM skeleton in `models.py` is frozen for Agents D/E/F — no table-structure edits.
