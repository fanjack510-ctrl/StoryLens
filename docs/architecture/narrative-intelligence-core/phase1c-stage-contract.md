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
- `WholeBookStageContext` — run/book/snapshot/mode/capability (no book text)
- `WholeBookStageResult` — status, write counts, metrics

Source: `apps/api/app/narrative_core/whole_book_stages.py`, `contracts/stage.py`.

Agent G owns stage plan execution tests beyond contract freeze.
