# STAGE_COLOR_AUDIT — CHG-20260729-002

**Public base HEAD (40-char):** `017d9cc26d5dd510aff8f251ddb22d083af382f3`  
**Branch:** `fix/1.1.2-reader-journey-stage-colors`  
**Workspace:** `D:\Dstorylens-wt-hotfix-1.1.2-reader-journey-stage-colors`  
**Scope:** presentation-only (no stage algorithm / score / insight changes)

## Data chain

```
Journey Result.visualization.phases[]
  → phase cards (ReaderJourneyWorkspace)
  → scene_nodes[].phase_ordinal
  → CanonicalJourneyChart phase_background rects
  → StructuredChapterTextPane left rail
```

## 1. Phase card data source

- `visualization.phases[]` with `ordinal`, `title`, `start_scene_ordinal`, `end_scene_ordinal`, `average_engagement`, `summary`
- Rendered in `ReaderJourneyWorkspace.tsx` (`journey-phase-strip`)
- Color today: `PHASE_BAND_COLORS[index % length]` via CSS var `--phase-band-color`

## 2. Scene stage ownership field

- Primary: `JourneySceneNode.phase_ordinal` (nullable)
- Fallback for display: match `phases[]` ranges by `start_scene_ordinal`…`end_scene_ordinal`
- Structured text uses `node.phase_ordinal` for rail color and “阶段{N}” label

## 3. Phase range representation

- **Not** Scene ID ranges for bands today
- Backend/UI use **scene ordinal** start/end on each phase
- Chart currently: `xFor(start) - 8` … `xFor(end) + 8` (fixed pixel pad, not midpoints)

## 4. Color definition file

- `apps/desktop/src/components/readerJourney/journeyVisualTokens.ts`
- Current: `PHASE_BAND_COLORS = ["#e8ede9", "#f0ebe3", "#e6ebf0", "#ede8e6"]`
- Opacity: `PHASE_BAND_OPACITY` in `journeyVisualizationConfig.ts` (idle 0.18 / active 0.32)
- Cards also mix via `readerJourney.css` `color-mix(... var(--phase-band-color) 28% ...)`

## 5. Six dimensions share one chart component?

- **Numeric lenses:** yes — `CanonicalJourneyChart` (综合阅读 / 剧情推进 / 阅读张力 / 情绪强度 / 节奏速度)
- **钩子回收:** `HookPayoffTimeline` (no phase band rects today)
- Phase cards sit above both; stage ownership is lens-agnostic

## 6. Current chart background partitioning

- Layer `phase_background`: one `<rect>` per `visualization.phases` entry
- Color by **array index**, not semantic 开端/发展/收束 key
- Dividers: dashed vertical line at each phase `start_scene_ordinal`
- **No** stage title text inside chart bands
- **Equal-third risk:** not used; widths follow phase start/end ordinals — but pad ±8px is not midpoint geometry

## 7. Legacy / missing phase fallback

- Empty `phases[]`: no band rects (plain chart) — safe
- Missing `phase_ordinal` on node: structured rail falls back to `phaseIndex = 0` (first color) — **incorrect guess**; CHG-002 must use neutral / 阶段未判定 instead
- Historical runs with phases but no node.phase_ordinal: can map from phase ranges at presentation time without mutating stored results

## Gaps for CHG-20260729-002

1. No semantic opening/development/closing tokens — index-based colors can drift if phase order differs
2. Band edges not midpoint-based
3. Contiguous same-title intervals not re-aggregated if non-monotonic history appears
4. No chart stage labels; X-axis lacks stage cue
5. Left list shows “阶段{N}” not 开端/发展/收束 label + shared token
6. Hook-payoff timeline lacks shared stage bands (should reuse same helper if feasible without algorithm change)

## Must not change

- Phase partition algorithm / scene membership
- Dimension names, scores, insights, persistence
