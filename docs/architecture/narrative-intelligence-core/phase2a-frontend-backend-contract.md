# Phase 2A Frontend–Backend Contract

**Change:** CHG-20260723-035
**Contract base:** [phase2a-frontend-lab-contract.md](./phase2a-frontend-lab-contract.md)

## Lab API paths

All Mock Run client calls use prefix:

```text
/api/v1/labs/whole-book-runs
```

Routes: create, get run view, start/pause/resume/cancel/retry, partial results. Formal production create path remains disabled.

## Lab marker (all mutating requests)

Every write from frontend client includes:

```text
X-StoryLens-Mock-Lab: 1
```

Missing marker → `MOCK_LAB_REQUEST_MARKER_REQUIRED` (fail-closed). Read/poll GETs follow contract; writes always carry marker.

## `allowed_actions` from backend

Frontend controls (`MockRunControls`) consume `allowed_actions` on `MockWholeBookRunViewDto` from backend DTO only. UI must not invent actions or derive run status locally. On action failure, re-fetch run view.

## Polling policy

`mockRunPollingController` / `useMockRunPolling`:

- Intervals per contract (running vs terminal backoff)
- Stop on terminal status
- Discard stale responses (version / run_id mismatch)
- Respect page visibility where implemented

## Result projection (Phase 1D reuse)

Partial/completed results use Phase 1D read-only paths:

```text
GET /api/v1/whole-book-runs/{run_id}/results
GET /api/v1/whole-book-runs/{run_id}/results/{module_key}
```

`resultProjectionClient.ts` reuses Phase 1D DTO guards. Mock flags (`mock`, `non_production`, `synthetic_usage`) displayed in Lab UI; not presented as production analysis.

## Shared fixtures (no duplicate set)

Integration and Agent N tests reuse:

```text
apps/desktop/src/features/wholeBook/runShell/__tests__/fixtures.ts
```

This file wraps Phase 1D `runViewFixtures` with mock Lab fields (`mock`, `non_production`, `allowed_actions`). Integration does **not** introduce a second frontend fixture directory.

## Isolation rules (unchanged)

- `WholeBookMockRunLab` isolated route; not in formal product nav
- Production start button disabled; mock banner visible
- `labEnabled` prop / env gate required to show Lab surface
