# DIMENSION_NODE_JUDGMENT_AUDIT — CHG-20260729-004

**Base HEAD:** `bbcd6d7ac925303247599c9869e11780e4a7ca20`  
**Branch:** `fix/1.1.2-journey-dimension-node-judgments`  
**Dependency:** CHG-20260729-003 integrated (MG PASS)

## Data chain

```
Journey Result → Scene Profile scores
  → build_reader_journey_visualization (+ CHG-003 enrich for composite only)
  → ReaderJourneyWorkspace / observationLenses
  → CanonicalJourneyChart nodes + tooltip + x-axis
  → JourneySceneDetailPanel dimension_insights
```

## Per-dimension score / fit (current)

| Lens | Score field | Fit today |
|------|-------------|-----------|
| 剧情推进 | `scores.plot_progress` | No dedicated fit field; diagnosis band may show 表现有效类文案 |
| 阅读张力 | `scores.reading_tension` | Same — no dedicated fit |
| 情绪强度 | arousal avg / emotional_investment | Same — valence arrows only on chart |
| 节奏速度 | `scores.pacing_speed` | `pacingFitLabel` → 合适/偏快/偏慢/无法判断 (+ optional `pacing_fit` score) |
| 综合阅读 | `reading_momentum` | `composite_role_fit` (CHG-003) — **out of scope** |
| 钩子回收 | hook/payoff | own lens — **out of scope** |

## Chart node labels today

- Composite: fit under node + short labels on x-axis + key nodes (CHG-003)
- Pacing: `pacingFitLabel` under node; pacing segment labels
- Emotion: valence ↑/↓ only
- Plot / tension: no dimension short judgment above nodes

## Shared component

All six lenses share `CanonicalJourneyChart`. CHG-003 presentation helpers are composite-specific; this CHG adds a parallel `dimensionNodeJudgments` module for the four target lenses without changing composite/hook_payoff.

## Compatibility

Missing judgments → `judgment_source=unavailable`; show fit only when resolvable; Tooltip fallback「当前节点暂无可靠判断」. No DB fields; presentation-only derive.

## Fit split risk

Diagnosis band (`primaryBandLabelForScene`) can diverge from role-band fit for non-composite lenses. This CHG forces chart under-node fit from dimension-specific resolvers (pacing: existing `pacingFitLabel`; others: role-band score fit 合适/偏弱/偏强/无法判断) and keeps judgment text separate.
