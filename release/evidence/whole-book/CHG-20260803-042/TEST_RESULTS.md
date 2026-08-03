# TEST_RESULTS — CHG-20260803-042

STATUS: **tested** (not verified; pending MG-WB-2.2)

## Targeted
| Suite | Result |
|---|---|
| Private CF + first_four | 35 passed |
| Public WB22 A–Y + WB21 + WB16 + prepare | 60 passed |
| Vitest CF+Structure+Product | 47 passed |
| Vitest layout CHG-031 | 3 passed |
| Playwright WB22 | 6 passed |
| Playwright WB21 | 2 passed |
| Typecheck | PASS |
| check_project.py | TIMEOUT (60s) |

## Full suites (do not claim all green)
| Suite | Result | Baseline (prompt) | New WB-2.2 failures |
|---|---|---|---|
| Public pytest | 2114 passed / 48 failed / 6 errors / 54 skipped | 2095 / 44 | 0 in wb22_* |
| Vitest | 1376 passed / 30 failed | 1357 / 30 | 0 |

Scene `test_fake_provider_complete_pipeline` remains baseline-failed (assert 3==1 on PUBLIC BASE).
