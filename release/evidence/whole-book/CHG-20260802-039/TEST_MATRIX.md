# TEST_MATRIX — WB-2.2 Chapter Functions（freeze）

REAL PROVIDER CALLS default：**0**（Fake / fixtures only）.

## Backend / Contract

| ID | Case | Primary assertion |
|---|---|---|
| A | Normal per-chapter functions | ≥1 chapters；controlled labels；citations catalog-bound；API 200 |
| B | Multi-function chapter | primary + ≥1 secondary；no primary dup in secondary |
| C | primary=null legal | secondary may be non-empty；completed when otherwise valid |
| D | Controlled label reject | unknown label → repair once → fail-closed；no confirmed asset |
| E | Synonym normalize | rising→escalation etc. per freeze table；deterministic |
| F | Evidence missing | claim observed/inferred without citation → reject/repair/fail |
| G | Truncation then repair success | one contract repair；completed |
| H | Repair still illegal | `CHAPTER_FN_EMPTY_RESULT_AFTER_REPAIR` / contract fail；failed |
| I | Coverage insufficient binding | `coverage_scope=insufficient`；`chapters=[]`；completed |
| J | Capability true + empty chapters | illegal → fail after repair |
| K | Non-contiguous chapter orders | no invented chapters；orders unique |
| L | Empty / duplicate chapter ids | deterministic failure codes |
| M | Long book batching | batches of ≤8；all chapters covered |
| N | Pause then resume | stage continues；no loss of completed batches |
| O | Cancel then resume forbidden | canceled terminal |
| P | Duplicate resume | provider call count not doubled |
| Q | Confirmed no-overwrite | confirmed asset unchanged（WB-1.10） |
| R | Conflict version | new version / conflict；no silent replace |
| S | Native input audit | chapter_analysis=0；journey=0；aggregate=0 as SoT |
| T | Structure absent | chapter_functions still runs（no hard block） |
| U | Structure derived context only | no structure-only citations as Evidence |
| V | Lab V1 adapter | Lab route still works；Free route returns V2 only |
| W | Pro Insights isolation | Pro V1 payload never materializes Free assets |
| X | Pagination | cursor/limit；stable order by chapter_order |
| Y | Cost estimate includes unit | prepare/estimate lists chapter_functions when available |

## UI

| Case | Assertion |
|---|---|
| available | per-chapter primary/secondary render |
| multi-function | secondary visible；not collapsed into primary-only lie |
| aggregation display | optional group view；underlying per-chapter intact |
| insufficient | explicit empty/insufficient；not infinite spinner |
| failed / canceled / conflict / loading / absent | distinct UX |
| Evidence deep link | exact paragraph；return stays on chapter-functions |
| Filter by function | optional；must not invent labels |
| Pagination / virtual list | usable at ≥100 chapters |
| Refresh / re-enter | same result |
| 1366 / 1920 | CHG-031 layout；no horizontal scroll |
| storylines | still planned / 开发中 |
| Pro purchase UI | absent |

## Regression

| Suite | Included |
|---|---|
| v1.1.2 Scene | YES |
| v1.1.2 Journey | YES |
| Wave D overview + characters/events | YES |
| Prepare dual path + cost consent | YES |
| WB-2.1 structure stages | YES |
| Pause / Resume / Cancel | YES |
| CHG-031 layout | YES |

## Commands（post-implementation； not this Change）

```text
pytest apps/api/tests/test_whole_book_wb22_* -q
pytest apps/api/tests/test_chapter_functions_* -q
# Private
pytest tests/test_chapter_functions_* -q
cd apps/desktop && npm run typecheck && npm run test -- --run
# e2e wb22 config TBD at implementation
```
