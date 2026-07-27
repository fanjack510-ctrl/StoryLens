# Phase 2A Runtime Composition

**Change:** CHG-20260723-035
**Module:** `apps/api/app/narrative_core/services/mock_whole_book_run_runtime.py`

## Composition root

`MockWholeBookRunRuntime` is the single wiring point for Agent M (service/executor) and Agent O (reliability stack). Integration constructs it via `create_mock_lab_runtime(...)` when Lab is enabled; tests inject isolated instances.

### Built services

| Factory | Dependencies wired |
|---------|-------------------|
| `build_run_service(session)` | auth, task_registry, idempotency, concurrency, quota, audit, fault_injection |
| `build_executor(session)` | task_registry, engine, budget_guard, idempotency, concurrency, audit, fault_injection |
| `build_recovery(session)` | lab_enabled, audit_sink, explicit_resume_allowed (default false) |
| `build_startup_adapter()` | session_factory, lab_enabled, audit_sink |

## Task Registry vs Concurrency Guard

| Concern | Component | Scope |
|---------|-----------|-------|
| In-flight executor lease | `InProcessMockRunTaskRegistry` | One active executor task per run; cancel/pause/resume routing |
| Book-level active run | `MockRunConcurrencyGuard` | At most one non-terminal mock run per book |
| Operation dedupe | `MockRunIdempotencyService` | Create/action replay; process-local + metadata-backed create |

Registry tracks **executor lifecycle** (background task handle). Concurrency guard tracks **business invariant** (no duplicate active runs). Both must pass before create/start proceeds.

## Quota / Budget order

On each stage asset write path (executor → engine hook):

1. **Concurrency guard** — active-run / lease checks (create path)
2. **Idempotency** — replay or conflict (create/action path)
3. **Quota service** — synthetic usage counters (non-persistent)
4. **Budget guard** — deny write before persistence when budget exceeded
5. **Audit sink** — record decision (no body/prompt)
6. **Persist** — stage artifact / metadata only if prior gates allow

Budget deny is fail-closed: no asset row, no metadata bump beyond audit.

## Default runtime policy

- `get_default_mock_lab_runtime()` returns disabled runtime in production or when Lab flag false
- No global singleton that enables Lab by default
- `reset_default_mock_lab_runtime()` clears process-local stores for tests

## Registration gate

`should_register_mock_lab_router(environment, lab_enabled)` requires `development` or `test` **and** `lab_enabled=true`. Used by `mount_mock_lab_if_enabled` in `main.py`.
