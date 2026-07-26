# STEP 2.G5 Gate Evidence

**Change:** CHG-20260725-003
**Step:** STEP 2.5
**Gate:** STEP 2.G5
**Started:** 2026-07-26T09:02:00+08:00
**Finished:** 2026-07-26T09:12:00+08:00
**Verdict:** PASSED

## Integration HEADs (at gate close)

| Repo | HEAD |
|------|------|
| Public | see final commit after this evidence |
| Private | `48072775773a09f4dc849096ba314e4fa0487c58` |

VERSION: `1.0.5`. Feature Flag default: `false` (Live used process env `PRO_NATIVE_OVERVIEW_ENABLED=true` only). Push / Tag / Release / verified: NO. Formal user DB: not used.

## Provider / Model

```text
Provider：aliyun_qwen_plus (keyring; key never logged)
Validation Model：qwen3.6-flash
Product Default Model：qwen3.7-plus
VALIDATION_MODEL_DIFFERS_FROM_PRODUCT_DEFAULT = YES
Reason：clear CNY pricing + lower cost for controlled Live smoke/full short run
```

## Live results

| Phase | Status | Notes |
|-------|--------|-------|
| Live 1 | PASSED | 灯塔试炼；1 window；engine `private-native-overview-v1`；transport_calls=2 |
| Live 2 | PASSED | `short_book_live2_v1`；4 windows；coverage 100%；transport_calls=5 |
| Live 3 | NOT_RUN | No prepared legal medium-length fixture; G5 does not require Live 3; budget reserved |

First Live 1 attempt failed (`PROVIDER_OUTPUT_INVALID` — state_delta bare string ids). Fixed in Private parser/prompt (`4807277`), offline test added, then single Live 1 retry succeeded.

## Coverage / persistence

| Metric | Live 1 | Live 2 |
|--------|--------|--------|
| Paragraphs | 4 | 9 |
| Windows | 1 | 4 |
| Coverage % | 100 | 100 |
| Entities | 1 | 2 |
| Asset versions | 4 | 6 |
| Evidence index | 4 | 11 |
| State versions | 1 | 4 |
| New session read | YES | YES |
| API restart read (reopen SQLite) | YES | YES |
| Evidence deep link | YES | YES |
| Fixture engine used | NO | NO |

## Cost (from provider-cost-ledger.json — actuals only)

```text
Actual Cost：¥0.0958008
Reserved Cost：¥0.00
Cumulative Controlled：¥0.0958008
Absolute Limit：¥10.00
Execution Limit：¥9.00
Exceeded：NO
Live attempts in ledger：8 (includes failed-first Live1 analyze + successful retries/windows/synthesis)
```

## Commits

### Private

- `4807277` fix(engine): coerce state_delta string ids to objects for Live models

### Public

- `97067c2` feat(pro-runtime): add Live native overview transport and cost ledger
- (this docs commit) gate-2g5 evidence

## D-Audit

```text
D-Audit：PASS

Live 1：PASSED
Live 2：PASSED
Live 3：NOT_RUN

Engine：PASS (private-native-overview-v1; prompt native-overview-window-v1)
Transport：PASS (AliyunNativeOverviewTransport; max_auto_retries=1)
Coverage：PASS (100%)
Persistence：PASS (new session + reopen DB)
Evidence：PASS (index + deep link fields)
Cost：PASS (pre-call ledger; actual ≤ ¥9)
Security：PASS (temp DB; no key logging; no user novel)

P0：（无）
P1：（无未关闭）— Validation model differs from product default (documented)
P2：ModelInvocation count may omit synthesis attempt row; ledger has full HTTP attempts

允许 STEP 2.G5：YES
```

## Result

```text
STEP 2.G5 = PASSED
```

## Next Step

```text
Read STEP-2.6-DETAILED.md
```
