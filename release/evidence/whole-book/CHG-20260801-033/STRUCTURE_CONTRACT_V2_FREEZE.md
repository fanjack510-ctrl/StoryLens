# STRUCTURE_CONTRACT_V2_FREEZE

## Decision

```
CANONICAL CONTRACT：V2
CONTRACT VERSION：STRUCTURE_OUTPUT_CONTRACT_VERSION = 2.0.0
WIRE contract_version：v2
V1 STATUS：adapter-only
V2 STATUS：canonical
```

Desktop Phase1D `StructureStagesResultDto` is **not** product SoT.  
Public Free API returns **V2** (or a thin UI view-model mapped **from V2 only**).  
No dual competing SoT.

## Identity

| Item | Value |
|---|---|
| Output contract id | `StructureStagesResultV2` |
| Package version | `2.0.0` |
| Wire `contract_version` | `"v2"` (required) |
| `evidence_contract_version` | `"v2"` (required) |

## Top-level fields

| Field | Type | Required | Nullable | Enum / default | Evidence | Compat |
|---|---|---|---|---|---|---|
| `contract_version` | string | yes | no | `"v2"` | — | reject other |
| `evidence_contract_version` | string | yes | no | `"v2"` | — | reject other |
| `coverage_scope` | string | yes | no | `local`\|`partial_span`\|`full_selected_range`\|`insufficient` | must match frozen expected | — |
| `stages` | array | yes | no (may be `[]`) | — | see empty policy | — |
| `turning_points` | array | yes | no (may be `[]`) | — | TP rules when present | — |
| `analysis_confidence` | number | no | yes | default null | — | optional |
| `overall_confidence` | number | no | yes | may mirror analysis_confidence | — | optional |
| `limitations` | string[] | no | no | default `()` | may include `RESOURCE_LIMIT_TRUNCATED` | — |
| `context_capabilities` | object | no | yes | server echo of capabilities | — | diagnostic |
| citation references | inside claims/boundaries as `citation_ids` | yes when observed/inferred | — | catalog-bound | exact deep-link | — |
| provenance / source revision | via Public Asset/Run binding (snapshot_revision, run_id) | Public persistence | — | — | not optional for persisted product | — |
| empty reason | failure codes / binding (see EMPTY_POLICY_FREEZE) | when insufficient or failed | — | STRUCTURE_* codes | — | UI may map labels |

## Stage object (minimum)

- stage key / local_ref  
- title (non-empty)  
- summary claim: status + value + citation_ids  
- start_boundary + end_boundary with citations  
- chapter range integrity (no overlap fail-closed)

## Turning point object (when present)

- tp key / local_ref  
- title + description claims with citations  
- related_stage_refs must resolve  

## Desktop consumption

**Freeze:** Public API exposes V2 product JSON; Desktop consumes V2 directly **or** maps V2 → local view props in the Free page layer.  
V1 `StructureStagesResultDto` retained only for Structure Map / Lab prototypes (**adapter-only**), never as Free product write path.

## Forbidden

- Returning V1 as Free product result SoT  
- Silent V1↔V2 dual write of different semantics  
- Markdown fences / `evidence_map` wrappers in provider payload  
