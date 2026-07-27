# Phase 2A Frontend Mock Lab Implementation (Agent N)

**Change:** CHG-20260723-033
**Branch:** `feature/narrative-phase2a-run-frontend`
**Worktree:** `D:\Dstorylens-wt-narrative-run-frontend`

## Surface

Isolated `WholeBookMockRunLab` under `apps/desktop/src/features/wholeBook/runShell/lab/`.

Flow: Preflight → Mode → Modules → Stage Plan → **启动 Mock 验证运行** → Progress → Partial Results → Evidence → Structure Map.

## Rules enforced

- Production start button remains disabled (`RUN_CREATE_ENABLED_IN_CLIENT=false`).
- Mock start is a separate control; never calls formal Run Create.
- Banner: “开发验证，不是真实分析”; every step shows `mock / non-production`.
- Visible only in development/test; production returns `null`.
- Lab disabled shows stable disable reason (`MOCK_LAB_DISABLED`).
- Isolated route constant `/dev/whole-book-mock-run-lab` — **not** wired into `apps/desktop/src/app/router.tsx`.
- No second Run state machine; status / `allowed_actions` come from backend only.

## Related docs

- [phase2a-mock-run-client.md](./phase2a-mock-run-client.md)
- [phase2a-polling-implementation.md](./phase2a-polling-implementation.md)
- [phase2a-run-controls-implementation.md](./phase2a-run-controls-implementation.md)
- [phase2a-partial-results-lab.md](./phase2a-partial-results-lab.md)
- [phase2a-frontend-verification.md](./phase2a-frontend-verification.md)
