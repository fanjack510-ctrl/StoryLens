# MEDIUM_COST_ESTIMATE — CHG-20260807-055

DATE：2026-08-07

## Gate

Import → Prepare → Cost Estimate **before** formal Provider calls.

## Book

| Field | Value |
|---|---|
| BOOK | 天才医生 |
| CHAPTER COUNT | 42 |
| CHARACTER COUNT | 129457 |
| SNAPSHOT | 1 |
| REVISION | `c047c09ac3abd08231dca4a3000f11893e0875deea846963866e3bf926497fb3` |
| ESTIMATE ID（formal run） | 2 |

## Estimate

| Unit | Count |
|---|---|
| OVERVIEW UNITS | 1 |
| CHARACTERS EVENTS UNITS（windows） | 8（estimate） |
| STRUCTURE UNITS | 1 |
| CHAPTER FUNCTIONS BATCHES | 6 |
| REPAIR RESERVE | 6 |
| TOTAL ESTIMATED PROVIDER UNITS | **22** |

Chapter Functions：`max_chapters_per_batch = 8`
`ceil(42 / 8) = 6` → **matches** planned CF batches.

## Cost

| Field | Value |
|---|---|
| pricing_status | available |
| estimated_cost_min_cny | 0.45832 |
| estimated_cost_max_cny | 0.674 |

## Decision

Cost Gate：**PASS** — proceed to Consent / Formal Create.
No abnormal order-of-magnitude estimate.
