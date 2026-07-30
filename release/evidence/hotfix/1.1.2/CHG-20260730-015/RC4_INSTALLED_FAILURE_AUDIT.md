# RC4_INSTALLED_FAILURE_AUDIT — CHG-20260730-015 / INC-20260730-007

## Verdict

STORYLENS 1.1.2-RC.4 MANUAL INSTALLED ACCEPTANCE：**FAILED**  
Release train：**rc4-installed-acceptance-failed**

This is **not** the CHG-013 confirm→starting interrupt race.  
Journey 5 was **claimed**, then immediately **failed** with `SCENE_ANALYSIS_INCOMPLETE` because confirm rematerialized scenes **68/69/70** and started V2 journey **before** scene-analysis artifacts for those IDs existed. UI then mixed **failed / interrupted / paused / analyze-complete / 0/3 running**.

## Failed task

| Field | Value |
|---|---|
| chapter_id | 1304 |
| analysis_run_id | 7 |
| journey_run_id | 5 |
| confirmed_revision_id | 13 |
| confirmed_scene_count | 3 |
| PUBLIC BASE HEAD | `678e0b1aff1ca827a48520474d2f8a3fc660dacc` |

## Millisecond timeline (UTC)

| # | Event | Time |
|---:|---|---|
| 1 | Analysis run 7 created / started | 2026-07-30 04:50:17.252 |
| 2 | Boundary provider calls 187–189 | 04:50:31 – 04:50:40 |
| 3 | Draft scenes 66–67 created | 04:51:50.507 |
| 4 | Scene analysis artifacts 66, 67 | 04:52:00.192 / 04:52:09.978 |
| 5 | **User confirm → rematerialize scenes 68–70** | **04:52:38.899 – .903** |
| 6 | Confirmed revision 13 bound; journey 5 created | 04:52:38.911 |
| 7 | startup intent | 04:52:38.916 |
| 8 | worker claim (`claimed=true`) | 04:52:38.935 |
| 9 | Scene-analysis stage for journey (require artifacts) | ~04:52:38.935 |
| 10 | First Provider request for journey profiles | **none** |
| 11–13 | Provider response / tokens / finish for journey | **n/a** |
| 14 | First exception `ValueError: SCENE_ANALYSIS_INCOMPLETE` | ~04:52:38.95 |
| 15 | journey status=`failed`, failed_stage=`pipeline` | 04:52:38.959 |
| 16 | interruption_reason | **none** (not interrupted in DB) |
| 17 | Scene artifacts 68/69/70 committed | 04:53:04 / 04:53:14 / 04:53:23 |
| 18 | analysis raw_output `scenes_completed_at` | 04:53:23.199 |
| 19–20 | UI poll sources | analysis_run.status=`succeeded` + journey.status=`failed` + journey counts 0/3 + FE composite lifecycle |

## Mandatory answers

| Question | Answer |
|---|---|
| Actual Provider call count (run 7) | **8** (all succeeded HTTP 200) |
| At least one request succeeded? | **YES** (boundary + later scene_analysis) |
| Why progress 0/3? | Journey `completed_scene_count` = journey **scene profiles**, not chapter scene-analysis; journey failed before any profile write |
| “分析场景完成” from? | `mark_scenes_complete_awaiting_journey` sets `analysis_runs.status=succeeded` on confirm; FE step “分析场景” treats run succeeded / pipeline marker as complete |
| “阅读旅程生成失败” from? | `journey.status=failed` + `effective_chapter_status→journey_failed` / FE failed labels |
| “阅读旅程已中断” from? | FE composite / gate maps recoverable/retryable failed journey to **interrupted** copy (`resolveSceneJourneyGate` / `compositeRunLifecycle`) despite DB `failed` |
| “分析已暂停” from? | FE pause mapping on budget/partial statuses overlapping same chapter panel |
| Different Runs? | Same analysis_run **7** + journey **5**; mixed **fields** of one run, not two successful runs |
| Old failed run as current? | Journey 5 is the current failed row for rev 13; older journeys are other chapters |
| Entered Journey Synthesis? | **NO** — failed at `require_completed_scene_analysis` before scene_profiles loop |
| Structured truncation? | **NO** evidence on journey path |
| Scene ID / revision mismatch? | **YES** — confirm rematerialized new IDs 68–70; artifacts still on 66–67 at fail time |
| Prompt/resource packaging error? | **NO** |
| Real Provider transport/model error? | **NO** for the failure itself (failure is completeness gate) |
| Usage but no Scene Result? | Scene analysis usage exists for 66–70; journey has **0** profile results |
| Stage completed before commit? | **YES** — confirm calls `mark_scenes_complete_awaiting_journey` **before** rematerialized scene artifacts exist |

## Root cause classes

Primary:

- **H. STAGE_MARKED_COMPLETE_BEFORE_COMMIT** — `mark_scenes_complete_awaiting_journey` on confirm
- **M. OTHER (`JOURNEY_START_BEFORE_REMATERIALIZED_SCENE_ARTIFACTS`)** — `ensure_auto_reader_journey_row(..., scene_revision_id=)` skips `is_scene_pipeline_complete`; V2 execution hard-fails `SCENE_ANALYSIS_INCOMPLETE`
- **I. MULTIPLE_RUN_STATE_SOURCES** — step bar / center / recovery panel derive conflicting user states
- **K. FAILURE_MAPPED_AS_INTERRUPTED** — DB `failed` shown as “已中断”

Not primary: Confirm-Start unclaimed→interrupted (CHG-013). Claim succeeded.

## Code anchors

- `confirm_scene_revision_and_start_journey_v1` → `mark_scenes_complete_awaiting_journey` then `execute_reader_journey`
- `ensure_auto_reader_journey_row` skips completeness when `scene_revision_id` set
- `reader_journey_v2_execution` → `require_completed_scene_analysis` → `SCENE_ANALYSIS_INCOMPLETE` → status `failed`
- FE: `compositeRunLifecycle.ts`, `resolveSceneJourneyGate.ts`, `mapAnalysisUiState.ts`

## Fix direction (authorized)

1. Do not mark scene stage complete / do not require journey start until confirmed-revision scene artifacts are valid (or requeue wait).
2. On `SCENE_ANALYSIS_INCOMPLETE` while scene analysis still pending: keep `starting`/`queued` wait — do not user-fail as journey synthesis failure.
3. Single current-run resolver for page / steps / recovery.
4. Product copy: real failure vs recoverable interrupt vs cancelled.
5. Tests + accident DB replay with Fake/Replay only.

## Safety

REAL PROVIDER CALLS THIS ROUND: 0  
FORMAL DATABASE WRITES: 0  
RC.4 installer preserved.
