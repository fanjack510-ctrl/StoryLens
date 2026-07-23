# Phase 1B Integrated Migration Verification

## Order (frozen, not renumbered)

1. `20260723_001_schema_migrations`
2. `20260723_002_content_hashes`
3. `20260723_003_book_snapshots`
4. `20260723_004_analysis_run_scope`
5. `20260723_005_analysis_run_stages`
6. `20260723_006_narrative_entities_aliases` — **revised pre-release** (see below)
7. `20260723_007_narrative_assets_versions`
8. `20260723_008_narrative_asset_evidence`
9. `20260723_009_narrative_relations_versions_evidence`
10. `20260723_010_analysis_conflicts`

Plus ledger marker `baseline_1_0_5`.

Entry point: `apply_narrative_phase1bp_migrations` (calls 001–005 via `apply_narrative_phase1p_migrations`, then 006–010).

## Schema correction note (006)

Integration added `superseded_by_entity_id` to `SQL_006` and idempotent `ALTER TABLE` for partial upgrades. **Checksum change is allowed** because Phase 1B is unpublished — fresh DBs and ledger both record the revised body SHA-256.

## Guarantees verified

| Property | Result |
|----------|--------|
| migration_id unique (10 entries) | yes |
| runner order via `apply_narrative_phase1bp_migrations` | yes |
| checksum stable (SHA-256 of SQL body) | yes |
| success then register | yes |
| checksum conflict → `MIGRATION_CHECKSUM_MISMATCH` | yes |
| re-run idempotent | yes |
| Phase 1A-only DB → upgrade to 010 | yes |
| legacy `analysis_runs` readable | yes |
| no historical backfill | yes |
| SQLite FK pragma + integrity_check | yes |

## No renumber / no backfill

Migration IDs 006–010 are frozen. Integration does not insert new IDs or renumber. No entity/asset/relation backfill runs in migration runners.
