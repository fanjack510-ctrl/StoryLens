# Phase 1B Agent E — Asset / Version Implementation

**Change:** CHG-20260723-018  
**Branch:** `feature/narrative-phase1b-assets`  
**Worktree:** `D:\Dstorylens-wt-narrative-assets`  
**Baseline:** `633ba93239f727474eaa27c769608870c0ffe12b` (Phase 1B-P)

## Scope

Implements stable Narrative Asset identity, versioned interpretations, review/canonical/lock/stale/supersede semantics, and migrations **007 / 008**.

| Component | Path |
|-----------|------|
| Repository | `apps/api/app/narrative_core/services/asset_repository.py` |
| Service | `apps/api/app/narrative_core/services/asset_service.py` |
| Evidence | `apps/api/app/narrative_core/services/asset_evidence_service.py` |
| Migrations | `runner.py` — `20260723_007_*`, `20260723_008_*` only |

## Stable Asset vs Version

- `NarrativeAsset` stores durable identity (`asset_key`, lock, lifecycle, stale markers).
- `NarrativeAssetVersion` stores one analysis or user correction (title/summary/review/canonical).
- Versions are never physically deleted; corrections always insert a new row.

## Canonical rules (implemented)

1. `create_candidate_asset` / `add_asset_version` never set `is_canonical`.
2. `confirm_asset_version` → `review_status=confirmed`; optional canonical switch.
3. `correct_asset` → new `corrected` version; optional canonical switch.
4. `rejected` cannot be confirmed or made canonical.
5. Switch clears prior `is_canonical` then sets the new flag inside one nested transaction.
6. Partial unique index `uq_narrative_asset_versions_one_canonical` enforces ≤1 canonical per asset.
7. `actor=model` + locked asset → `AssetCanonicalConflictRequest` (no AnalysisConflict write).
8. `actor=model` must not replace user `confirmed` / `corrected` canonical → ConflictRequest.

## Lock / Stale / Supersede

- Lock lives on the stable Asset; orthogonal to `review_status`.
- Locked: model cannot switch canonical; model may still add candidates.
- `mark_asset_stale` / `clear_asset_stale` use `stale_at` / `stale_reason` (+ lifecycle `stale`); stale ≠ rejected.
- `supersede_asset` links stable identities (`superseded_by_asset_id`); not a version update.
- `list_assets` defaults to excluding `archived` / `superseded`; pass explicit flags to include.

## Migrations 007 / 008

- Idempotent: skip CREATE when primary table exists; always `CREATE INDEX IF NOT EXISTS` (including partial unique).
- Checksum = SHA-256 of LF-normalized `SQL_007` / `SQL_008` bodies (unchanged from Phase 1B-P freeze).
- Ledger recorded only after successful DDL; mismatch raises `MIGRATION_CHECKSUM_MISMATCH`.
- No historical JSON backfill.

## Out of scope (this Agent)

Entity/Alias, Relation, AnalysisConflict persistence, Pattern tables, model calls, `models.py` edits, VERSION/tag/publish/push.
