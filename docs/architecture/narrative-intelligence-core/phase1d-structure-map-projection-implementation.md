# Phase 1D Structure Map Projection Implementation (Agent L)

Change: `CHG-20260723-029`  
Service: `apps/api/app/narrative_core/services/structure_map_projection.py`

## Output

`NarrativeStructureMapProjectionDto` — projection only.

## Inputs

- Canonical Asset / Relation versions (default)
- `include_candidates=True` explicit opt-in
- Evidence index keys (lazy)
- Review / Conflict summaries

## Views

1. `structure_stages`
2. `storylines`
3. `character_growth`

## Limits

- Default max nodes **100**, max edges **250**
- Truncation flagged in `review_summary.truncated*`
- Evidence keys only (`asset_evidence:{id}` / `relation_evidence:{id}`)
- `writes_database_facts=false`, `pattern_orm_table=false`

## Non-goals

- No Pattern tables / migrations
- No analysis algorithms
- No Neo4j / graph DB
- Node/edge positions are not story facts
