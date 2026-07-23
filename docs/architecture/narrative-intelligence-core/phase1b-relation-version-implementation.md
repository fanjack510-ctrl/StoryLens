# Phase 1B — Relation Version Implementation (Agent F)

**Change:** CHG-20260723-019  
**Owner:** Agent F  
**Branch:** `feature/narrative-phase1b-relations`  
**Migrations:** `20260723_009_narrative_relations_versions_evidence`

## Stable Relation vs Version

| Layer | Table | Responsibility |
|-------|-------|----------------|
| Identity | `narrative_relations` | Durable endpoints (`source_asset_id`, `target_asset_id`), `relation_key`, lock, lifecycle, stale/supersede |
| Interpretation | `narrative_relation_versions` | One analysis/user edit: `relation_type`, summary, review_status, canonical flag |

Endpoint mutation is forbidden on an existing Relation — callers must create a **new** Relation identity.

## `relation_key`

Helper: `build_relation_key` (SHA-256; never Python `hash()`).

Payload includes:

- `book_id`
- `source_asset_id` / `target_asset_id` (order preserved → A→B ≠ B→A)
- relation identity fingerprint (`relation_type` + optional disambiguator)

On key collision, service prefers a **new candidate Relation** (fresh disambiguator) rather than silently merging uncertain identities.

## Service surface

`NarrativeRelationServiceImpl` + `NarrativeRelationRepository`:

- `create_candidate_relation` — never auto-canonical
- `add_relation_version` — locked Relation still allows candidates
- `confirm_relation_version` / `correct_relation` / `reject_relation_version`
- `lock_relation` / `unlock_relation`
- `mark_relation_stale` / `clear_relation_stale` / `supersede_relation`
- `list_relations` / `get_relation` / `get_relation_versions` / `get_canonical_relation_version`

## Canonical / Lock rules

1. Only `confirmed` / `corrected` may become canonical.
2. `candidate` / `rejected` cannot.
3. At most one canonical per Relation (partial unique index + transactional clear/set).
4. Locked Relation blocks **model** canonical switches (`actor="model"` → `RELATION_LOCKED` + Conflict record).
5. User may still confirm/correct when unlocked semantics allow.
6. Canonical requires ≥1 `support` Evidence (context alone insufficient).

## Book consistency

- Both Assets must exist and share the same `book_id`.
- Relation `book_id` must match both endpoints.

## Out of scope

Entity/Alias, full Asset Service, Snapshot mutation, model calls, Pattern tables, history backfill.
