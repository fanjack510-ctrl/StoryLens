# Phase 1A Integration Report

**Change:** CHG-20260723-015  
**Branch:** `integration/narrative-phase1a`  
**Worktree:** `D:\Dstorylens-wt-narrative-integration`  
**Source:** `e983e7279d4c72655334017da114ce572e41b0e0` (`feature/narrative-phase1-contract`)  
**VERSION:** 1.0.5

## Merge order

1. Agent A `feature/narrative-phase1a-snapshot` @ `7863ba8`
2. Agent B `feature/narrative-phase1a-runstage` @ `ca49ae2`
3. Agent C `feature/narrative-pattern-readiness` @ `7ca2d81`

Cherry-pick all commits chronologically per branch (not primary-only).

### Conflicts

- `apps/api/app/narrative_core/services/__init__.py` — unified A+B exports; Stub not re-exported as production default.

## Integration corrections

1. **Book Hash Contract** — sole public entry `calculate_book_content_hash(Sequence[BookHashChapterInput])`; removed dual aggregate API.
2. **Snapshot errors** — revised migration `20260723_003` + ORM with `error_code` / `error_message`; `source_fingerprint` is source-only.
3. **Gateway wiring** — `RunStageService` defaults to `SnapshotValidationGatewayImpl`.
4. **Sidecar interrupt** — staged runs with stages → `interrupted`; legacy no-stage → `failed`.
5. **RunStatus** — centralized narrative run status constants.
6. **Snapshot rebuild** — expire/populate_existing after child clear so integrity revalidation sees new chapters.

## Test evidence (directed)

- Agent A + B + Integration pytest: 62 passed
- Agent C: `npm run typecheck` + `npx vitest run src/features/narrativePattern`
- `python scripts/version_manager.py check`
- `python scripts/change_registry.py check`
- `git diff --check`

## Not done

- Phase 1B narrative assets
- WholeBookAnalysisEngine / prompts / model calls
- Pattern ORM / routes / Pro pages
- Release / push / build / publish
