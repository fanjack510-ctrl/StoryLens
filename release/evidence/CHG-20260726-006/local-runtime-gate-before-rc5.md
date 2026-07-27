# Local Runtime Gate (before RC5) — CHG-20260726-006 / FIX-5 + FIX-5B

Date: 2026-07-26  
Result: **PASSED** (chapter Smoke Fake closed; RC5 build allowed once tree is clean)

## Heads / Version

| Item | Value |
|------|-------|
| Public HEAD (gate baseline) | `691acbc16474325a69128430cbfc911aed9d3add` |
| Private HEAD | `30d8dad8cd649e832999874f7bf16cc1661cf221` |
| Formal VERSION | `1.0.5` |
| Unique Vite Config | `apps/desktop/vite.config.ts` |
| Shadow Config Removed | YES |

## Local runtime

| Item | Value |
|------|-------|
| Frontend | `http://127.0.0.1:1421` |
| Backend | `http://127.0.0.1:18000` |
| Database Path | `data/fix5-local-gate/database/storylens.db` |
| Feature Flags | `PRO_NATIVE_OVERVIEW_ENABLED=true`, `STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE=1`, `STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1` |
| Transport | Native Fake + Chapter Fake (transport-only) |
| Runtime Fingerprint | `DEV Public 691acbc16474 · API 18000` |

## Gate checklist

- [x] Unique Vite config confirmed
- [x] Dev fingerprint = Public HEAD prefix
- [x] Top button real DOM correct (start → progress → result / reanalyze)
- [x] Task Center real request 200 + loading ends
- [x] Chapter Fake Create Run success (Run `#8`)
- [x] Chapter task in Task Center
- [x] Chapter Run completed
- [x] Top CTA → 查看分析结果
- [x] Chapter result page opens
- [x] Reader Journey result opens (contract 2.0)
- [x] Fake failure injection (Run `#9` `failed_provider` / `PROVIDER_TRANSPORT_ERROR`)
- [x] Retry after failure (Run `#10` succeeded)
- [x] Native Overview Fake still PASS
- [x] Page refresh recovery
- [x] Fake default OFF
- [x] Production does not silently use Fake
- [x] Real Provider calls = 0
- [x] P0 = 0 / P1 = 0

## Chapter evidence pointer

See `release/evidence/CHG-20260726-008/chapter-analysis-smoke-fake.md`.

## Result

```text
LOCAL RUNTIME GATE = PASSED
RC5 BUILD ALLOWED = YES
RC5 BUILD COUNT = (set after installer build)
Push / Tag / Release / verified = NO
```
