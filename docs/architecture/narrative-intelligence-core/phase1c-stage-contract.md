# Phase 1C Stage Contract

Frozen stage catalog and runtime envelopes for WholeBook pipeline.

## Stage keys (ordered DAG)

1. `build_fulltext_index`
2. `resolve_entities` ← index
3. `analyze_structure` ← entities
4. `analyze_storylines` ← structure
5. `analyze_characters` ← entities
6. `analyze_hooks` ← structure, characters
7. `analyze_causality_timeline` ← storylines, hooks
8. `generate_diagnostics` ← causality
9. `verify_evidence` ← diagnostics
10. `persist_narrative_assets` ← verify

## Types

- `WholeBookStageDefinition` — catalog entry + `depends_on`
- `WholeBookStagePlan` — mode + ordered stages
- `WholeBookStageContext` — run/book/snapshot/mode/capability + first-class writers
  (`snapshot_reader`, `asset_writer`, `relation_writer`, `artifact_writer`,
  `conflict_sink`, `cancellation_token`, `budget_guard`); `extra` is non-core only
- `WholeBookStageResult` — status, write counts, metrics
- `WholeBookStageArtifactEnvelope` — frozen stage artifact payload
  (`artifact_type=whole_book_stage_result` on existing `analysis_artifacts`)

Source: `apps/api/app/narrative_core/whole_book_stages.py`, `contracts/stage.py`,
`contracts/whole_book_artifact.py`.

Integration (CHG-025) owns Stage Context / Artifact envelope corrections.
Agent G owns stage plan execution tests beyond contract freeze.
