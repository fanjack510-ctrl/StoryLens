# L3_REAL_PROVIDER_TEST_PLAN — CHG-20260728-040

## Freeze (authorized 2026-07-28)

| Item | Value |
|------|-------|
| Sample | Synthetic Chinese paragraphs producing 20 boundary candidates (not user novel) |
| Provider | `aliyun_qwen_plus` |
| Model | `qwen3.7-plus` |
| Max logical calls | 4 |
| Max actual calls | 6 |
| Max input tokens | 40000 |
| Max output tokens | 24000 |
| Per-request output hard cap | 4000 |
| Max cost | ¥5 |
| Formal DB writes | 0 |
| BUILD / MERGE / PUSH | NO |

## Execution

| Item | Value |
|------|-------|
| Authorized | YES (`STORYLENS_L3_CHG040_AUTHORIZED=1`) |
| Harness | `scripts/l3_chg040_boundary_adjudication_real.py` |
| Result | `L3_REAL_PROVIDER_RESULT.json` |
| Outcome | **PASS** |

## Observed

- 20 candidates → **2** batches
- Initial output limit **1792** (not 768) per batch
- Actual HTTP calls: **2** (both `finish_reason=stop`; truncation retry not needed this run)
- Candidates covered: **20** exact
- Estimated cost: **¥0.02787**
- Temp SQLite deleted; formal AppData writes: **0**

Truncation adaptive increase remains covered by Fake fixtures; this L3 run validated live batching + budget policy + full coverage.
