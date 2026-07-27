# Phase 1D Structure Map Integration

## Projection Source Protocol

`NarrativeProjectionSource` (`narrative_projection_source.py`) is implemented by  
`WholeBookResultIndexService` and consumed by `NarrativeStructureMapProjectionService`.

Required inputs:

- `get_canonical_assets_for_projection` / `get_candidate_assets_for_projection`
- `get_canonical_relations_for_projection` / `get_candidate_relations_for_projection`
- `get_evidence_index` / `get_review_summary` / `get_conflict_summary`

Structure Map **must not** maintain a parallel Asset/Relation query path.

## Behavior

- Canonical default; candidates require `include_candidates=True`
- Rejected excluded
- Lock / stale / conflict marked via projection metadata
- Book + Snapshot isolation
- Nodes → Asset Version; Edges → Relation Version
- Default limits: 100 nodes / 250 edges with truncation flags
- Evidence lazy (ids/hashes only)
- Three views: structure_stages / storylines / character_growth
- Zero-dependency SVG FE prototype; **not** in product nav
- No Pattern ORM tables / no new facts written
