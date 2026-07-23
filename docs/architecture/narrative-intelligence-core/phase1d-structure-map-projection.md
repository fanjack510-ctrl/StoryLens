# Phase 1D-P Structure Map Projection

`NarrativeStructureMapProjectionDto` — projection only.  
**NO Pattern tables.** Nodes/edges from canonical (or explicit candidate). Does not create new facts.

## NarrativeStructureMapProjectionDto

| Field | Notes |
|-------|-------|
| `book_id` | |
| `book_snapshot_id` | |
| `source_run_id` | optional / nullable when book-level |
| `projection_version` | |
| `root_nodes` | projected nodes |
| `edges` | projected edges |
| `filters` | view / search / fold filters |
| `evidence_index` | lazy Evidence index keys |
| `review_summary` | |
| `conflict_summary` | |
| `generated_at` | |

## Node / Edge sources

| Kind | Source |
|------|--------|
| Node | Canonical Asset Version **or** user-explicit candidate view |
| Edge | Canonical Relation Version **or** user-explicit candidate view |

Projection **does not** invent new narrative facts and **does not** map 1:1 to ORM Pattern tables (none exist).

## Three required views (v1)

1. 结构阶段视图 (structure stages)
2. 故事线视图 (storylines)
3. 人物成长视图 (character growth / arcs)

Future (out of Phase 1D-P / early Phase 2):

- 钩子回收视图
- 因果链视图
- 人物关系网络

## v1 limits & UX

| Limit / feature | Value |
|-----------------|-------|
| Max visible nodes | **100** (default) |
| Max visible edges | **250** (default) |
| Evidence | load on demand |
| Fold / search | required |
| Theme | light / dark supported |
| 原文跳转 | via Evidence deep_link |

## Hard boundaries

- **No** Narrative Pattern data tables
- **No** Neo4j / FTS5 / vector DB in this phase
- Pattern Map readiness drafts remain non-authoritative vs this projection DTO
- Agent L owns adapters; no analysis algorithms

See [phase1b-pattern-map-data-boundary.md](./phase1b-pattern-map-data-boundary.md), [phase1d-pattern-map-contract-draft.md](./phase1d-pattern-map-contract-draft.md).
