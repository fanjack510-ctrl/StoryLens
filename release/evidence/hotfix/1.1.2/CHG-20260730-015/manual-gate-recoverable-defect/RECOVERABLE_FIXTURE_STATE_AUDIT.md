# RECOVERABLE FIXTURE STATE AUDIT — CHG-20260730-015

Frozen at: 2026-07-30 (Manual Gate Fixture C failure)  
Failed URL: `http://127.0.0.1:1428/books/1?chapter=3&analysisRun=3&journeyRun=2&view=progress`  
HEAD: `f4560b19bc57d771e8a1baf0862b8bf1084a6347`  
Live DB (not reseeded): `%TEMP%\storylens-mg-chg015-rc4-failure\database\storylens-mg-chg015.db`  
Frozen copy: `./frozen-db/` + `./database/`

## 1. Target IDs

| Field | Value |
|-------|-------|
| analysis_run_id | **3** |
| journey_run_id (URL) | **2** |
| chapter_id | **3** |
| confirmed_revision_id | **3** |
| page selected Run | analysisRun=3, journeyRun=2, view=progress |

## 2. Analysis Run 3

| Field | Value |
|-------|-------|
| status | `succeeded` (scene pipeline) |
| workflow_state (DB column) | *(none — not a persisted column)* |
| effective_status (API) | `completed` ← derived via `latest_journey()` → Journey **5** |
| chapter_complete | `true` |
| scene_pipeline_complete | `true` |
| completed scene count | 3 / 3 |
| journey_run_id (API) | **5** (not 2) |
| journey_status (API) | `succeeded` |
| can_resume / journey_retryable | `false` |
| can_restart_as_new_task | `true` |
| raw_output.auto_journey_run_id | **5** |
| raw_output.unified_analysis_recover.resume_stage | `completed` |
| manual_recovery_attempts | 2 |

## 3. Journey Run 2 (URL target — still interrupted)

| Field | Value |
|-------|-------|
| status | `scene_profiles_partial` |
| current_stage | `reader_journey_scene_profiles` |
| root_error_code | `JOURNEY_INTERRUPTED` |
| retryable | `true` |
| result_status | `superseded` (set when Journey 5 was created) |
| completed_scene_count | **1 / 3** |
| journey result (summary) | **NO** (`has_chapter_summary=false`) |
| checkpoint / profiles | **YES** — 1× `SceneReaderJourneyProfile` for scene 7 |
| worker claim | **YES** — `failure_details.worker_claim` (`mg-chg015-worker`) |
| lease_expires_at | `2026-07-30T05:31:53+00:00` (expired) |
| interruption | `failure_details.interrupt.code=JOURNEY_INTERRUPTED`, `had_worker_claim=true` |
| recovery_safe (progress API) | `true` |
| can_resume (explicit field) | not a DB column; progress exposes `recovery_safe` + resume_preflight |

## 4. Journey Run 5 (contaminant — same analysis_run_id=3)

| Field | Value |
|-------|-------|
| status | `succeeded` |
| client_request_id | `auto-chapter-journey:3:rev:3` |
| created_at | ~`2026-07-30T06:23:58Z` (after Fixture C seed) |
| completed_scene_count | 3 / 3 |
| scene_revision_id | `NULL` (`legacy_revision_unresolved`) |
| journey result | **YES** |

## 5. UI copy sources (contradiction)

| On-screen text | Source |
|----------------|--------|
| **分析已暂停** | `UnifiedAnalysisRecoveryCard` default title when `!isFailed` (`UnifiedAnalysisRecoveryCard.tsx`) |
| **当前进度已保存，可以稍后继续** | same card default lead |
| **阅读旅程已完成** | Recovery plan check `reader_journey` with `user_label="阅读旅程已完成"` when `_journey_for_run` → latest Journey **5** (`analysis_recovery_center.py`) |
| **修复并继续** | Recovery plan `recommended_actions[].action=fix_and_continue` + card CTA |
| **请在右侧恢复面板重试** | No exact source string in repo. Closest family: right-rail `ChapterAnalysisProgressPanel` / `BoundaryReviewPanel` “请在本章右侧进度面板…” + Continue/recover routing that expects the rail recovery card while main pane already shows `UnifiedAnalysisRecoveryCard`. Treat as **recovery-rail dead-end copy / UX**, not a Fixture C interrupted StateView. |

## 6. Why the page mixes states

1. `GET /analysis-runs/3` uses `latest_journey()` → Journey **5** → `chapter_complete=true`, `journey_status=succeeded`.
2. URL `journeyRun=2` loads Journey 2 → `scene_profiles_partial` + `JOURNEY_INTERRUPTED`.
3. `mapChapterCompositionState(progress.run, journey.data)` sees live Journey 2 needs resume → `awaiting_reader_journey_start`.
4. `resolveJourneyPageState` treats `chapterComplete=true` as **completed** *before* interrupted, so `showJourneyInterrupted=false`.
5. `showJourneyAwaiting=true` → main pane renders **UnifiedAnalysisRecoveryCard**.
6. Recovery plan again uses latest Journey 5 → check “阅读旅程已完成” + **修复并继续**.

## 7. Classification

| Code | Applicable? |
|------|-------------|
| A FIXTURE_JOURNEY_ALREADY_COMPLETED | **NO** — Journey **2** is not succeeded |
| B FIXTURE_NOT_TRULY_INTERRUPTED | **NO** — claim + lease expiry + JOURNEY_INTERRUPTED present |
| C JOURNEY_COMPLETED_FLAG_FROM_WRONG_RUN | **YES** — completed flags from Journey **5** |
| D ANALYSIS_AND_JOURNEY_STATE_SPLIT | **YES** — AR3 completed vs JR2 interrupted |
| E RECOVERY_PANEL_READING_DIFFERENT_RUN | **YES** — recovery plan / parent payload use JR5 |
| F COMPLETED_JOURNEY_MAPPED_AS_RESUMABLE | **YES** — `resume_stage=completed` + `fix_and_continue` |
| G RESUME_ACTION_ROUTE_MISMATCH | **PARTIAL** — primary CTA becomes fix_and_continue / recover instead of same-journey Continue |
| H STALE_FRONTEND_STATE | **NO** — API + DB agree on the split; FE mirrors it |
| I OTHER | **YES** — `ensure_auto_reader_journey_row(..., scene_revision_id=)` created `auto-chapter-journey:3:rev:3` without reusing recoverable JR2; `find_recoverable_journey_run` default `contract_major="1"` skips contract `2.0` rows |

**Verdict:** Journey 2 itself is a **valid interrupted row**, but chapter 3 Fixture C is **contaminated** by Journey 5.  
**Product code defect:** YES (current-run / page-state / auto-journey reuse).  
**Fixture defect (for MG URL C):** YES (invalid as *legal single-run Recoverable Interrupted* after contamination).  

Do **not** rewrite Journey 2/5. Keep frozen evidence. Seed a **new** legal recoverable fixture on a fresh chapter after product fixes.

## 8. Legal Recoverable invariants (original Fixture C at failure)

| # | Invariant | Result |
|---|-----------|--------|
| 1 | analysis_run exists | PASS (3) |
| 2 | journey_run exists | PASS (2) |
| 3 | confirmed_revision exists | PASS (3) |
| 4 | Scene complete / checkpoint | PASS (scenes 3/3 + 1 profile) |
| 5 | journey not succeeded | PASS (JR2) / FAIL (parent uses JR5) |
| 6 | journey not cancelled | PASS |
| 7 | not terminal failed | PASS |
| 8 | interruption_reason present | PASS (failure_details.interrupt) |
| 9 | can_resume | PASS on JR2 progress (`recovery_safe`) / FAIL on AR3 (`journey_retryable=false`) |
| 10 | Continue same journey | FAIL (UI offers fix_and_continue / auto path → JR5 already exists) |
| Page copy legal | FAIL |

## 9. Evidence files

- `frozen-db/storylens-mg-chg015.db` (+ wal/shm)
- `database/` mirror
- `api.log` / `api.err.log` / `fe.log` / `fe.err.log`
- `api_snapshot_run3_journey2.json`
