# ROOT_CAUSE — CHG-041 Round 6

## Category

`V2_FINALIZE_CROSS_JOURNEY_ARTIFACT_BLEED` + `VISUALIZATION_SCENE_PROFILE_COUNT_GATE`

## Primary defect

`apps/api/app/services/reader_journey_v2_execution.py` → `_load_v2_profiles_from_stubs`

Loads **all** `reader_journey_scene_profile_v2` artifacts for `analysis_run_id`, keyed by `scene_id`.

When revision rematerializes new Scene rows (ids 10–15) after a prior journey (ids 5–9), finalize merges **both** generations into journey run 2:

- `included_scene_ids = [10..15]` (correct)
- persisted profiles = 11 rows (5–9 + 10–15) (incorrect)
- `completed_scene_count = 11` (incorrect)

## Why refresh shows “尚未生成”

`build_reader_journey_visualization` loads current revision scenes (6) and requires `len(profiles) == len(scenes)`. Mismatch → `visualization = null`.

Frontend:

```ts
hasJourney = status === "succeeded" && visualization
```

Null viz → unavailable copy **当前章节尚未生成阅读旅程** despite durable succeeded run 2.

## Secondary defects

- DEFECT-041-17: First paint can succeed on stub-phase GET; not durable post-finalize.
- DEFECT-041-18: Explicit `journeyRun` GET works, but unusable viz looks like unused run.
- DEFECT-041-20: Historical/superseded path confused with “not generated” when viz/gate fails.

## Fix plan (no regen of forensic DB)

1. Scope V2 stub load to this journey’s stub/`included_scene_ids`.
2. V2 execute uses `load_journey_bound_scenes`.
3. Visualization + serialize filter profiles to journey-bound scene ids (repairs run 2 reload).
4. Explicit URL uses by-id GET; superseded still readable; missing run distinct copy.
5. Tests + HTTP E2E with API restart hash match on fresh DB.
