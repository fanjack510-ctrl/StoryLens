# STEP 2.G4 Gate Evidence

**Change:** CHG-20260725-003
**Step:** STEP 2.4
**Gate:** STEP 2.G4
**Started:** 2026-07-26T02:48:54+08:00
**Finished:** 2026-07-26T06:47:10+08:00
**Verdict:** PASSED

## Integration HEADs

| Repo | Branch | HEAD |
|------|--------|------|
| Public | `integration/narrative-phase2br1` | `d8c9eb1d3f499fb08080bbb243497155f8d8e0fb` |
| Private | `integration/phase2br1` | `e0b96e7d7dba4d5383e0f250cc24a92eb7b7ee23` |

Working trees: clean. VERSION: `1.0.5`. Feature Flag default: `PRO_NATIVE_OVERVIEW_ENABLED=false`. Fixture `combined_sha256` unchanged. Structure Empty Policy WIP: preserved. Real Provider: not executed. Push / Tag / Release / verified: NO.

## Commits (STEP 2.4)

### Public

- `c614f72` fix(pro-integration): map Private engine errors and stop double transport calls
- `e663f72` fix(pro-runtime): block book delete while whole-book native run is active
- `6dd271b` fix(pro-ui): map PROVIDER and PRIVATE_ENGINE recovery error states
- `d8c9eb1` test(pro-integration): add STEP 2.4 failure injection and recovery matrix

### Private

- `e0b96e7` fix(engine): persist FakeTransport response for Public attempt accounting

## Adapter Path

```text
Public Run Orchestrator
→ Engine Loader (private-native-overview-v1)
→ Private Native Overview Engine
→ Fake Provider Transport only
→ Parser / Repair
→ Window Result
→ Materializer
→ Synthesis / Projection
```

Fixture engine is not used to stand in for Private in STEP 2.4 failure/happy private tests. Production API default remains Fixture until Live wiring (STEP 2.5); Loader still refuses silent Fixture downgrade.

## Failure Injection Matrix

| Class | Result |
|-------|--------|
| PROVIDER_TIMEOUT / RATE_LIMITED / UNAVAILABLE / OUTPUT_INVALID / OUTPUT_EMPTY | PASS (Public maps Private codes) |
| PRIVATE_ENGINE_UNAVAILABLE (import missing) | PASS (no Fixture fallback, no assets) |
| PRIVATE_ENGINE_INCOMPATIBLE (unknown engine id) | PASS |
| Evidence invalid quote (existing + Private citation repair) | PASS |
| Materializer mid-write nested rollback | PASS |
| Accounting no double transport.request | PASS (`call_count == 1` on timeout) |
| Interrupted window recovery (w0 skip, resume/retry) | PASS |
| Double retry same client_request_id | PASS (single run) |
| Create Run idempotency | PASS (prior STEP coverage retained) |
| Private+Fake one-window happy path | PASS |

## Transaction / Retry / Free

- Nested materializer savepoint prevents half-commit on forced asset write failure.
- Retry skips completed windows; assets not duplicated in recovery test.
- Free: book/chapter/paragraph reads + Pro 403 retained; active whole-book native run now blocks delete.
- UI: PROVIDER_* / PRIVATE_ENGINE_* titles + Vitest coverage.

## Tests

| Suite | Result |
|-------|--------|
| Public directed (walking/runtime/step23/step24/I0/flag/book_delete) | 74 passed |
| Private native + fixture | 28 passed |
| Desktop Vitest (proNativeOverview + api + router) | 26 passed |
| D-Audit (Integration review) | PASS — no P0 |

## P0 / P1 / P2

| Severity | Item | Status |
|----------|------|--------|
| P0 | Private PROVIDER_* collapsed to PRIVATE_ENGINE_UNAVAILABLE | Fixed |
| P0 | Accounting double `transport.request` | Fixed |
| P0 | Active whole-book run did not block delete | Fixed |
| P1 | API default engine_id still Fixture | Accepted until STEP 2.5 Live wiring; offline G4 proves Private path via explicit engine_id |
| P2 | Multi-window private+Fake full happy path | Partial (one-window private+Fake + multi-window Fixture retained) |
| P2 | api_dto comment lag / ending_state naming | Pre-existing; not expanded |

## Budget Used

```text
Live Provider cost: ¥0.00 (offline only)
```

## Result

```text
STEP 2.G4 = PASSED
```

## Next Step

```text
Read STEP-2.5-DETAILED.md
```
