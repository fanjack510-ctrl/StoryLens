# CHAPTER_HOOK_UI_AUDIT — CHG-20260729-005

**Base HEAD:** `2e8ed1edaf7dc91933666f5e46f4b2bdb747407c`  
**Branch:** `fix/1.1.2-chapter-hook-simplification`  
**Dependency:** CHG-20260729-004 verified + integrated

## Data chain

```
Scene profiles (hooks/payoffs/reader_question_*)
  → question_lifecycle (v2) / narrative_loops (viz-time)
  → hookResolutionModel + HookPayoffTimeline (current ordinary UI)
  → JourneySceneDetailPanel evidence
```

## Audit answers

| # | Topic | Finding |
|---|--------|---------|
| 1 | Hook title / reader question | `NarrativeLoopView.question` / `information_gap` / `hooks[].summary` / `question_lifecycle.question_text`; UI short via `shortPlainTitle` |
| 2 | Introduced scene | `open_from_scene` / `setup_scene` / first hook scene |
| 3 | Reinforced scene | `development_scenes[]` / `developments[]` (no single field) |
| 4 | Partial / full response | `payoffs[].type`, `answer_degree`, loop status `partially_resolved`/`resolved` |
| 5 | Still unanswered | loop `open` / `unresolved` main_status; last-scene `reader_question_out` |
| 6 | Chapter-end active | unresolved loops; `open_at_chapter_end` on chains (not shown in UI) |
| 7 | Current stats fields | 建立钩子 / 已回收 / 部分回收 / 未回收 (+ conflict) |
| 8 | Importance | Exists on chains/clusters/`strength`; **not shown** on hook page |
| 9 | Core-event link | **None** explicit |
| 10 | Legacy compat | Client synthesizes loops from lifecycle/chains when bundle missing; `resolveHookPayoffDataStatus` |

## Presentation plan (this CHG)

- New FE-only `chapterHookSimplification.ts`
- Replace ordinary HookPayoffTimeline overview/lanes/table with: 本章提出/回应/继续保留/章末牵引 + 1–3 重要读者问题 + Scene 四态短标签
- Keep tab name **钩子回收**; do not change hook algorithms or persisted facts
- Detail/evidence can still use existing resolution row lookup
