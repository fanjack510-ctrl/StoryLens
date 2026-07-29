# VERIFICATION — CHG-20260729-011

## Registration

| Field | Value |
|-------|-------|
| Change ID | CHG-20260729-011 |
| Status | **tested** (not verified) |
| Commits | none (uncommitted worktree) |
| VERSION | unchanged (1.1.2) |
| Build / Installer | NO |
| Push / Release | NO |

## Automated checklist

| Check | Status | Evidence |
|-------|--------|----------|
| Pytest revision binding | PASS | `test_workflow_consistency_chg011.py` 6/6 |
| Vitest presentation / hooks / tasks | PASS | 78 tests, 8 files |
| HTTP E2E Fake Provider | PASS | `HTTP_E2E.json` |
| Real provider calls | 0 | HTTP E2E + seed scripts |
| Formal DB writes | 0 | Isolated `%TEMP%` DB only |
| Typecheck (full) | FAIL | See `TEST_RESULTS.json` |

## Manual gate checklist (pending human acceptance)

| # | Case | URL | Status |
|---|------|-----|--------|
| 1 | Revision 22→6 ordinary API/UI | REVISION 22-TO-6 | ☐ not verified |
| 2 | Interrupted 1/6, not running | INTERRUPTED | ☐ not verified |
| 3 | Awaiting confirmation 17→6 | AWAITING CONFIRMATION | ☐ not verified |
| 4 | Confirm → journey binds new revision | Fixture C flow | ☐ not verified |
| 5 | Running 2/6 progress | RUNNING | ☐ not verified |
| 6 | Succeeded unified shell | SUCCEEDED | ☐ not verified |
| 7 | Hook empty lens | HOOK EMPTY | ☐ not verified |
| 8 | Hook rich lens | vitest Fixture B | ☐ not verified |
| 9 | No「场景分析」ordinary tab | any chapter | ☐ not verified |
| 10 | Task Center scene ordinals not raw IDs | TASK CENTER | ☐ not verified |

## MG environment

- API + Frontend prepared and **left running** for acceptance (ports 18047 / 1426)
- Run `refresh_mg_after_api_boot.py` after any API restart before cases B / Running

## Next step

Human manual acceptance → update rows above → set change status to `verified` → attach MANUAL_GATE_PASS.md
