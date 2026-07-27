# Phase 1D-P Preflight Page Contract

Frontend page model + sections A–D. Preflight is **check-only**; never creates Run / Snapshot / Stage / Quota reserve.

## WholeBookPreflightPageModel

Required fields:

| Field | Notes |
|-------|-------|
| `book` | 书名、章节/段落/字数等摘要 |
| `snapshot` | 当前 Snapshot 与变更提示 |
| `capability` | CapabilityDecision 摘要 |
| `quota` | QuotaDecision 摘要 |
| `engine` | Engine 健康 / 可用性 |
| `analysis_mode` | `whole_book_native` \| `whole_book_enhanced` |
| `requested_modules` | 用户勾选 |
| `resolved_modules` | 勾选 + 自动补齐依赖后 |
| `stage_plan` | 信息性阶段计划（不执行） |
| `source_coverage` | Enhanced 覆盖率等 |
| `estimated_usage` | Token / 费用 / 耗时等级 |
| `blocking_reasons` | 阻断启动原因列表 |
| `warnings` | 非阻断警告 |
| `run_creation_enabled` | **default `false`** |
| `confirmation_required` | 用户确认门禁 |

## Section A — 书籍状态 (Book)

- 书名
- 章节数 / 段落数 / 字数
- 当前 Snapshot ID
- Snapshot 创建时间
- 正文是否发生变化
- 是否需要重新建立 Snapshot

## Section B — 分析模式 (Mode)

### `whole_book_native`

- 只要求完整正文 Snapshot
- 不要求已有章节分析
- 适用于首次分析

### `whole_book_enhanced`

- 完整正文仍是主来源
- 可读取已有 Scene、Reader Journey、章节分析资产
- 缺少增强资产时允许降级
- 必须显示增强覆盖率（`source_coverage`）

Native / Enhanced = **modes**，不是不同产品 SKU。

## Section C — 模块选择 (Modules)

First-batch module keys:

| Module Key |
|------------|
| `book_overview` |
| `structure_stages` |
| `chapter_functions` |
| `storylines` |
| `characters` |
| `character_arcs` |
| `relationships` |
| `hooks_payoffs` |
| `causal_chain` |
| `basic_timeline` |
| `diagnostics` |

## Module → Stage Dependency Table

Frozen dependency suggestions（不实现算法；UI 模块名 ≠ Engine Stage Key）:

| Module | Required stages (auto-fill) |
|--------|-----------------------------|
| `book_overview` | `build_fulltext_index` |
| `structure_stages` | `build_fulltext_index`, `resolve_entities`, `analyze_structure` |
| `chapter_functions` | `analyze_structure` |
| `storylines` | `resolve_entities`, `analyze_structure`, `analyze_storylines` |
| `characters` | `resolve_entities`, `analyze_characters` |
| `character_arcs` | `resolve_entities`, `analyze_characters`, `analyze_storylines` |
| `relationships` | `resolve_entities`, `analyze_characters`, `analyze_storylines` |
| `hooks_payoffs` | `analyze_structure`, `analyze_storylines`, `analyze_hooks` |
| `causal_chain` | `analyze_storylines`, `analyze_causality_timeline` |
| `basic_timeline` | `resolve_entities`, `analyze_causality_timeline` |
| `diagnostics` | `analyze_structure`, `analyze_storylines`, `analyze_characters`, `analyze_hooks`, `analyze_causality_timeline`, `verify_evidence` |

Rules:

1. 用户选择模块后自动补齐依赖阶段，并向用户说明。
2. 用户不能取消 required 依赖。
3. 模块与 Stage **禁止**一一硬绑定；一 Stage 可支撑多模块；一模块可依赖多 Stage。
4. 不得把 UI 模块名直接作为 Engine Stage Key。

## Section D — 分析条件 (Conditions)

展示并汇总：

- Capability / License / Quota / Engine / Snapshot
- 预计阶段 / 费用 / Token / 耗时等级
- 是否允许启动（`run_creation_enabled`）

## Hard defaults (Phase 1D-P)

| Flag | Value |
|------|-------|
| `run_creation_enabled` | `false` |
| Force-start button | **Forbidden** — 不得出现可绕过门禁的「强制启动」 |
| Preflight writes | None |

Backend preflight reference: Phase 1C `POST .../whole-book-runs/preflight`（只读）。  
See [phase1c-whole-book-preflight.md](./phase1c-whole-book-preflight.md).
