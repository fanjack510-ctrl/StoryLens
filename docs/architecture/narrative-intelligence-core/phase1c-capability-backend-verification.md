# Phase 1C Capability Backend Verification

Change: `CHG-20260723-023`

## Commands

```powershell
cd D:\Dstorylens-wt-capability-backend
$env:PYTHONPATH="D:\Dstorylens-wt-capability-backend\apps\api"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

py -3.11 -m pytest apps/api/tests/test_narrative_phase1c_capability_backend.py -q --noconftest
py -3.11 -m pytest apps/api/tests/test_pro_license_local.py -q --noconftest
python scripts/version_manager.py check
python scripts/change_registry.py check
git diff --check
```

Notes:

- Prefer `--noconftest` on this agent machine when system Python 3.11 `_ssl` DLL is broken (FastAPI TestClient path).
- API cases exercise FastAPI-free payload builders (`capability_api_payloads.py`); router is a thin Depends wrapper.
- Do **not** run full pytest or release publish gates for this Change.

## Coverage map

| # | Case | Result |
|---|------|--------|
| 1 | Capability keys unique | pass |
| 2 | whole_book not shipped | pass |
| 3 | preview_visible ≠ usable | pass |
| 4 | License missing | pass |
| 5 | License invalid | pass |
| 6 | License expired | pass |
| 7 | Valid license (injected shipped meta) | pass |
| 8 | native mode | pass |
| 9 | enhanced mode | pass |
| 10 | unsupported mode | pass |
| 11 | legacy key mapping | pass |
| 12 | unknown legacy/feature key | pass |
| 13 | can_use_feature compat | pass |
| 14 | narrative_asset_library foundation ungated | pass |
| 15 | Quota none | pass |
| 16 | per_book | pass |
| 17 | per_day + reset_at | pass |
| 18 | concurrent_runs | pass |
| 19 | character_limit | pass |
| 20 | token_budget | pass |
| 21 | cost_budget | pass |
| 22 | reservation commit | pass |
| 23 | reservation release | pass |
| 24 | duplicate release idempotent | pass |
| 25 | GET capabilities payload | pass |
| 26 | GET capability payload | pass |
| 27 | unknown API key | pass |
| 28 | Run Guard default deny | pass |
| 29 | Guard failure no Run | pass |
| 30 | Guard failure no Engine | pass |
| 31–33 | version_manager / change_registry / git diff --check | see commit report |

Observed local run: **36 passed** (`test_narrative_phase1c_capability_backend.py`) + **10 passed** (`test_pro_license_local.py`).

## Public asset gate audit

Entity / Alias / Asset / Asset Version / Evidence / Relation / Conflict services contain no `can_use_feature` / `DefaultCapabilityService` / `require_capability` imports. Foundation storage remains usable without `whole_book_analysis` License.
