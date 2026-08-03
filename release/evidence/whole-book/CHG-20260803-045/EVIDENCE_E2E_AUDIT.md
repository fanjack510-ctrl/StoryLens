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

## Wave 1
- overview / characters_events 打开 reader 时传入 `returnModule`  
- 四模块 Evidence round-trip 正式页/Playwright（Fake）  
- stale/conflict 负例  
