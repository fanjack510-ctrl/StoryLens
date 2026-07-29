# CHG-20260729-006 verification notes

## Model

Cooperative cancel on AnalysisRun: `cancellation_requested` → `stopping` → `cancelled` (queued/paused finalize immediately).

## API

`POST /api/v1/analysis-runs/{run_id}/cancel`

## Migration

`migrate_phase_task_cancellation_v1` — columns: `status_version`, `cancellation_requested_at`, `cancelled_at`, `cancellation_reason`, `cancelled_by` (idempotent ALTER).

## Worker

Checkpoints via `raise_if_cancel_requested` / `try_finalize_if_cancel_requested` in scene pipeline, structured_output (pre-call + retry sleep), journey v2 batch loop, startup recovery finalizes cancel-in-progress.

## UI

Task Center **停止分析** + confirm dialog; labels **正在停止** / **已停止** (not failed); detail cancel section; **重新分析** navigates to chapter shell for new task.

## Boundaries honored

No process kill; no formal AppData DB; no VERSION/Build/Push/Merge; Real Provider = 0.
