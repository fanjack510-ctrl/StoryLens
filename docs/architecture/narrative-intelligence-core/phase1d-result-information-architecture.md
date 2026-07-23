# Phase 1D-P Result Information Architecture

Frozen whole-book results navigation and cross-cutting result chrome.  
本阶段不开发正式结果页；只冻结 IA。

## Result navigation (10 sections)

| # | Nav label | Primary module keys |
|---|-----------|---------------------|
| 1 | 总览 | `book_overview` |
| 2 | 结构 | `structure_stages`, **`chapter_functions`** |
| 3 | 故事线 | `storylines` |
| 4 | 人物 | `characters`, **`character_arcs`** |
| 5 | 人物关系 | `relationships` |
| 6 | 钩子与回收 | `hooks_payoffs` |
| 7 | 因果与时间 | **`causal_chain`**, **`basic_timeline`** |
| 8 | 诊断 | `diagnostics` |
| 9 | Evidence 与冲突 | Evidence Drawer + Conflict Center |
| 10 | 叙事结构地图 | Structure Map projection |

Placement rules:

- `chapter_functions` → under **结构**
- `character_arcs` → under **人物**
- `basic_timeline` + `causal_chain` → under **因果与时间**

## Cross-cutting result chrome

Every result surface must support:

| Concern | Behavior |
|---------|----------|
| Module status | via Envelope `module_status` |
| Partial results | `partial=true`; progressive reveal |
| Stale | `stale` hint ≠ failed |
| Conflict | conflict tip ≠ failed |
| Evidence count | from Envelope / refs |
| Canonical / candidate | explicit switch; default candidate until confirmed |
| User confirm state | review summary |
| Lock state | from Phase 1B asset base |
| Source Run / Snapshot | bound on Envelope |
| 原文跳转 | via Evidence deep_link |

## Partial / stale / conflict / canonical-candidate

- **Partial**: module usable but incomplete; keep showing completed siblings.
- **Stale**: Snapshot / hash drift; not a hard failure.
- **Conflict**: needs Conflict Center; not auto-failed.
- **Canonical candidate**: model output defaults to candidate; confirm/lock via Phase 1B — frontend never writes `is_canonical` directly.

See [phase1d-result-envelope.md](./phase1d-result-envelope.md), [phase1d-module-result-contracts.md](./phase1d-module-result-contracts.md).
