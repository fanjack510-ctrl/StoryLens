# EVIDENCE_E2E_AUDIT — CHG-20260803-045

Shared helper：`apps/desktop/src/services/wholeBookFreeEvidenceDeepLink.ts`  
规则：精确 chapter/paragraph/offsets；stale 抛错；无 fuzzy；无 evidence_map wrapper。

## Per module

| Module | Citation path | Exact offsets | No fuzzy / no map | Return state | Verdict |
|---|---|---|---|---|---|
| overview | claim evidence_ids → getEvidenceSource → reader | YES（helper） | YES | returnModule **未传**（仅 structure/CF） | **GAP**（返回模块保持） |
| characters_events | entity/event evidence → same | YES | YES | returnModule **未传** | **GAP** |
| structure | stage evidence；Vitest 覆盖 return structure | YES | YES | `returnModule=structure` | **PASS**（单测） |
| chapter_functions | panel evidence + restoreFunction/Status/Cursor | YES | YES | restore* query + returnModule | **PASS**（实现有；正式页 E2E PARTIAL） |

## Additional rules

| Rule | Status |
|---|---|
| citation 来自当前 Snapshot/Revision | PARTIAL — source state + paragraph hash；跨 revision 混用需强化测 |
| 禁止只开章节顶部 | PASS in helper（offsets required） |
| stale revision 不静默开错文 | PASS — UI 提示 + throw EVIDENCE_STALE |
| conflict 结果不混用 Evidence | PARTIAL — structure conflict UI；跨模块缺 |
| Reader 使用正确 chapter **id** | **GAP / must-fix** — 见下 |
| Drawer 禁止 fuzzy fallback | **INCONSISTENT** — 见下 |
| CF Evidence 返回保持筛选/cursor/详情 | **GAP** — restore* 写入后经 Entry 回链易丢；`restoreCursor` 未真正恢复分页 |

### Wave 1 must-fix（Desktop audit 确认）

1. **chapter_id vs chapter_index**  
   API `get_evidence_source` 返回 `chapter_id`（`source_chapter_id`）与 `chapter_index`（`chapter_order`）。  
   `WholeBookFreeProductPage` 使用 `source.chapter_index` 作为 reader `chapter` 参数，而 `BookRoutePage` 按 **chapter id** 解析 → id≠order 时**错章**。  
   Desktop `EvidenceSourceDetail` 类型需对齐并改用 `chapter_id`。

2. **Drawer `highlightQuote`**  
   offset 失败时 `indexOf(quote)` fuzzy，与 deep-link「禁止 fuzzy」合同不一致。

3. **CF restore\***  
   Evidence 往返须把 restoreFunction/Status/Cursor/Chapter 带进正式回链；`loadFirstPage` 不得清空未消费的 restoreCursor。

## Wave 1
- 修复 chapter_id 深链（P0）  
- 去掉或隔离 drawer fuzzy（P0）  
- overview / characters_events 传入 `returnModule`  
- CF Evidence round-trip 保持筛选/cursor/详情  
- 四模块正式页/Playwright（Fake；非仅 harness）  
- stale/conflict 负例

## Audit delta source
[Audit Free E2E desktop](da1b73d8-c797-4e73-a382-993852f31373)  
