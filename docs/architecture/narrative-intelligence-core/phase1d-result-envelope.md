# Phase 1D-P Result Envelope

Shared backend/frontend logical contract: `WholeBookResultEnvelope`.  
No raw model JSON; no full body text in Envelope.

## WholeBookResultEnvelope fields

| Field | Required | Notes |
|-------|----------|-------|
| `schema` | yes | envelope schema id |
| `version` | yes | envelope schema version |
| `run_id` | yes | |
| `book_id` | yes | |
| `book_snapshot_id` | yes | results bind to Snapshot |
| `analysis_mode` | yes | |
| `module_key` | yes | one of 11 module keys |
| `module_status` | yes | see enum |
| `generated_at` | yes | |
| `source_stage_keys` | yes | module may span stages |
| `source_artifact_ids` | yes | |
| `asset_ids` / `asset_version_ids` | yes | Phase 1B refs |
| `relation_ids` / `relation_version_ids` | yes | |
| `conflict_ids` | yes | |
| `evidence_count` | yes | |
| `confidence_summary` | yes | aggregate |
| `review_summary` | yes | confirm/lock status |
| `stale` | yes | bool |
| `partial` | yes | bool; must be explicit |
| `warnings` | yes | |
| `payload` | yes | **typed by module DTO** |

## `module_status` semantics

| Status | Meaning |
|--------|---------|
| `not_requested` | module not in resolved plan |
| `pending` | planned, not started |
| `running` | stages producing this module in flight |
| `partial` | usable incomplete result |
| `completed` | module finished for this Run |
| `failed` | module failed (siblings may remain) |
| `stale` | outdated vs Snapshot / hash; ≠ failed |
| `blocked` | waiting on dependency / conflict / gate |

## Payload rules

1. `payload` MUST be constrained by the matching Module Result DTO.
2. Frontend MUST NOT consume arbitrary model JSON.
3. Envelope MUST NOT store full novel body text.
4. Evidence uses references (`WholeBookEvidenceRefDto`), not inline full paragraphs.
5. `partial` must be explicit (`true`/`false`).
6. `stale` ≠ `failed`; conflict ≠ `failed`.
7. One module may span multiple stages (`source_stage_keys`).
8. Results MUST bind `book_snapshot_id`.
9. `schema` + `version` are mandatory.

See [phase1d-module-result-contracts.md](./phase1d-module-result-contracts.md).
