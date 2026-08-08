# CHG-20260808-062 Evidence

## Root cause (reproduced)

HTTP STATUS: 422
BACKEND ERROR CODE: REQUEST_VALIDATION_ERROR (now REQUEST_SCHEMA_INVALID)
DETAIL: `consent_id` Input should be a valid integer / Field required

Frontend `createRun` sent `consent_id: null` and never created Consent;
product `/whole-book/consents` path is blocked when capability enabled.

Secondary product issue: recommended limits were hardcoded 200 / 500k / 100k,
below real Estimate (425 / 1.758M / 297k), and UI showed only generic 422 text.

## Fixes

1. Free create accepts inline limits and creates Consent when `consent_id` omitted.
2. Backend rejects limits below estimate with LIMIT_* / BUDGET_TOO_LOW codes.
3. Prepare recommended_limits derived from estimate with headroom.
4. Desktop pre-start gap check disables Start + suggested limits button.
5. Validation handler no longer says only「请求字段校验失败」。

## REAL PROVIDER CALLS

0 (targeted unit/service tests only; schema test is pure Pydantic).

## Final DeepSeek Small Acceptance

ROOT CAUSE: 旧 runtime Sidecar + Create consent schema mismatch
NEW SIDECAR runtime: verified (SHA256 6E049C483744ECCD69AEFF19904BF92797123B1BF19A77FE6AC20AC3DFB7C197)
SMALL REAL SAMPLE: 明朝那些事儿.txt（6章切片）
PROVIDER: deepseek
MODEL: deepseek-v4-flash
PRE-RUN ESTIMATED CALLS: 5
PRE-RUN COST: ¥0.0375–¥0.0447
REAL CALLS: 4
PROMPT TOKENS: 15201
CACHE HIT: 0
CACHE MISS: 15201
COMPLETION TOKENS: 1605
TOTAL TOKENS: 16806
ESTIMATED ACTUAL COST: ¥0.018411
FOUR MODULES: PASS
EVIDENCE: PASS
FAILED / RETRY / REPAIR: 0 / 0 / 0
DUPLICATES: 0
SECRET LEAK: ABSENT
