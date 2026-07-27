# Phase 1A — Run Stage Implementation (Agent B)

**Change:** CHG-20260723-013  
**Branch:** `feature/narrative-phase1a-runstage`

## Modules

| Module | Role |
|--------|------|
| `run_stage_repository.py` | Persist stages; enforce unique `(run_id, stage_key)`; transition matrix |
| `run_stage_service.py` | `initialize` / `transition` / `pause` / `resume` / `mark_interrupted` / `retry` |
| `SimulatedStageRunner` | **Test-only** loop helper (no model / asset / artifact generation) |
| Migration `20260723_005_analysis_run_stages` | Frozen Phase 1P DDL; owned by Agent B |

## Status machine

Implements frozen matrix in `apps/api/app/narrative_core/stage_transitions.py` only.

Statuses: `pending` | `running` | `paused` | `interrupted` | `completed` | `failed` | `skipped` | `cancelled`

Illegal transitions raise `NarrativeCoreError(INVALID_STAGE_TRANSITION)`.  
Retry of completed raises `COMPLETED_STAGE_CANNOT_RETRY`.

## API semantics

### initialize_run_stages

- Idempotent for identical key sequences.
- Stable `stage_order` = input index.
- Duplicate keys in input → `DUPLICATE_STAGE_KEY`.
- Re-init with different keys → `DUPLICATE_STAGE_KEY`.

### transition_stage

- Enforces matrix inside the session transaction (`flush` before commit at service layer).
- `started_at` set on first transition into `running`.
- `completed_at` set only for terminal statuses: `completed` / `skipped` / `cancelled`.
- `failed` / `paused` / `interrupted` clear or omit terminal `completed_at` (retryable / resumable).
- `token_input` / `token_output` / `cost` accumulate by default.
- `checkpoint_json` validated to include `schema` + `version`.
- `output_artifact_id` may be null.
- Errors never applied onto completed stages (completed is terminal).

### pause_run

- Running → paused.
- Pending stays pending; completed stays completed.
- Run status becomes `paused` (not `failed`).

### resume_run

- Paused → running.
- Interrupted → running (allowed by Contract matrix).
- Completed skipped.
- Failed **not** auto-resumed (must `retry_failed_stage`).

### mark_interrupted

- Only stages currently `running` → `interrupted`.
- Completed unchanged.
- Run marked `interrupted`, **not** permanent `failed`.
- Does **not** rewrite sidecar `mark_interrupted_runs_failed` (Integration Issue).

### retry_failed_stage

- `failed` → `running` only.
- Increments `attempt_count`.
- Completed cannot retry.

## Checkpoint contract

Default schema:

```json
{"schema":"narrative_run_stage_checkpoint","version":"1"}
```

Writers may add arbitrary fields; missing schema/version are filled; explicit empty schema/version rejected.

## Simulated runner (tests only)

Path covered: initialize → start → checkpoint → pause → resume → complete → fail → retry → interrupted.

Forbidden in this runner: model calls, whole-book analysis, real assets/artifacts, BackgroundTasks whole-book jobs.
