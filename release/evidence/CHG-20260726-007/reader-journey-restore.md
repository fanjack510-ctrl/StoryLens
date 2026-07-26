# CHG-20260726-006 / CHG-20260726-007 — RC3 blockers fix evidence (FIX-3)

## RC3 USER ACCEPTANCE

**BLOCKED** (must not mark RC3 as passed)

## Root causes

### Native Overview start stuck on「启动中…」

**Class: F** (Create API synchronized full-book execution inside HTTP) + **H** risk mitigated.

`NativeOverviewService.create_run` previously called `execute_run` inline before returning. On a 1299-chapter / 2046-window book the HTTP request never returned, so React Query `isPending` stayed true → permanent「启动中…」. SQLite write lock during that sync also starved Task Center.

**Fix:** HTTP create uses `defer_execution=True` + `BackgroundTasks` (`execute_native_overview_run_background`). Create returns `run_id` + `pending` immediately. Frontend races create with 15s timeout, resets loading on error, navigates on `run_id`, shows「查看任务」for active runs, reuses `client_request_id` for idempotent retry.

### Task Center stuck on「正在载入…」

**Primary:** SQLite lock from sync Native create (same F).

**Secondary:** heavy `serialize_run` for whole-book runs; book filter missed book-subject runs; timeout collapsed.

**Fix:** slim serialize path for `whole_book_overview` / `subject_type=book`; list filter includes book subject / `book_id`; frontend list race timeout (`TASK_LIST_TIMEOUT`); TasksPage maps overview rows to Native Progress route; ErrorState keeps business codes.

### Free Reader Journey entry missing

**Class:** toolbar crowded by Native Overview + Chapter Aggregation; no explicit Free journey CTA when WorkspaceViewSwitcher is hidden (no `analysisRun` in URL).

**Fix (CHG-007):** `ReaderJourneyEntry` —「分析读者旅程」/「查看读者旅程」; also in「更多」; keeps「开始分析」, Native Overview, Chapter Aggregation Pro distinct. Deep link `/analysis-runs/:id/results?tab=reader-journey` preserved.

## Residual Run check (RC3 long book)

This FIX-3 session did **not** call real Providers and did **not** re-start the 1299-chapter book.

If a Run was created during RC3 manual acceptance on the user's machine, stop it only via Stop/Cancel API — do not delete DB rows or forge Completed. Live cost during this fix: **¥0.00**.

## Tests (no live Provider)

- pytest native overview walking / free / runtime / step23: **36 passed**
- vitest proNativeOverview + BookRoute + ReaderJourneyEntry + taskCenterErrors + TasksPage: directed suites passed
- `npx tsc --noEmit`: pass
- `git diff --check`: clean

## Constraints preserved

- Database schema / migrations: unchanged
- Native Contract: unchanged
- Private Engine: unchanged
- Formal VERSION: **1.0.5**
- No Push / Tag / Release / verified
