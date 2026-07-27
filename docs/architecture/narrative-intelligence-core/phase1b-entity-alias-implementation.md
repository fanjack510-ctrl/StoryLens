# Phase 1B — Entity / Alias Implementation (Agent D)

**Change:** CHG-20260723-017  
**Branch:** `feature/narrative-phase1b-entities`  
**Worktree:** `D:\Dstorylens-wt-narrative-entities`  
**Baseline:** `633ba93239f727474eaa27c769608870c0ffe12b` (VERSION `1.0.5`)

## Scope delivered

| Area | Path | Notes |
|------|------|-------|
| Migration 006 | `apps/api/app/narrative_core/migrations/runner.py` | Idempotent DDL + indexes; checksum of `SQL_006`; no backfill |
| Repository | `apps/api/app/narrative_core/services/entity_repository.py` | ORM helpers |
| Service | `apps/api/app/narrative_core/services/entity_service.py` | Contract operations + review/lock |
| Tests | `apps/api/tests/test_narrative_entity_alias.py` | Directed suite |
| Errors (additive) | `apps/api/app/narrative_core/errors.py` | `ENTITY_INVALID_NAME`, `ENTITY_NOT_ACTIVE`, `ENTITY_MERGE_NOT_SUPPORTED`, `ALIAS_LOCKED` |

## Entity API

- `create_entity` — stable identity; empty `canonical_name` rejected; `normalized_name` via `normalize_entity_name`
- `get_entity` / `list_entities`
- `lock_entity` / `unlock_entity` — orthogonal to Alias `review_status`; idempotent
- `archive_entity` / `supersede_entity` — soft lifecycle only (no physical delete)
- Same book may hold multiple entities with the same display name (no auto-merge)

## Alias API

- `add_alias_candidate` — model discoveries are candidates only; never overwrite `canonical_name`
- `confirm_alias` / `reject_alias` — blocked when Alias `is_locked`
- `lock_alias` / `unlock_alias`
- `list_entity_aliases`
- `find_entity_by_alias` — book-scoped; confirmed only; returns `AliasLookupResult` (`none` / `unique` / `ambiguous`)
- Duplicate `(entity_id, normalized_alias)` is idempotent (returns existing row); concurrent inserts use savepoint + unique constraint

## Normalization

Uses frozen helper `app.narrative_core.asset_key.normalize_entity_name` (whitespace collapse + ASCII lower). Preserves CJK and digits. No 简繁 conversion, nickname guessing, or book-specific rules.

## Explicitly out of scope

- `models.py` schema edits
- Asset / Relation / Conflict / Snapshot / Run Stage services
- Pattern Map, Capability, VERSION, build/publish/push
- AI disambiguation / prompts / model calls
- Historical entity backfill

See also: [phase1b-entity-merge-boundary.md](./phase1b-entity-merge-boundary.md), [phase1b-entity-alias-verification.md](./phase1b-entity-alias-verification.md).
