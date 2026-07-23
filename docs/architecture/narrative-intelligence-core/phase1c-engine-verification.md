# Phase 1C Agent G — Engine Verification

**Change:** CHG-20260723-022  
**Branch:** `feature/narrative-phase1c-engine`

## Commands (local, not full suite)

```powershell
$env:PYTHONPATH="apps/api"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
python -m pytest apps/api/tests/test_narrative_phase1c_engine.py -q --noconftest
python -m pytest apps/api/tests/test_narrative_phase1cp_contract.py -q --noconftest
python scripts/version_manager.py check
python scripts/change_registry.py check
git diff --check
```

## Coverage map

| # | Case | Status |
|---|------|--------|
| 1 | Registry register | covered |
| 2 | Duplicate engine_id | covered |
| 3 | Engine not found | covered |
| 4–5 | native / enhanced | covered |
| 6 | Unsupported mode | covered |
| 7–9 | Snapshot / run consistency | covered |
| 10 | Capability denied | covered |
| 11 | Unsupported module | covered |
| 12–14 | Stage plan order / deps / cycle | covered |
| 15–22 | Init / execute / checkpoint / pause / resume / interrupt / retry / cancel / no-rerun / token | covered |
| 23 | BudgetGuard deny | covered |
| 24–27 | Mock asset / relation / non-canonical / conflict | covered |
| 28 | health_check | covered |
| 29–31 | version_manager / change_registry / git diff --check | covered |

## Integration Issues

| ID | Summary |
|----|---------|
| II-ENGINE-001 | WholeBook ArtifactWriter lacks dedicated stage-typed artifact contract; adapter reuses `analysis_artifacts` without schema expansion. |
| II-ENGINE-002 | Frozen `WholeBookStageContext` has no `relation_writer` field; Agent G injects via `extra["relation_writer"]` pending contract additive review. |

## Explicit non-goals verified

- `PRODUCTION_DEFAULT_ENGINE_ID is None`
- Factory `production_mode=True` refuses Mock
- No `PRO_CAPABILITIES_SHIPPED` / endpoint flag changes
- No DB migration / VERSION bump
