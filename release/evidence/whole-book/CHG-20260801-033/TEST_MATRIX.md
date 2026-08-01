# TEST_MATRIX

## Backend

| ID | Case | Primary assertion |
|---|---|---|
| A | Normal multi-stage | ≥1 stages, citations valid, 200 structure |
| B | Non-three-act | Variable labels; no forced 3 stages |
| C | Variable stage count | 1..N accepted when legal |
| D | TP empty, stages valid | `turning_points=[]` + completed |
| E | Evidence missing | reject / repair / fail-closed; no confirmed asset |
| F | Truncation then repair success | one repair; completed |
| G | Repair still illegal | `STRUCTURE_EMPTY_RESULT_AFTER_REPAIR` or contract fail; failed |
| H | Chapter coverage insufficient | binding → insufficient empty completed |
| I | Non-contiguous chapter orders | fail-closed or legal local per policy; no invent |
| J | Empty / duplicate chapters | deterministic codes; no novel-specific hacks |
| K | Pause then resume | status transitions; units continue |
| L | Cancel then resume forbidden | cancelled terminal |
| M | Duplicate resume | provider calls not doubled |
| N | Confirmed no-overwrite | confirmed asset unchanged |
| O | Conflict version creation | new version / conflict row; no silent replace |

Reuse/extend: FakeHttp A–J + empty fixtures + empty_policy unit tests + free product API tests + WB-1.8/1.9/1.10 tests.

## UI

| Case | Assertion |
|---|---|
| available result | stages/TPs render |
| insufficient empty | explicit empty/insufficient UX; not spinner forever |
| failed | failure visible |
| canceled | canceled visible |
| conflict | conflict UX |
| loading | progress |
| Evidence deep link | exact paragraph locate |
| refresh / re-enter | same result |
| 1366 / 1920 | CHG-031 layout still holds |
| chapter_functions | still 开发中 / planned |
| Pro purchase UI | absent |

## Regression

| Suite | Included |
|---|---|
| v1.1.2 Scene | YES |
| v1.1.2 Journey | YES |
| Wave D prepare dual path | YES |
| Overview | YES |
| Characters / Events | YES |
| Pause / Resume / Cancel | YES |
| CHG-031 layout | YES |

REAL PROVIDER CALLS default **0**.
