# Phase 1B Entity → Asset → Relation E2E

**Test file:** `apps/api/tests/test_narrative_phase1b_integration.py`  
**Primary test:** `test_entity_asset_relation_e2e_lock_conflict_projection`

## Path exercised

1. Seed Book + Chapters + Paragraphs
2. Build COMPLETED `BookSnapshot` (Phase 1A gateway)
3. Create book-scope `AnalysisRun` with `book_id` + `book_snapshot_id`
4. Create Entity + confirm Alias
5. Create Asset + Version bound to run/snapshot; attach **support** evidence
6. User confirms Asset Version → canonical
7. Second Asset + canonical (relation endpoints)
8. Create Relation with explicit `identity_fingerprint` → evidence → canonical
9. Lock first Asset
10. Model adds confirmed Version + support evidence; `confirm_asset_version(actor="model")` → **conflict**, canonical unchanged
11. `analysis_conflicts` row persisted (`LOCKED_ASSET_VS_NEW_RUN`)
12. Unlock; user confirms new Version → canonical switches
13. Prior Version + Evidence rows retained
14. `build_pattern_projection_input(book_id)` returns canonical assets/relations with evidence counts, chapter ids, paragraph hashes, `entity_ids` from `attributes_json`

## Related negative tests (same file)

- Version snapshot ≠ evidence snapshot → rejected
- Run snapshot ≠ version snapshot → rejected
- Cross-book conflict refs → `CONFLICT_CROSS_BOOK`
- Canonical without support evidence → rejected
- Context-only evidence → cannot canonical

## Dependencies

Reuses helpers/patterns from Agent D/E/F directed suites (`_seed_book`, `_completed_snapshot`, evidence attach, migration factory).
