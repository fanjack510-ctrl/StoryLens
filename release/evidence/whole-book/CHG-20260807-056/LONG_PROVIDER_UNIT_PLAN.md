# LONG_PROVIDER_UNIT_PLAN — CHG-20260807-056

DATE：2026-08-07

公式（产品 `whole_book_cost_estimate_v2`）：

`TOTAL = windows + overview(1) + structure(1) + CF_batches + CF_repair_reserve`

| Unit | Count |
|---|---|
| OVERVIEW UNITS | 1 |
| CHARACTERS EVENTS UNITS（estimated windows） | 162 |
| STRUCTURE UNITS | 1 |
| CHAPTER FUNCTION UNITS（batches） | 163 |
| REPAIR RESERVE | 163 |
| OTHER UNITS | 0 |
| **TOTAL ESTIMATED PROVIDER UNITS** | **490** |

加总校验：1+162+1+163+163+0 = **490**（与 `estimated_provider_call_count` 一致）。

| Case | Units |
|---|---|
| NORMAL（无 repair） | 327 |
| REPAIR CASE（含 reserve） | 490 |
| STRESS（normal ×2，每 unit 最多 1 retry） | 654 |
