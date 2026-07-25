# StoryLens 1.1.0 — Native Overview State Machine

**Status:** Frozen (STEP 2.1)  
**Change:** CHG-20260725-003  
**Implementation:** `apps/api/app/narrative_core/contracts/whole_book_overview_state_machine.py`  
**Enums:** `apps/api/app/narrative_core/enums.py`

## Related docs

- [Contract](./storylens-1.1.0-native-overview-contract.md)
- [Error codes](./storylens-1.1.0-native-overview-error-codes.md)
- [Database](./storylens-1.1.0-native-overview-database.md)
- [Architecture](../architecture/storylens-whole-book-architecture.md)
- [Public/Private boundary](../architecture/storylens-public-private-boundary.md)
- [1.1.0 scope](../releases/storylens-1.1.0-scope.md)
- [ADR-001](../architecture/adr/ADR-001-single-business-database.md) · [ADR-002](../architecture/adr/ADR-002-whole-book-native-source-of-truth.md) · [ADR-003](../architecture/adr/ADR-003-unified-narrative-assets.md) · [ADR-004](../architecture/adr/ADR-004-whole-book-runtime-and-analysis-passes.md) · [ADR-005](../architecture/adr/ADR-005-long-text-index-strategy.md)

---

## Run status (`RunStatus`)

### Additive production values

`pending` → `preparing` → `analyzing` ⇄ `materializing` → `synthesizing` → `completed`

Also: `failed`, `paused`, `cancelled`.

### Free / legacy values retained

`queued`, `running`, `interrupted` remain for Free / scene pipeline. Do not remove.

### Allowed Overview transitions

```text
pending → preparing
preparing → analyzing
analyzing → materializing
materializing → analyzing
materializing → synthesizing
synthesizing → completed
pending|preparing|analyzing|materializing|synthesizing → failed
analyzing|materializing|synthesizing → paused
paused → analyzing
failed → preparing | analyzing
any non-completed → cancelled
```

### Forbidden (examples)

```text
completed → analyzing
completed → failed
cancelled → running
failed → completed   # without actual re-execution
```

Re-analysis requires a new Run (or an explicit new version policy later). Do not mutate a completed Run into a new analysis.

Exact retry landing status depends on failed stage + checkpoint (orchestrator STEP 2.2+).

---

## Overview production stages (`OverviewProductionStageKey`)

Separate from legacy Lab `WholeBookStageKey` (10-stage). **Do not delete** the 10-stage enum.

```text
snapshot_preflight
build_context_windows
extract_overview_facts
materialize_assets
generate_overview_projection
finalize
```

Persisted via reused `analysis_run_stages` (`stage_key`, `stage_order`, `status`, `attempt_count`, input fingerprint, `checkpoint_json`, timestamps, error fields).

### Stage status subset for Overview

`pending` → `running` → `completed` | `failed` | `skipped`  
`failed` → `running` (retry)

Free `StageStatus` still includes `paused` / `interrupted` / `cancelled` for non-Overview pipelines.

---

## Window status (`WindowStatus`)

```text
pending → running → completed | failed | skipped
failed → running   # retry
```

Completed windows are terminal: default policy is **no** Provider re-call on Retry.

---

## Field status (`OverviewFieldStatus`)

`supported` | `low_confidence` | `insufficient_evidence` | `conflicted`

High confidence without evidence_refs is rejected by schema validators.
