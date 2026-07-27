# Phase 2B Context Pipeline Implementation (Agent Q)

Change: `CHG-20260723-038`  
Implementation: `apps/api/app/narrative_core/services/whole_book_context_pipeline.py`  
Units / TextRef: `whole_book_context_units.py`

## DefaultWholeBookContextPipeline

Methods: `prepare_snapshot` · `normalize_chapters` · `build_chapter_units` · `build_scene_units` · `build_paragraph_units` · `build_context_index` · `build_module_context` · `build_context_bundle` · `validate_context_bundle`

## Guarantees

1. Only **COMPLETED** Snapshot is accepted (`validate_snapshot_for_book` + integrity).
2. Snapshot must belong to the target Book.
3. Live `Paragraph` body is never used as a substitute fact source.
4. Chapter / paragraph order is deterministic (`chapter_order` / `paragraph_order`).
5. Hashes recomputed via `calculate_text_hash` / bundle fingerprint helpers.
6. `stable_paragraph_id` retained on units.
7. No second full-novel copy table; no new migrations; no FTS5 / vector / Neo4j.
8. Temporary TextRef cache is not a recovery fact source.

## Related docs

- [phase2b-text-ref-resolution.md](./phase2b-text-ref-resolution.md)
- [phase2b-context-index.md](./phase2b-context-index.md)
- [phase2b-context-bundle-builder.md](./phase2b-context-bundle-builder.md)
- [phase2b-hierarchical-context-planner.md](./phase2b-hierarchical-context-planner.md)
- [phase2b-native-enhanced-context.md](./phase2b-native-enhanced-context.md)
- [phase2b-context-evidence-verification.md](./phase2b-context-evidence-verification.md)
