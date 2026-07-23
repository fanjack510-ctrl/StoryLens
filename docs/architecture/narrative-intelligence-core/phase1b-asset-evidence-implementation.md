# Phase 1B Agent E — Asset Evidence Implementation

**Change:** CHG-20260723-018

## Binding

Evidence rows bind an **Asset Version** (`asset_version_id`), not only the stable Asset id.

Fields (contract-aligned):

| Field | Rule |
|-------|------|
| `book_snapshot_id` | Snapshot must be `COMPLETED`; book matches Asset |
| `snapshot_chapter_id` | Belongs to Snapshot |
| `snapshot_paragraph_id` | Required; belongs to Snapshot Chapter |
| `paragraph_content_hash` | Must equal Snapshot Paragraph hash |
| `start_offset` / `end_offset` | Paragraph-local; `0 ≤ start ≤ end ≤ len(paragraph)` |
| `source_scene_id` | Optional |
| `evidence_role` | `support` \| `contradict` \| `context` only |

Evidence does **not** store a full body copy. Excerpts are restored via Phase 1A:

- `SnapshotValidationGateway.validate_snapshot_for_book`
- `BookSnapshotServiceImpl.get_snapshot_paragraph_text`

## Service API

`NarrativeAssetEvidenceService` (+ delegation from `NarrativeAssetService`):

- `attach_asset_evidence(...)`
- `validate_asset_evidence(...)`
- `list_asset_version_evidence(...)`
- `remove_candidate_evidence(...)`
- `restore_evidence_excerpt(...)` (test/helper)

## Protection rules

1. Model cannot silently delete evidence on `confirmed` / `corrected` **canonical** versions.
2. Model cannot modify formal evidence on a **locked** Asset’s confirmed/corrected canonical version.
3. Model may remove evidence only on **candidate** versions.
4. Live book edits create a new Snapshot; old Snapshot evidence remains reproducible.

## Error codes used

`EVIDENCE_SNAPSHOT_REQUIRED`, `EVIDENCE_PARAGRAPH_REQUIRED`, `EVIDENCE_HASH_MISMATCH`, `EVIDENCE_OFFSET_OUT_OF_RANGE`, `EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH`, plus Snapshot codes (`SNAPSHOT_NOT_COMPLETED`, `SNAPSHOT_BOOK_MISMATCH`, …).
