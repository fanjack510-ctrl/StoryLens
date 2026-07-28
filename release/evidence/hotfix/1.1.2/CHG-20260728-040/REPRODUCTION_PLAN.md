# REPRODUCTION_PLAN — CHG-20260728-040

Investigation-only. **No formal code changes. No real provider calls in this phase.**

## 10.1 Parser Fixture (offline)

Construct fixtures exercised against current `structured_output` / JSON helpers:

| Fixture | Expectation (v1.1.1 behavior) |
|---------|--------------------------------|
| Complete legal `BoundaryCandidateAdjudicationResult` JSON + `finish_reason=stop` | succeed |
| JSON truncated mid-string + `finish_reason=length` | `OutputTruncatedError` before/at truncate check |
| JSON truncated mid-array + `finish_reason=length` | `OUTPUT_TRUNCATED` |
| JSON truncated mid-object + `finish_reason=length` | `OUTPUT_TRUNCATED` |
| Complete-looking JSON but `finish_reason=length` | still `OUTPUT_TRUNCATED` (finish_reason wins) |
| Incomplete JSON + unknown finish_reason | JSON parse / schema path (`JSON_PARSE_FAILED` / schema) |

Deliverable later: pytest module under `apps/api/tests/` (implementation phase).

Status now: **NOT YET executed** (design only).

## 10.2 Fake Provider

Fake returns:

- truncated JSON body
- `finish_reason=length`
- partial usage (`output_tokens == requested`)
- reservation already created for run

Observe:

| Concern | Expected today |
|---------|----------------|
| Error type | `OUTPUT_TRUNCATED` → run `failed_structural` |
| Retry | truncation_retry × N with **same** max_tokens |
| Usage | rows in `model_invocations` with costs |
| Reservation | ends `released` |
| Task status | `failed_structural` |
| Scene progress | `0 / 0` if scenes not created |

Status now: design only.

## 10.3 Real Provider plan (DO NOT EXECUTE without separate approval)

| Freeze item | Value |
|-------------|-------|
| Sample | Desensitized chapter with ≥15 boundary candidates OR synthetic paragraphs matching incident scale (~6k adjudication input tokens) |
| Provider | `aliyun_qwen_plus` |
| Model | `qwen3.7-plus` |
| Max calls | ≤ 3 |
| Max tokens / call | observe product default (do not silently raise in prod until fix approved) |
| Max cost | ≤ 0.20 CNY |
| Auto retry | OFF at operator level; allow in-process truncation_retry as product does |
| Stop conditions | first non-length success OR 3 length failures OR cost cap |
| Use incident chapter | **NO** (PII/copyright); use redacted/synthetic substitute with similar candidate density |
| Desensitized text | required |

**REAL PROVIDER CALLS THIS PHASE: 0**
