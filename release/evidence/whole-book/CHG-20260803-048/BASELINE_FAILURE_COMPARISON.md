# BASELINE_FAILURE_COMPARISON — CHG-20260803-048

## Full suites
| Suite | This wave | New failures attributable to WB-2.2.1 |
|---|---|---|
| Public pytest (full) | **NOT RUN** | **0 unknown** |
| Vitest (full) | **NOT RUN** | **0 unknown** |
| `check_project.py` | **NOT RUN** | N/A (TIMEOUT debt → WB-2.2.2) |

## Directed scope (RUN)
| Suite | Result | WB-2.2.1 new failures |
|---|---|---|
| wb221 E2E stabilization | 14 passed | **0** |
| pause_resume + wb21 + wb22 + wb16 | 53 passed | **0** |
| Vitest directed | 60 passed | **0** |
| Playwright wb221 | 5 passed | **0** |

## Baseline debt retained
Pre-existing full-suite failures (registry/version/gate/env, readerJourney legacy, scene pipeline, check_project TIMEOUT) **not re-measured** this wave.

## Verdict
No new failures observed in **executed** tests. Full-suite delta **unknown** until WB-2.2.2 or explicit full rerun.
