# Phase 1D Pattern Map vs Structure Map Boundary

Change: `CHG-20260723-029`

## Terminology

| Layer | Name |
|-------|------|
| Product formal name | **Narrative Structure Map** |
| Agent C frontend draft dir | `apps/desktop/src/features/narrativePattern/` (may remain temporarily) |
| Agent L product adapters | `apps/desktop/src/features/wholeBook/structureMap/` |
| Authoritative data | Narrative Asset / Relation versions + Evidence |
| Display DTO | `NarrativeStructureMapProjectionDto` / legacy Pattern draft DTO |

## Rules

1. **No Pattern ORM tables** (`PATTERN_DTO_HAS_ORM_TABLE = false`).
2. Do not copy Asset/Relation content into a second Pattern store.
3. Pattern DTO is a display/spike contract only.
4. Users cannot change canonical facts on the map; Review goes through Review Action Adapter.
5. Agent C 36-default / 81-expand SVG fixtures remain compatible under `narrativePattern/`.
6. Phase 1D does **not** perform large directory renames — Integration may decide later.

## Integration note

- **II-STRUCTURE-DIR-001**: Decide whether to rename `narrativePattern` → `structureMap` after Phase 1D merge; keep dual exports during transition.
