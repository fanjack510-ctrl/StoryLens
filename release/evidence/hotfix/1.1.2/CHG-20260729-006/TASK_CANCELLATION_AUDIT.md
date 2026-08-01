# TASK_CANCELLATION_AUDIT — CHG-20260729-006

**Public base HEAD:** `595545351972cacd010b149061f4f513d8a0bd71`  
**Branch:** `fix/1.1.2-task-cancellation`  
**Worktree:** `D:\Dstorylens-wt-hotfix-1.1.2-task-cancellation`

## Answers

| # | Topic | Finding |
|---|--------|---------|
| 1 | Status enums | **AnalysisRun.status** free string (`models.AnalysisRun`, default `queued`). Observed: `queued`, `running`, `preparing`, `analyzing`, `scene_analysis_running`, `awaiting_boundary_review`, `awaiting_provider_recovery`, `boundary_*`, `reader_journey_*`, `succeeded`, `failed*`, **`cancelled`**, `review_cancelled`, `aborted_by_limit`, `interrupted`. **ReaderJourneyRun.status** includes `queued`/`running`/`succeeded`/`failed`/`cancelled` (`schemas/reader_journey.py`, pipelines). No dedicated Task table — Task Center lists **AnalysisRun**. |
| 2 | Pause/resume | Budget / provider-recovery **pause** via statuses like `awaiting_provider_recovery`, `boundary_confirmed_budget_blocked`, `aborted_by_limit` (`BudgetPauseRecovery.tsx`, `budgetPauseDetect.ts`, `scene_analysis_provider_recovery.begin_provider_recovery_pause`). Not a generic user “pause analysis” for all stages. Whole-book lab has mock pause/resume/cancel (`wholeBook/runUx`) — out of v1.1.2 chapter scope. |
| 3 | Worker model | FastAPI **`BackgroundTasks`** → `execute_scene_pipeline` / `execute_reader_journey` (`api/v1/analysis.py`). In-process async, not separate OS process kill target. |
| 4 | Loops | Scene pipeline `_execute`: boundary **batches**, adjudication batches, scene-analysis batches (`scene_pipeline.py`). Journey: scene batches + chapter synthesis (`reader_journey_pipeline.py` / v2). Structured-output repair retries inside provider path. |
| 5 | Provider checkpoints | Budget claim / eligibility before gateway calls; structured_output invoke; post-parse validation. **No persisted user-cancel flag checked today.** |
| 6 | Persistence | Status mutations + `session.commit()` at stage boundaries; failures classify via `classify_pipeline_error`. Startup recovery `mark_interrupted_runs_failed` preserves terminal including `cancelled`. |
| 7 | Reservation | `budget_reservation.reserve_budget` / claim / `release_reservation` / `release_run_reservation` (idempotent when not `active`). |
| 8 | Scene result timing | Artifacts written per scene/batch inside `_execute` before run terminal status. |
| 9 | Partial → current success | Chapter complete requires journey succeeded (`chapter_analysis_completion`). Partial scenes do not auto-become chapter succeeded without journey. Risk if cancel races with success commit — needs lock. |
| 10 | API restart | `mark_interrupted_runs_failed` marks leftover worker-bound runs failed/interrupted; **must treat `cancellation_requested`/`stopping`/`cancelled` as non-resume** and finish cancel cleanup. |
| 11 | Task Center | `TasksPage.tsx` polls `GET /api/v1/analysis-runs`; status via `normalizeRunLifecycle` / `resolveTaskCenterPrimaryAction` (`runLifecycle.ts`). Filter already includes `cancelled`. **No Stop button yet.** |
| 12 | Existing cancel | Terminal token `cancelled` / `review_cancelled` known. Journey pipelines early-return if `cancelled`. **No AnalysisRun cancel API / cooperative request flag.** Whole-book cancel is separate lab path. |
| 13 | Safe to stop | `queued`, `running`, `preparing`, `analyzing`, `scene_analysis_*`, `reader_journey_*`, `boundary_candidates_running`, budget/provider pause statuses, retryable partials. Terminal: succeeded/failed*/cancelled/review_* — not stoppable. |
| 14 | Split risk | AnalysisRun vs ReaderJourneyRun can diverge; cancel must cascade to open journey runs and block `continue_chapter_after_scenes`. |
| 15 | Idempotency | `client_request_id` on AnalysisRun create (`analysis.py`). Cancel should accept optional `client_request_id` + `expected_status_version` for optimistic concurrency. |

## Root design decision

Introduce cooperative cancel on **AnalysisRun** (Task Center identity):

- statuses: `cancellation_requested` → `stopping` → `cancelled`
- persisted: `cancellation_requested_at`, `cancelled_at`, `cancellation_reason` (`user_requested`), `cancelled_by`, `status_version`
- API: `POST /api/v1/analysis-runs/{run_id}/cancel`
- Guard: `task_cancellation` service checked in scene + journey workers
- Do **not** kill processes; do **not** map cancelled → failed

## Migration

**YES** — minimal additive columns on `analysis_runs` via `migrate_phase_task_cancellation_v1` in `session.py`.

## Highest-risk files

- `apps/api/app/services/scene_pipeline.py`
- `apps/api/app/services/reader_journey_pipeline.py` / `reader_journey_v2_execution.py`
- `apps/api/app/services/chapter_analysis_completion.py`
- `apps/api/app/api/v1/analysis.py`
- `apps/desktop/src/pages/TasksPage.tsx`
- `apps/desktop/src/services/runLifecycle.ts`
