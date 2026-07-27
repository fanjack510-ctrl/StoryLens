# Phase 1B-P — Pattern Map Data Boundary

Pattern Map remains a **derived visualization**. Phase 1B-P does **not** create Pattern ORM tables or product routes.

Source DTO: `apps/desktop/src/features/narrativePattern/contracts/patternMap.draft.ts`

## What Pattern Map may consume (from Phase 1B)

| Pattern Map field | Narrative source |
|-------------------|------------------|
| `relatedAssetIds` | Stable `narrative_assets.id` (stringified) whose **canonical** version is in scope |
| `evidenceCount` | Count of evidence rows on the canonical Asset/Relation version |
| `confidence` | Canonical version `confidence` |
| `userStatus` | Derived from version `review_status` + lock (mapping owned by later Pattern adapter; not 1:1 DB enum) |
| `startChapterId` / `endChapterId` | Derived from evidence Snapshot chapter range on canonical version |
| `relatedCharacterIds` | Entity ids (`entity_type=character`) linked via future Asset↔Entity join (not in Phase 1B-P tables) |
| `relatedStorylineIds` | Asset ids with canonical `asset_type=storyline` |
| Edge `relationType` | **UI** taxonomy (`parent_child`, `setup_payoff`, …) — adapter maps from canonical `relation_type` |
| `PatternMapEvidenceRefDto` | Snapshot ids + `paragraphContentHash` from Asset/Relation evidence |

Projection DTOs (Python, not tables): `PatternMapAssetProjectionDTO`, `PatternMapRelationProjectionDTO` in `contracts/dto.py`.

## Explicit non-goals

- Do **not** create `narrative_patterns`, `pattern_nodes`, `pattern_evidence`.
- Do **not** 1:1 map frontend DTO fields into SQL tables.
- Do **not** implement pattern recognition or wire formal routes / Pro nav.
- Do **not** treat Pattern Map DTO as the Asset schema.

## Adapter ownership

Integration / later Phase 1D owns the read-model adapter that projects canonical Asset/Relation versions into `NarrativePatternMapDto`. Agents D/E/F only ensure canonical + evidence contracts are queryable.
