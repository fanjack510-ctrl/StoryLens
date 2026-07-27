# Phase 1D Evidence Read Implementation (Agent L)

Change: `CHG-20260723-029`  
Service: `apps/api/app/narrative_core/services/evidence_read_service.py`

## API

| Method | Purpose |
|--------|---------|
| `get_evidence_ref` | Project Asset/Relation Evidence → `WholeBookEvidenceRefDto` |
| `get_evidence_preview` | Short preview (≤160 chars) |
| `get_evidence_text` | On-demand Snapshot excerpt; full text not retained on DTO |
| `validate_evidence_integrity` | `valid` / `stale` / `hash_mismatch` / `missing` / `inaccessible` |
| `build_evidence_deep_link` | Chapter/scene/paragraph query deep link |

## Rules honored

1. Uses Phase 1A `BookSnapshotServiceImpl.get_snapshot_paragraph_text` only.
2. Never substitutes live `Paragraph` rows for Snapshot Evidence body.
3. Validates `paragraph_content_hash` and start/end offsets.
4. Preview clipped to `MAX_PARAGRAPH_PREVIEW_CHARS`.
5. Hash mismatch deep links set `locateBlocked=1` — UI must not silent-locate.
6. Old Snapshot Evidence remains readable after live body edits.

## Frontend

Isolated drawer under `apps/desktop/src/features/wholeBook/review/`  
(`WholeBookEvidenceDrawer`, `EvidencePreviewCard`, badges, source link).

Not wired into formal result-page navigation.
