# CHAPTER_HOOK_UI_AUDIT — CHG-20260729-005 (complete)

**Base HEAD:** `2e8ed1edaf7dc91933666f5e46f4b2bdb747407c`  
**Branch:** `fix/1.1.2-chapter-hook-simplification`  
**Dependency:** CHG-20260729-004 verified + integrated

## Ordinary page structure (final)

1. Page blurb（提出 / 回应 / 留下期待）
2. Four overview stats：本章提出 / 本章回应 / 继续保留 / 章末牵引
3. Simplified Scene 钩子变化图（提出疑问 / 加深悬念 / 给出回应 / 留到下章）
4. 1–3 important reader questions（提出 / 结果 / 最后变化）
5. Dedicated 章末牵引 block
6. Right panel：场景编号 · 场景角色 · 钩子洞察（1–2 句）
7. Developer mode only：bottom collapsed 技术详情

## Presentation modules

- `chapterHookSimplification.ts` — FE derive only
- `HookPayoffTimeline.tsx` — ordinary layout
- `JourneySceneDetailPanel.tsx` — ordinary insight; tech evidence under developer details

## Explicit non-goals confirmed

- Hook recognition / formula_v2 / other five lenses / persistence / tab rename：unchanged
- Unresolved is not framed as failure on ordinary UI
- Recovery rate / Hook ID / smoke-fake：absent from ordinary UI
