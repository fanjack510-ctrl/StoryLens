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
| Public | b62cd02ea40c13fcc2fcc39231f23f10c9d6297d |
| Private | `48072775773a09f4dc849096ba314e4fa0487c58` |

VERSION: `1.0.5`. Feature Flag default: `false` (Live used process env `PRO_NATIVE_OVERVIEW_ENABLED=true` only). Push / Tag / Release / verified: NO. Formal user DB: not used.

## Provider / Model

```text
Provider锛歛liyun_qwen_plus (keyring; key never logged)
Validation Model锛歲wen3.6-flash
Product Default Model锛歲wen3.7-plus
VALIDATION_MODEL_DIFFERS_FROM_PRODUCT_DEFAULT = YES
Reason锛歝lear CNY pricing + lower cost for controlled Live smoke/full short run
```

## Live results

| Phase | Status | Notes |
|-------|--------|-------|
| Live 1 | PASSED | 鐏璇曠偧锛? window锛沞ngine `private-native-overview-v1`锛泃ransport_calls=2 |
| Live 2 | PASSED | `short_book_live2_v1`锛? windows锛沜overage 100%锛泃ransport_calls=5 |
| Live 3 | NOT_RUN | No prepared legal medium-length fixture; G5 does not require Live 3; budget reserved |

First Live 1 attempt failed (`PROVIDER_OUTPUT_INVALID` 鈥?state_delta bare string ids). Fixed in Private parser/prompt (`4807277`), offline test added, then single Live 1 retry succeeded.

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

## Cost (from provider-cost-ledger.json 鈥?actuals only)

```text
Actual Cost锛毬?.0958008
Reserved Cost锛毬?.00
Cumulative Controlled锛毬?.0958008
Absolute Limit锛毬?0.00
Execution Limit锛毬?.00
Exceeded锛歂O
Live attempts in ledger锛? (includes failed-first Live1 analyze + successful retries/windows/synthesis)
```

## Commits

### Private

- `4807277` fix(engine): coerce state_delta string ids to objects for Live models

### Public

- `97067c2` feat(pro-runtime): add Live native overview transport and cost ledger
- (this docs commit) gate-2g5 evidence

## D-Audit

```text
D-Audit锛歅ASS

Live 1锛歅ASSED
Live 2锛歅ASSED
Live 3锛歂OT_RUN

Engine锛歅ASS (private-native-overview-v1; prompt native-overview-window-v1)
Transport锛歅ASS (AliyunNativeOverviewTransport; max_auto_retries=1)
Coverage锛歅ASS (100%)
Persistence锛歅ASS (new session + reopen DB)
Evidence锛歅ASS (index + deep link fields)
Cost锛歅ASS (pre-call ledger; actual 鈮?楼9)
Security锛歅ASS (temp DB; no key logging; no user novel)

P0锛氾紙鏃狅級
P1锛氾紙鏃犳湭鍏抽棴锛夆€?Validation model differs from product default (documented)
P2锛歁odelInvocation count may omit synthesis attempt row; ledger has full HTTP attempts

鍏佽 STEP 2.G5锛歒ES
```

## Result

```text
STEP 2.G5 = PASSED
```

## Next Step

```text
Read STEP-2.6-DETAILED.md
```
