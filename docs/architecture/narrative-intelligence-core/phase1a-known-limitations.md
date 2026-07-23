# Phase 1A Known Limitations

## Current leftovers

1. No public HTTP API for whole-book staged runs yet.
2. `SimulatedStageRunner` only — no model invocation.
3. Pattern Map is a frontend technical draft (DTO/Mock/prototype); not ORM, not routed, not Pro.
4. Evidence DTO includes `paragraphContentHash` but is not wired to live Evidence Hash APIs.
5. Legacy scene-pipeline statuses (`boundary_candidates_running`, etc.) remain free strings alongside `RunStatus`.
6. Revising migration 003 checksum means any pre-integration Agent A DB that recorded the old 003 checksum must be recreated or manually reconciled (acceptable: not released).

## Must confirm before Phase 1B

1. Freeze narrative entity / asset / relation table contracts.
2. Decide whether Pattern Map DTO becomes DB schema input as-is or needs another draft pass.
3. Confirm book-scope run persistence + resume UX product rules.
4. Confirm whether interrupted staged runs need reservation/budget handling beyond legacy release path.

## Explicitly not implemented

- `narrative_entities` / `narrative_assets` / `narrative_relations`
- Pattern persistence tables
- `WholeBookAnalysisEngine` / prompts / model calls
- Formal whole-book UI / Reader Journey / Scene / Hook algorithm changes
- FTS5 / Neo4j / vector DB
- VERSION bump / release / publish
