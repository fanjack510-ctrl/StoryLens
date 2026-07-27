# Phase 1B-P — Narrative Relation Contract

**Owner:** Agent F (CHG-20260723-019)  
**Migrations:** `20260723_009_narrative_relations_versions_evidence`, `20260723_010_analysis_conflicts`

## Stable Relation

`narrative_relations` endpoints are **stable Asset ids** (`source_asset_id`, `target_asset_id`).

If endpoints change → create a **new** Relation identity (do not mutate old Relation versions' endpoints).

`relation_key` via `build_relation_key(book_id, source_asset_id, target_asset_id, identity_fingerprint)` — SHA-256 hex digest; no Python `hash()`. Caller should pass a stable `identity_fingerprint`; omitting it creates an independent key via random UUID.

## Version

`narrative_relation_versions` mirrors Asset Version semantics:

- `review_status`: candidate | confirmed | corrected | rejected
- `origin_type`: model | user | migrated | system
- `is_canonical` with partial unique index per `relation_id`
- Lock on Relation identity blocks model-driven canonical switches

## Relation types (minimum extensible set)

causes, enables, blocks, escalates, resolves, pays_off, foreshadows, reveals, contradicts, belongs_to, advances, changes_relationship, precedes, parallels

Type name alone does **not** prove existence — Evidence required.

## Analysis Conflict

`analysis_conflicts` records (no auto-adjudication in this phase):

- locked asset vs new run
- candidate contradiction
- entity identity conflict
- relation conflict
- evidence stale / snapshot mismatch
- duplicate asset candidate

`status`: open | resolved | dismissed  
`severity`: info | warning | blocking

## Protocol

`NarrativeRelationService` + `AnalysisConflictService` in `contracts/relation.py`.
