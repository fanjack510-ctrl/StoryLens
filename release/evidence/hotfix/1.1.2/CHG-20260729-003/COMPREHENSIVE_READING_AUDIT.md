# COMPREHENSIVE_READING_AUDIT — CHG-20260729-003

**Status:** pre-implementation audit (no formula / phase / role algorithm change)  
**Base HEAD (hotfix/1.1.2 after CHG-002 integrate):** `9464b957e1538fe975115c972b0606b5a6d9dda2`  
**Branch:** `fix/1.1.2-comprehensive-reading-curve`  
**Workspace:** `D:\Dstorylens-wt-hotfix-1.1.2-comprehensive-reading-curve`  
**Dependency:** CHG-20260729-002 integrated (MG PASS)

## Data chain (current)

```
Reader Journey Result / Scene Profile (V2)
  → scores.reading_momentum  (= formula_v2 compute_reading_momentum)
  → build_reader_journey_visualization
      → attach_dimension_insights_to_node
         · overall_reading_score := reading_momentum (alias)
         · composite_role_fit := composite_role_fit_label(momentum, scene_role|role)
         · dimension_insights.{overall_reading,…}
  → API visualization payload
  → ReaderJourneyWorkspace
      · lens = composite → primaryKey reading_momentum
      · phase cards → phaseAverageForLens (mean of curve series in phase range)
  → CanonicalJourneyChart (single polyline) + JourneySceneDetailPanel
```

---

## 1. Per-scene composite score — real source

| Item | Value |
|------|-------|
| Canonical field | `scores.reading_momentum` |
| Presentation alias | `overall_reading_score` (set in `attach_dimension_insights_to_node`) |
| UI label | `综合阅读` (`observationLenses` / `lensMetricBinding`) |
| Chart line id | `reading_momentum` (`buildLensChartLines` for `composite`) |
| Formula | `compute_reading_momentum` in `apps/api/app/services/reader_journey_v2_derivation.py` |
| Formula version | `formula_v2` / `reader_journey_formulas_v2.json` — **must not change this CHG** |
| Inputs (unchanged) | `plot_progress`, `reading_tension`, optional `pacing_fit` / `hook_payoff_fit`, minus clarity/cognitive/redundancy penalties |
| Null fallback (UI) | `engagement.engagement_score` → `curiosity` (`nodeScores` / CHG-001 freeze) |

**Not equal to:** `reading_tension` alone, five-dimension simple average, or “作品质量总分”.

Evidence: `release/evidence/hotfix/1.1.2/CHG-20260729-001/COMPOSITE_SCORE_SOURCE.md`.

---

## 2. Phase card “综合阅读” aggregation

| Path | Behavior |
|------|----------|
| Primary | `phaseAverageForLens(viz, observationLens, phase)` — arithmetic mean of primary chart series values for ordinals in `[start_scene_ordinal, end_scene_ordinal]` (`lensMetricBinding.ts`) |
| Composite series | `reading_momentum` per scene via `buildLensChartLines` |
| Fallback | `phase.average_engagement` from visualization phase payload (`ReaderJourneyWorkspace` `phaseMetricAverages`) |
| Display | `formatLensPhaseScoreLabel` → e.g. `综合阅读 60` on `.journey-phase-avg` |

**Gap for CHG-003:** cards show **average only**; no stage conclusion / fit summary / strongest-weakest scene callout.

---

## 3. Fit labels: 合适 / 偏弱 / 偏强 / 无法判断

| Layer | Symbol | Allowed values |
|-------|--------|----------------|
| Backend attach | `composite_role_fit` via `composite_role_fit_label` | `合适` \| `偏弱` \| `偏强` \| `无法判断` |
| Frontend mirror | `compositeRoleFitLabel` in `observationLenses.ts` | same |
| Type | `JourneySceneNode.composite_role_fit` | same |

**Mechanism:** compare `reading_momentum` to `COMPOSITE_ROLE_BANDS[scene_role]` (setup/escalation/…/aftermath). Missing role → default band `[40,70]`.

**Pacing is separate:** `pacingFitLabel` → `合适` / `偏快` / `偏慢` / `无法判断` (not used for composite fit).

**Forbidden labels (already not used for composite fit):** 表现有效 / 未表现明显异常 / 表现明显异常 / 质量好 / 质量差.

**Diagnosis band (important):** `JourneyDiagnosisBand` when `observationLens === "composite"` **forces** `compositeRoleFitLabel(...)` and does **not** use `primaryBandLabelForScene` (which can emit「表现有效」等). Non-composite lenses still use diagnosis-band labels.

**Gap:** field name today is `composite_role_fit`, not `overall_reading_fit`. Spec wants explicit `overall_reading_score` + `overall_reading_fit` separation in data + UI.

**Risk:** when only `role` (`core`/`secondary`/`beat`) is present and `scene_role` (setup/climax/…) is missing, band lookup falls through to default `[40,70]` — fit may be coarse.

**UI gap:** composite chart nodes do **not** render fit under points (only pacing lens shows `pacingLabel` under nodes). Fit appears in diagnosis band + `JourneySceneDetailPanel`（「角色契合 …」, developer mode for score alias）.

---

## 4. Primary driver / primary drag fields

| Location | Present? |
|----------|----------|
| Schema / visualization types | **No** `primary_driver` / `primary_drag` / `主推动` / `主拖累` |
| Fake / persist | **No** dedicated fields |
| Dimension insights | Prose only in `dimension_insights.overall_reading` (generated or `derive_legacy_dimension_insights`) |
| Tooltip “主要原因” | Uses first scene-role tag title or `scene_value_summary` or lens caution — **not** structured driver/drag |

**CHG-003 must introduce presentation-layer derivation** (from existing five dimension scores + role), without changing `formula_v2`.

---

## 5. Node change reasons (升 / 降 / 转折)

| Mechanism | Status |
|-----------|--------|
| `buildSegmentMarkers` (`journeySegmentMarkers.ts`) | Heuristic labels on Δ`reading_momentum` ≥ 12 / ≤ −12: 冲突升级、钩子建立、推进停滞、张力下降… |
| Placement | Mid-plot SVG text (not stage-band titles) |
| Structured “为何相对上一场变化” | **No** dedicated field |
| Strongest / weakest chapter node callouts on chart | **No** (chapter summary peaks exist in payload but not as composite annotation layer) |

---

## 6. Chart “red / resistance” overlay semantics

| Layer | Source | Semantics |
|-------|--------|-----------|
| Risk top strip (post CHG-002) | `visualization.risk_intervals` → thin `#c47a6a` strip (was full-height `#f3ddd8@0.28`) | Reading-resistance / risk intervals — **not** a second score curve. V2 types include `momentum_decline` / `low_reading_momentum` / `unpaid_hook` / `high_dropoff_risk` (`base ≈ 100 - reading_momentum`); legacy may still emit `consecutive_no_payoff` |
| Secondary compare line | Compare mode / overlay → dashed purple `journey-secondary-line` | Optional second metric when user enters 对比分析 |
| Grid / selection | `--line` / accent selection | Axes + current scene |
| Valence arrows | `valenceDirection` | **Emotion lens only** — not composite |

User-visible “红色线条/色带” in MG screenshots was primarily the **risk wash** (now strip) and/or selection accents — **not** an extra composite formula line.

---

## 7. Y-axis 强 / 中 / 弱

Implemented only for `lensId === "composite"` in `CanonicalJourneyChart`:

- tick ≥ 75 → `强`
- tick ≤ 25 → `弱`
- tick === 50 → `中`
- other ticks keep numeric

Documented in `getLensExplanation("composite").y_axis_semantics` = `强 · 中 · 弱`.

---

## 8. Bottom Scene index — short label capacity

Current X-axis under each scene (`CanonicalJourneyChart` grid layer):

- `S{n}`
- 3px stage color mark (`sceneMarker`)
- optional `{阶段}起点` at stage start ordinals

Pacing lens additionally draws fit text under nodes (`合适`/`偏快`/`偏慢`).

**Capacity for CHG-003:** short fit tags (`合适`/`偏弱`/`偏强`) under composite nodes are feasible (same pattern as pacing). Driver/drag strings are too long for axis; belong in tooltip / right panel / rise-fall markers.

---

## 9. Legacy Journey compatibility

| Missing field | Behavior today |
|---------------|----------------|
| No `dimension_insights` | `resolve_scene_dimension_insights` → `derive_legacy_dimension_insights` (`insight_source=derived_legacy`) or `unavailable` |
| No `reading_momentum` | UI fallback engagement → curiosity; fit → `无法判断` if momentum null |
| No `overall_reading_score` | Alias filled at attach time when momentum/engagement known |
| No `composite_role_fit` | Computed at visualization attach / can recompute on FE via `compositeRoleFitLabel` |
| No driver/drag | N/A — must derive at read time without re-run / DB write |

**Constraint:** no Journey Run / Revision / persistence rewrite; presentation enrich only (same pattern as CHG-001).

---

## 10. Current top explanation (综合阅读)

Source: `readerJourneyLensExplanation.ts` → `READER_JOURNEY_LENS_EXPLANATIONS.composite.one_line_summary`:

> 综合阅读：综合判断每个场景对剧情理解、阅读期待、情绪体验和阅读流畅度的整体贡献。

**Spec target (CHG-003):**

> 综合阅读：综合判断每个场景对故事理解、阅读期待、情绪体验和阅读流畅度的整体贡献；分数高低需要结合场景任务和前后位置判断。

Also update `chart_title` currently `综合阅读动力` if still confusing vs frozen name `综合阅读`.

**Chrome / test debt to fix in this CHG:**

| Issue | Detail |
|-------|--------|
| Possible double title | `JourneyLensExplanationChrome` renders `<strong>{title}</strong>` plus `one_line_summary` that already starts with `综合阅读：` |
| Stale tests | `readerJourneyLensExplanation.test.tsx` and `readerJourneyTerminology.test.ts` still expect older copy (`线越高，读者继续阅读的动力…` / `不代表一定写得差`) |

---

## 11. Scene Role / Role Fit vs curve today

- Curve **height** = `reading_momentum` contribution (score).
- Fit **state** = band check vs `scene_role` → `composite_role_fit` (separate conceptually, weakly surfaced in UI).
- Scene list tags (开端/发展/收束) are **phase stage** colors from CHG-002, not composite fit.
- Narrative role tags (核心场景/钩子等) from `buildSceneRoleTags` — must not become stage-band titles (CHG-002).

---

## 12. Five other dimension scores on each node

Available on `node.scores` for driver/drag derivation (when present):

| Dimension | Typical field(s) |
|-----------|------------------|
| 剧情推进 | `plot_progress` |
| 阅读张力 | `reading_tension` |
| 情绪强度 | `arousal_start`/`arousal_end` (and/or emotional fields) |
| 钩子回收 | `hook`, `payoff` |
| 节奏速度 | `pacing_speed`, optional `pacing_fit` |

Plus penalty-related: clarity / cognitive_load / redundancy (when present).

---

## 13. Six `dimension_insights`

Keys: `overall_reading`, `plot_progression`, `reading_tension`, `emotional_intensity`, `hook_payoff`, `pacing_speed`.  
Right panel resolves via `resolveDimensionInsightText(node, lensId)` (CHG-001).

---

## 14. Right-panel composite insight today

- Title: 综合阅读洞察  
- Body: `dimension_insights.overall_reading`  
- Optional: `composite_role_fit` as “角色契合 …”  
- Developer `<details>` for technical fields  

**Gaps:** no structured 主推动 / 主拖累; no explicit score-vs-fit separation copy; phase cards lack conclusions.

---

## Root gaps mapped to CHG-003 goals

| Goal | Current | Gap |
|------|---------|-----|
| Score vs fit separation | score + `composite_role_fit` exist | Rename/alias to `overall_reading_fit`; surface fit on chart points |
| Why up/down | segment markers + vague tooltip reason | Structured driver/drag + clearer rise/fall/turn |
| Phase cards | average only | Stage conclusion + highlight shortfall/strength |
| Definition copy | near-spec one-liner | Add “结合场景任务和前后位置” |
| No five-curve stack | already single polyline | Keep |
| formula_v2 | intact | Keep intact |

---

## Absolute boundaries (reconfirmed)

- Do **not** modify `compute_reading_momentum` / `formula_v2`
- Do **not** modify other five dimension scores, phase algorithm, Scene Role algorithm
- Do **not** call real Provider / write formal DB / migrate
- Presentation + optional read-time derive only

## Spec note

Kickoff message truncated after introducing `overall_reading_score` / `overall_reading_fit` separation. Implementation of UI details beyond §1–§7 awaits full remaining sections if provided; audit above is sufficient to start presentation design for score/fit split and explanation copy.

## Cross-check

Deep path audit by [Audit comprehensive reading path](608005e0-ac42-4324-887e-999162630564) confirms the same score/fit/driver gaps; deltas above (diagnosis-band override, risk types, chrome/test debt) were merged into this document.
