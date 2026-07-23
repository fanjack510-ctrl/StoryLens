# Phase 1B — Entity / Alias Merge Boundary (Agent D + Integration)

**Change:** CHG-20260723-017, CHG-20260723-020

## Schema (post-Integration)

| Column / capability | `NarrativeEntity` | `NarrativeAsset` / `NarrativeRelation` |
|---------------------|-------------------|----------------------------------------|
| `lifecycle_status` including `superseded` | yes | yes |
| `superseded_by_*_id` target lineage | **yes** (`superseded_by_entity_id`) | yes |

Migration `20260723_006` includes `superseded_by_entity_id` (revised pre-release checksum).

## Implemented merge

`merge_entities(source_id, target_id)`:

1. Validates ids differ, same `book_id`, target active, source not archived/superseded
2. Moves non-duplicate aliases to target (dedupe by `normalized_alias`)
3. Sets source `lifecycle_status=superseded`, `superseded_by_entity_id=target.id`
4. Does **not** rewrite Asset `attributes_json` entity references

## Still deferred

- Auto-update Asset/Relation entity links on merge
- Bulk supersede of Assets tied to merged entity

See [phase1b-known-limitations.md](./phase1b-known-limitations.md).
