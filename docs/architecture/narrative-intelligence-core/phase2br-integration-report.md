# Phase 2B-R Integration Report

**Change:** CHG-20260723-044  
**Branch:** `integration/narrative-phase2br`  
**Worktrees:** public `D:\Dstorylens-wt-narrative-phase2br-integration`; private `D:\Dstorylens-private-engine-wt-integration`  
**VERSION:** 1.0.5 (unchanged)  
**Status cap:** `tested` (not `verified` — Live Smoke deferred)

## Merge order (cherry-pick; no agent-branch merge)

1. **Agent S** — `8d193e6` … `c37e302` (Private Lab, Bailian dry adapter, runtime foundation)
2. **Agent T** — `8845a20` … `6bc3421` (four-module public adapters + Phase1B sink)
3. **Private** — already linear at `10c19fc` (+ Integration composition follow-up on private branch)

No conflicts on public cherry-picks (S/T file ownership disjoint).

## Composition wiring

| Mode | Provider | Modules | Persistence |
|------|----------|---------|-------------|
| Default / tests | Fake gateway | `build_first_four_fake_runners` | `RecordingCandidatePersistenceSink` |
| Private Lab | `create_lab_provider_gateway(dry_run=True)` | `build_private_module_runner_adapters` over `build_first_four_private_runners` when package importable | `Phase1BCandidatePersistenceSink` when session+book_id |

Factory: `create_private_whole_book_analysis_runtime` / `create_lab_private_whole_book_analysis_runtime` in `private_whole_book_analysis_runtime.py`.  
Private Lab router mount remains `development|test` + `WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED` (default false) in `main.py`.

## Production isolation (unchanged)

- `PRO_CAPABILITIES_SHIPPED=false`
- `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=True`
- `PRODUCTION_DEFAULT_ENGINE_ID=None`
- `WHOLE_BOOK_MOCK_LAB_ENABLED=False`
- `WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED=False` (default)
- No new migrations / VERSION / formal `POST /books/{id}/whole-book-runs`

## Tests

- `apps/api/tests/test_narrative_phase2br_integration.py` (directed)
- Retained: `test_narrative_phase2br_private_runtime.py`, `test_narrative_phase2br_real_modules.py`
- `scripts/check_project.py` + registry/capability/diff checks

See also: [phase2br-known-limitations.md](./phase2br-known-limitations.md), [phase2br-production-isolation-verification.md](./phase2br-production-isolation-verification.md).
