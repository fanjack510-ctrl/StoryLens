# Phase 2A Backend Verification (Agent M)

## Test command

```bash
cd apps/api
PYTHONPATH=. python -m pytest tests/test_narrative_phase2a_mock_run_backend.py -q
```

(Used: `py -3.12` when system 3.11 `_ssl` DLL is broken.)

## Result

**27 passed** (targeted file only; full Pytest not run).

## Coverage map

| # | Case | Status |
|---|------|--------|
| 1 | Lab default disabled | pass |
| 2 | production env reject | pass |
| 3 | non-loopback | pass |
| 4 | no marker | pass |
| 5 | non-mock engine | pass |
| 6 | create success | pass |
| 7 | precheck fail no persist | pass |
| 8 | idempotency | pass |
| 9 | duplicate_of_run_id | pass |
| 10 | snapshot invalid | pass |
| 11 | module invalid | pass |
| 12 | active run conflict | pass |
| 13 | metadata schema/version | pass |
| 14 | task single instance | pass |
| 15–16 | executor start / next | pass |
| 17 | execute until blocked | pass |
| 18–19 | pause / resume | pass |
| 20 | cancel | pass |
| 21–22 | retry / completed no rerun | pass |
| 23–26 | artifact / candidates / no canonical | pass |
| 27 | budget denied | pass |
| 28–29 | Lab API DTO + non-mock reject | pass |
| 30 | formal run entry disabled | pass |
| 31 | no model / HTTP / production factory reject | pass |
| 32 | version_manager check | pass |
| 33 | change_registry check | pass |
| 34 | git diff --check | pass |

## Production gates verified

- `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`
- `WHOLE_BOOK_MOCK_LAB_ENABLED` default `false`
- `PRODUCTION_DEFAULT_ENGINE_ID is None`
- Production factory rejects Mock engine
