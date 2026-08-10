# CHG-20260810-077 Evidence

## Root cause

Formal Free create (`POST /whole-book/free/create`) ran `execute_minimal_pipeline_v1` **synchronously inside the HTTP request before `db.commit()`**.

Symptoms:
- UI stuck on「创建中…」
- Task center (AnalysisRun list) showed no new task
- WholeBookRun not visible until (if ever) the long request finished

## Call estimate (542 ch / ~2.9M chars)

User limits `300 / 2.2M / 400k / ¥10` match **recommended limits for 244 calls**, not 2444.

Free minimal estimator dry-run:
- windows: 106
- calls: 244 = 106 extract + 2 synthesis + 68 CF batches + 68 repair reserve
- tokens/cost match the screenshot exactly

Likely display/read of **244** as **2444**.

Hierarchical V2 dry-run (not yet the Free create executor): 15 windows / 33 estimated calls / CONTEXT_SAFE=YES.

## Fixes

1. Defer pipeline via BackgroundTasks after commit
2. Clear Chinese LIMIT_* errors with numbers
3. Frontend create error alert + loading clears on failure
4. Call breakdown in prepare estimate

REAL PROVIDER CALLS during this change: 0
