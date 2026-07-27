# Phase 1C Agent G — Stage Orchestrator

**Change:** CHG-20260723-022  
**Module:** `apps/api/app/narrative_core/services/whole_book_stage_orchestrator.py`

## Purpose

Test-level orchestrator verifying:

```
Request → validate → build plan → initialize AnalysisRunStages
→ execute current stage → checkpoint → complete → next
→ pause / resume / interrupted / retry / cancel
```

Uses Phase 1A `RunStageService` only — does not invent a second RunStage store.

## Guarantees

| Rule | Behavior |
|------|----------|
| Completed stages | Not re-executed (`skipped_rerun`) |
| Pause | Sets `PAUSED`; never `FAILED` |
| Interrupted | Resume via `resume_stage` / `resume_run` |
| Failed | Explicit `retry_failed_stage` then re-execute |
| Cancel | Orchestrator refuses further stages; token checked before/after work |
| Checkpoint | Always includes `schema` + `version` |
| Token / cost | Written onto the stage row on complete |
| Stage result key | Must match the executing stage key |
| Output IDs | Deduplicated |
| BudgetGuard deny | Raises `WHOLE_BOOK_BUDGET_DENIED` before Asset writes |

## Adapters

| Adapter | Delegates to |
|---------|--------------|
| SnapshotReaderAdapter | BookSnapshot metadata (no unbounded body) |
| NarrativeAssetWriterAdapter | Phase 1B `NarrativeAssetService.create_candidate_asset` |
| NarrativeRelationWriterAdapter | Phase 1B `NarrativeRelationServiceImpl.create_candidate_relation` |
| ArtifactWriterAdapter | Legacy `analysis_artifacts` (see II-ENGINE-001) |
| AnalysisConflictSinkAdapter | Phase 1B Conflict Sink |
| BudgetGuardAdapter / CancellationTokenImpl | In-memory test guards |

No ORM bypass; no confirm / correct / lock paths.
