# FIX PLAN — parallel Agents (NOT STARTED)

Parent: CHG-20260803-049 / WB-2.2.2. Implementation **not authorized** until user says so.

## Parallelism
**2 Agents** (ownership split; Integration merges + re-gates).

---

## Agent 1 — Public / Release Tooling / Registry / Version / Migration / Backend tests

### Scope
- T1–T5 tooling gates
- P1 scene progress product fix (backend/API)
- O1–O6 obsolete backend tests (+ U* backend investigations)
- Register missing commits / repair change registry records for 1.2.0 integration line
- Align `release/baseline.json` + `release/unreleased.json` with VERSION 1.2.0 policy (no silent VERSION downgrade)

### Needs product code?
| Item | Product? | Test? | Registry/docs? |
|---|---|---|---|
| P1 scene progress_total | **YES** (`apps/api` scene pipeline / progress fields) | update assert only if contract intentionally changed (unlikely) | no |
| T1 version baseline/unreleased | no | update obsolete 1.0.5 tests (O1) | **YES** release JSON |
| T2/T3 change_registry / check_project | no | registry-invoking tests may flip | **YES** `release/**` change records + scripts only if rule bug proven |
| T4/T5 collection ImportErrors | no | **YES** fix pytest_plugins / imports under `apps/api/tests` | no |
| O2 migration length | no (order already 16) | **YES** | maybe docs |
| O3 capability/gate locks | only if product incorrectly gated | **YES** mostly | registry if capability metadata recorded |
| O4 RJ wiring mocks | only if real model path broken | **YES** fixtures | no |
| U1–U5 | investigate first; product only if proven | likely | maybe |

### File ownership (Agent 1)
- `apps/api/**` (product + tests) except desktop
- `scripts/change_registry.py`, `scripts/version_manager.py`, `scripts/check_project.py` (**read/diagnose**; modify only if tooling bug — prefer registry data fixes)
- `release/baseline.json`, `release/unreleased.json`, `release/changes/**` (or project’s change record paths)
- `docs/whole-book/EXECUTION_REGISTRY.json` (WB-2.2.2 / CHG-049 notes only as needed)
- Evidence under `release/evidence/whole-book/CHG-20260803-049/` backend sections

### Agent 1 tests to drive green
- Directed: `test_scene_pipeline.py::test_fake_provider_complete_pipeline`
- All currently failing Public tests owned above + zero collection errors on native_overview / http_replay
- `python scripts/version_manager.py check`
- `python scripts/change_registry.py check`
- `python scripts/check_project.py`
- Public full pytest once at Integration (not looped in agent)

### Formal exceptions Agent 1 may propose
- Private-lab live suites (U1) if proven out-of-Free-1.2.0 ship scope after investigation write-up
- Not: T1/T2/T3 (must fix for release gate)

---

## Agent 2 — Desktop / Vitest / readerJourney / Production build checks

### Scope
- P2 CHG-041 navigation mapping (desktop)
- O7/O8 obsolete Vitest updates
- Confirm production build still isolates `/dev/*` (no Sidecar/installer)
- Do **not** expand into Reader offset highlight / DEV fuzzy (X1/X2) unless authorized as exceptions only

### Needs product code?
| Item | Product? | Test? | Registry/docs? |
|---|---|---|---|
| P2 scene-boundary-review → scene tab | **YES** if product routing wrong; else test | update test if CHG-041 contract intentionally maps elsewhere | no |
| O7 readerJourney Vitest locks | only if MG-verified UI missing required affordances | **YES** majority | no |
| O8 recovery card / runtime capabilities / autoDiscover | case-by-case; prefer test update when MG already accepted UI | **YES** | no |
| X1/X2 deferred polish | **NO** this wave | no | exception notes |

### File ownership (Agent 2)
- `apps/desktop/src/**`
- `apps/desktop` Vitest / Playwright configs as needed for test fixes only
- Desktop evidence under CHG-049
- **Forbidden**: Sidecar, installer scripts, formal AppData, real Provider

### Agent 2 tests to drive green
- Full Vitest once at end of agent work (or Integration)
- Directed files listed in `DESKTOP_FULL_VITEST.txt` FAIL set
- `npm run typecheck` (or project equivalent)
- `npm run build` production + INDEX_NO_DEV / JS_NO_DEV spot check

### Formal exceptions Agent 2 may propose
- X1 Reader offset highlight
- X2 DEV diagnostics fuzzy cleanup
- Individual readerJourney cosmetic asserts proven superseded by verified Free UI (must cite MG / CHG-048 evidence)

---

## Integration final gates (after both Agents merge)
1. Public targeted pytest for Agent1 fail set + collection-error files
2. Desktop targeted Vitest for Agent2 fail set
3. Public **full** pytest (once)
4. Desktop **full** Vitest (once)
5. `version_manager check` + `change_registry check` + `check_project.py`
6. Typecheck + Desktop production build
7. No real Provider / no installer / no Tag/Push unless separately authorized

## Implementation blockers (before authorizing Agents)
- User must authorize fix Agents (this CHG only plans)
- Clarify whether private-lab (U1) is in Free 1.2.0 release gate or formal-exception track
- Confirm change-registry rewrite policy for historical `integrated` statuses / missing ancestors (tooling rules vs data repair)
