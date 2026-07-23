# Phase 1B-P — Evidence Contract

Applies to `narrative_asset_evidence` and `narrative_relation_evidence`.

## Binding target

Evidence binds a **Version** row (`asset_version_id` / `relation_version_id`), not only the stable identity.

## Required fields

| Field | Rule |
|-------|------|
| `book_snapshot_id` | Snapshot must be `COMPLETED`; book must match Asset/Relation book |
| `snapshot_chapter_id` | Must belong to that Snapshot |
| `snapshot_paragraph_id` | **Required** (never null); must belong to Snapshot |
| `paragraph_content_hash` | Must match Snapshot paragraph hash |
| `start_offset` / `end_offset` | Offsets **inside** paragraph; `start >= 0`, `end >= start`, within paragraph length |
| `source_scene_id` | Optional (nullable) |
| `evidence_role` | support \| contradict \| context |

## Body storage

- Evidence does **not** store a full user-text copy.
- Exact text is recovered via Phase 1A Snapshot APIs (`BookSnapshotService.get_snapshot_paragraph_text` / chapter `content_text` slice).
- After live book edits, old Evidence remains reproducible through the **old** Snapshot.

## Version snapshot match

When the parent Version has `book_snapshot_id`, evidence **must** use the same snapshot (`assert_evidence_matches_version_snapshot`). Mismatch → `EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH`.

## Canonical support evidence

Promoting a Version to canonical requires at least one attached evidence row with `evidence_role=support`. Context-only or contradict-only evidence is insufficient.

## Validation ownership

Agent E / F **must** reuse Phase 1A `SnapshotValidationGateway` / Snapshot services.  
**Forbidden:** a second independent body-reader path.

## Error codes (frozen)

`EVIDENCE_SNAPSHOT_REQUIRED`, `EVIDENCE_PARAGRAPH_REQUIRED`, `EVIDENCE_HASH_MISMATCH`, `EVIDENCE_OFFSET_OUT_OF_RANGE`, `EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH`, plus existing Snapshot codes.
