# REGRESSION — CHG-20260728-040

## Public pytest

```
apps/api/tests/test_chg040_boundary_adjudication_truncation.py
apps/api/tests/test_phase_2b2.py
apps/api/tests/test_phase_2b8.py
apps/api/tests/test_scene_pipeline.py
```

Result: **46 passed**

## Private pytest

```
tests/test_scene_boundary_hotfix_chg040.py
```

Result: **1 passed**

## Vitest

```
apps/desktop/src/pages/TasksPage.chg040.test.ts
```

Result: **3 passed**

## git diff --check

PASS

## Typecheck

Desktop `tsc --noEmit`: PASS

## whole-book-v120

Not required / not run for this hotfix.
