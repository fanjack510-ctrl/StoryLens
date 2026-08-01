# PIPELINE_STAGE_DECISION

## Current baseline Free stages

`WHOLE_BOOK_STAGE_CODES_V1`:

`snapshot` → `windowing` → `extract_entities_events` → `materialize_assets` → `synthesize_overview` → `project_result` → `finalize`

**`structure_stages` is NOT a Free stage code today.**

## Freeze

| Item | Decision |
|---|---|
| Pipeline stage code | **`synthesize_structure_stages`** (Free/foundation stage list) |
| Provider module key | **`structure_stages`** (existing Private/Lab module) |
| Provider unit kinds | `structure_stages_initial`, `structure_stages_contract_repair` (existing) |
| Position | After `synthesize_overview`, before `project_result` |
| Depends on overview / characters_events **results** as input? | **NO** (native independence). Ordering is orchestration-only for resume UX. |
| Input | Snapshot paragraphs + CitationCatalog + frozen StructureStagesExecutionMaterialization / coverage binding |
| Independent retry | YES at provider-unit level with same frozen materialization fingerprint; no new catalog/scope drift |
| Cost estimate | Include structure provider unit(s) in Free estimate when structure capability available |
| Pause / resume / cancel | Same WholeBookRunStatus machine; resume skips completed units; cancel stops further units |
| Legal insufficient empty | Stage/unit **completed** |
| Unrecoverable after repair | Stage/unit **failed**; may fail run per existing Free failure aggregation rules |
| Duplicate resume | No second Provider call for completed unit; no duplicate Asset materialization for same fingerprint |
| Cancelled | No further structure execution |

## Stage list after freeze (code constant update, not Migration)

```
snapshot
windowing
extract_entities_events
materialize_assets
synthesize_overview
synthesize_structure_stages   ← NEW
project_result
finalize
```

## EMPTY RESULT RUN STATUS

| Structure outcome | Run status (typical) |
|---|---|
| Legal insufficient empty | `completed` (if other Free modules ok) |
| Structure failed unrecoverable | `failed` (or recoverable per existing policy if retryable — default **failed** for EMPTY_RESULT_AFTER_REPAIR) |
| User cancel | `cancelled` |

## Progress aggregation

`current_stage` may show `synthesize_structure_stages`; provider_calls_used includes structure units; completed_provider_units counts structure units.
