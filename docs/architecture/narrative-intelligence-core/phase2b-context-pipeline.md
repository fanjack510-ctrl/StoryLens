# Phase 2B Context Pipeline

## WholeBookContextPipeline methods

`prepare_snapshot(...)` · `normalize_chapters(...)` · `build_chapter_units(...)` · `build_scene_units(...)` · `build_paragraph_units(...)` · `build_context_index(...)` · `build_module_context(...)` · `build_context_bundle(...)` · `validate_context_bundle(...)`

## Fact source

Completed Book Snapshot is the **sole** fact source. Do not read mutable live body as substitute. Temporary caches are allowed for on-demand reads but are never the fact source. Do not store a second full-novel copy in the database.

## Context Bundle bindings

`book_id`, `book_snapshot_id`, Snapshot content hash, chapter hashes, paragraph hashes, context schema/version, pipeline version, configuration fingerprint.

## Hard exclusions (Phase 2B)

No FTS5 · no vector DB · no Neo4j · no new database tables / migrations for context indexing.

## Stability

Chapter/paragraph order deterministic; stable paragraph IDs retained; whitespace-only formatting must not break semantic location.
