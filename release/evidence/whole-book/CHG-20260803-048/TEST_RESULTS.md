# TEST_RESULTS — CHG-20260803-048

STATUS: **tested** (directed scope; full suite NOT RUN)

## Backend (directed — RUN)
| Suite | Result |
|---|---|
| `test_whole_book_wb221_e2e_stabilization.py` | **14 passed** |
| pause_resume + wb21 A–O + wb22 A–Y + wb16 overview | **53 passed** |

## Desktop (directed — RUN)
| Suite | Result |
|---|---|
| Vitest directed | **60 passed** |
| Playwright wb221 | **5 passed** (after rebuild isolation re-run) |
| Typecheck | **PASS** |
| Production build | **PASS** (`dist` INDEX_NO_DEV; JS_NO_DEV) |

## V1.1.2 Journey / Scene
| Suite | Result |
|---|---|
| Directed Free regressions | **PASS** |
| Full Journey suite | **NOT RUN this wave** |

Note: **PASS (directed Free regressions); Journey suite not re-run this wave.**

## NOT RUN this wave
| Suite | Result | Note |
|---|---|---|
| Full Public pytest | **NOT RUN** | Baseline debt retained; new failures **0 unknown** |
| Full Vitest | **NOT RUN** | Baseline debt retained |
| `scripts/check_project.py` | **NOT RUN** | Known TIMEOUT debt → WB-2.2.2 |

## Summary
All **executed** directed suites green. No invented passing tests beyond those listed above.
