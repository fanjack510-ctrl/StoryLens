# Phase 1D-P Release Scope

Product delivery slices after Contract freeze. Phase 1D-P itself ships **docs + DTO/guards only**.

## Phase 2A — 运行壳 (Run shell)

Must include:

- Preflight
- Native / Enhanced mode
- Module selection
- Stage plan
- Create **Mock** Run (not production create gate flip)
- Progress UI
- Pause / Resume / Retry / Cancel
- Partial result status
- Capability gates

**Still no real model calls.**  
**Do not** implement all analysis modules in 2A.

## Phase 2B — 第一批真实结果模块

Priority:

- `book_overview`
- `structure_stages`
- `chapter_functions`
- `storylines`

## Phase 2C — 人物模块

- `characters`
- `character_arcs`
- `relationships`

## Phase 2D — 叙事机制模块

- `hooks_payoffs`
- `causal_chain`
- `basic_timeline`

## Phase 2E — 诊断与审阅

- `diagnostics`
- Evidence Drawer
- Conflict Center
- confirm / correct / lock

## Deferred (后续阶段)

- Narrative Structure Map 正式生成（beyond projection contract）
- 高级双时间线
- 世界规则
- 主题系统
- 跨书分析
- Story Lab
- Pattern tables / Neo4j / FTS5 / vector DB

## Phase 1D-P vs Phase 2A

| Item | 1D-P | 2A |
|------|------|-----|
| Product / DTO contracts | Yes | Consume |
| Mock-only UX prototypes | Ownership for J/K/L | Implement |
| Real models | No | No |
| `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=false` | Forbidden | Still gated unless explicit later change |
| Pattern tables | No | No |
