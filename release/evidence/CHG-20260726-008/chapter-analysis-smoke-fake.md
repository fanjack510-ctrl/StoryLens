# CHG-20260726-008 — Chapter Analysis Smoke Fake

Date: 2026-07-26  
Step: STEP-2.8-FIX-5B  
Result: **LOCAL RUNTIME GATE = PASSED** (RC5 build allowed after clean commits)

## Heads

| Item | Value |
|------|-------|
| Public HEAD (at gate) | `691acbc16474325a69128430cbfc911aed9d3add` |
| Private HEAD | `30d8dad8cd649e832999874f7bf16cc1661cf221` |
| Unique Vite Config | `apps/desktop/vite.config.ts` |
| Shadow Config Removed | YES (`vite.config.js` + `vite.config.d.ts` deleted) |
| Runtime Fingerprint | `DEV Public 691acbc16474 · API 18000` |

## Runtime

| Item | Value |
|------|-------|
| API Base | `http://127.0.0.1:18000` |
| Database | `data/fix5-local-gate/database/storylens.db` (isolated) |
| Chapter Book ID | `1` |
| Chapter ID (success) | `1` (第一章｜港口夜雨) |
| Paragraph Count | `3` |
| Create Run URL | `POST /api/v1/chapters/1/analysis-runs` |
| HTTP Status | `202` |
| Chapter Run ID | `8` |
| Initial State | `boundary_candidates_running` / UI progress CTA |
| Final State | `succeeded` (+ reader journey `succeeded`) |
| Provider (configured) | `aliyun_qwen_plus` / `qwen3.7-plus` |
| Transport | Chapter Smoke Fake (`STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1`) |
| Input Tokens | `32` (fake accounting) |
| Output Tokens | `64` (fake accounting) |
| Cost | `¥0.00` |
| Result Route | `/books/1?chapter=1&view=result&analysisRun=8` |
| Reader Journey Result | `/books/1?chapter=1&view=result&analysisRun=8&tab=reader-journey` (contract 2.0) |
| Task Center Status | PASS — run `#8` 已完成 visible; filter/refresh OK |
| Refresh Recovery | PASS |

## Failure injection

| Item | Value |
|------|-------|
| Env | `STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL=1` |
| Chapter ID | `2` |
| Run ID | `9` |
| Final State | `failed_provider` |
| Root Error | `PROVIDER_TRANSPORT_ERROR` |
| Top CTA | `重新分析` (`shell-reanalyze`) |
| Task Center | failed visible |
| Retry | Run `#10` created without FAIL → `succeeded`; CTA → `查看分析结果` |

## Native Overview regression

| Item | Value |
|------|-------|
| Native Fake | `STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE=1` |
| Result | PASS (`run_id=7` completed; tasks list includes overview + chapter) |
| Interference | Chapter Fake does not replace Native engine |

## Fake safety

| Item | Value |
|------|-------|
| Chapter Smoke Fake Default | OFF (unset / `0`) |
| Production Fake Fallback | DISALLOWED (`STORYLENS_APP_ENV=production` or frozen → rejected) |
| Real Provider Calls | `0` |
| Settings UI Fake toggle | none |

## Tests

- `pytest apps/api/tests/test_chapter_analysis_smoke_fake_transport.py` → 7 passed
- Live Book Workspace UI create → boundary confirm → scene → journey → results
- Task Center live `GET /api/v1/analysis-runs` 200
- Native Overview smoke create/poll completed

## P0 / P1 / P2

| Level | Count |
|-------|-------|
| P0 | 0 |
| P1 | 0 |
| P2 | 0 (local helper scripts under `data/runtime/` gitignored; gate DB not committed) |

## Result

```text
LOCAL RUNTIME GATE = PASSED
RC5 BUILD ALLOWED = YES
verified = NO
```
