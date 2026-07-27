# Phase 1D Agent J — Preflight UX

## Data loading

- Endpoint: `POST /api/v1/books/{book_id}/whole-book-runs/preflight`
- Adapter: `apps/desktop/src/features/wholeBook/runUx/preflightClient.ts`
- Mapper: `preflightMapper.ts` (Phase 1C body → `WholeBookPreflightPageModel`)

Rules:

1. Backend is sole authority for capability / quota / engine / blocking.
2. Transport failure → fail-closed model (`run_creation_enabled=false`, `allowed=false`).
3. Unknown book → `BOOK_NOT_FOUND` surfaced explicitly.
4. Missing snapshot → “需要建立快照” warning; **no auto-create**.
5. Client never calls create-run.

## Mode selection

- Modes: `whole_book_native` | `whole_book_enhanced`
- Modes are **not** Capability Keys
- `supported_modes` from Preflight / capability decision
- Unsupported modes disabled with reason text
- Mode change reloads Preflight

## Confirm zone

Shows Capability / License / Quota / Engine / Snapshot / warnings / blocking_reasons / `run_creation_enabled`.

Buttons:

- **开始整书分析** — always disabled this phase; no force start
- 刷新检查 / 返回书籍 / 查看功能预览 / 查看 Snapshot 状态

## A11y / theme

- Light/dark via lab `data-theme`
- Status text for screen readers
- Disabled controls expose `title` / visually-hidden reasons
- Long titles wrap (`overflow-wrap`)
