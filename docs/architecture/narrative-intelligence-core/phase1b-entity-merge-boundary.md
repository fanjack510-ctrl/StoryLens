# Phase 1B — Entity / Alias Merge Boundary (Agent D)

**Change:** CHG-20260723-017

## Schema check

| Column / capability | `NarrativeEntity` | `NarrativeAsset` / `NarrativeRelation` |
|---------------------|-------------------|----------------------------------------|
| `lifecycle_status` including `superseded` | yes | yes |
| `superseded_by_*_id` target lineage | **no** | yes |

Frozen ORM (`models.py`) for Entity has **no** `superseded_by_entity_id`. Agent D must not alter table structure or invent JSON surrogate fields.

## Decision

`merge_entities(survivor_id, absorbed_id)` **returns** `NarrativeCoreError(ENTITY_MERGE_NOT_SUPPORTED)` after validating:

1. ids differ
2. both entities exist
3. same `book_id`

It does **not**:

- move aliases
- mark source superseded/archived
- rewrite Asset `attributes_json`
- fabricate a target pointer

Rationale: without persisted superseded-target lineage, a “successful” merge would lose auditability and violate Phase 1B-P review/lock versioning semantics (`superseded` + `superseded_by_*_id`).

## Partial lifecycle still available

- `archive_entity` — soft archive
- `supersede_entity` — sets `lifecycle_status=superseded` **without** recording target (documented limitation; full supersede-with-target deferred)

## Integration follow-up

See **II-ENTITY-001** in [phase1b-entity-alias-verification.md](./phase1b-entity-alias-verification.md): add `superseded_by_entity_id` in a future coordinated schema Change, then implement transactional merge (alias dedupe move, retain confirmed/locked, no canonical auto-overwrite).
