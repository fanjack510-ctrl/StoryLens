# Phase 2B Context & Evidence Verification (Agent Q)

Change: `CHG-20260723-038`  
Branch: `feature/narrative-phase2b-context-evidence`  
Baseline: `f2ce37afd75e5773c4a30c0cf005603610ebac60`

## Owned implementation

| Path | Role |
|------|------|
| `whole_book_context_units.py` | TextRef, Unit builder |
| `whole_book_context_pipeline.py` | Pipeline, Index, Bundle, Planner, Native/Enhanced, Cache |
| `whole_book_evidence_pipeline.py` | Candidate builder, Coverage, Policy |
| `whole_book_evidence_validator.py` | Default validator |
| `test_narrative_phase2b_context_evidence.py` | Directed tests |

## Directed test command

```powershell
$env:PYTHONPATH="apps/api"
py -3.12 -m pytest apps/api/tests/test_narrative_phase2b_context_evidence.py -q --tb=short
```

Also: `python scripts/version_manager.py check` · `python scripts/change_registry.py check` · `git diff --check`

## Coverage map (task §十六)

Completed Snapshot · non-completed reject · Book mismatch · chapter/paragraph order · stable id · content hash · TextRef lazy · hash mismatch · chapter/scene/paragraph units · long grouping · no book-specific branch · Context Index · 100/500/1000 chapters · Bundle deterministic/hash/isolation · Hierarchical plan · context limit · budget downgrade · Native · Enhanced missing/stale · Evidence candidate deterministic · valid/invalid hash/offset/target · cross-book/snapshot · derived rejected · duplicate · coverage · critical unsupported · cache · privacy · no model · no DB index · version/change registry · git diff --check

## Explicit non-goals

No model calls · no prompts · no Provider · no four-module algorithms · no new tables/migrations · no FTS5/vector/Neo4j · no VERSION / release/unreleased mutation · no build/publish/push
