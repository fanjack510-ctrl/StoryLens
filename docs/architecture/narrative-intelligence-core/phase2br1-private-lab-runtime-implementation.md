# Phase 2B-R1 Private Lab Runtime Implementation (Agent V / CHG-047)

## Scope

Upgrades HTTP Private Lab from shell-only sessions to AnalysisRun-backed
development whole-book runtime with sequential first-four modules and Phase 1B
candidate persistence.

## Public deliverables

| Component | Path |
|-----------|------|
| Ports (U-compatible) | `apps/api/app/narrative_core/services/private_lab_ports.py` |
| Metadata | `apps/api/app/narrative_core/services/private_lab_run_metadata.py` |
| Task registry | `apps/api/app/narrative_core/services/in_process_private_lab_task_registry.py` |
| Idempotency / concurrency | `apps/api/app/narrative_core/services/private_lab_idempotency.py` |
| State service | `apps/api/app/narrative_core/services/private_lab_run_state_service.py` |
| Run service | `apps/api/app/narrative_core/services/private_engine_lab_run_service.py` |
| Executor | `apps/api/app/narrative_core/services/private_lab_run_executor.py` |
| Recovery | `apps/api/app/narrative_core/services/private_lab_recovery_service.py` |
| Persistence methods | `apps/api/app/narrative_core/services/candidate_persistence_adapter.py` |
| HTTP router | `apps/api/app/routers/whole_book_private_engine_lab_runs.py` |
| Tests | `apps/api/tests/test_narrative_phase2br1_private_lab_runtime.py` |

## Create order

`CREATE_PRIVATE_LAB_RUN_SEQUENCE` in `private_engine_lab.py`:

Authorization → Preflight → Estimate fingerprint → Consent fingerprint →
Credential → Budget → Snapshot COMPLETED → Snapshot/Book bind → Concurrency
reserve → AnalysisRun → 10 RunStages → Task register → Executor start.

Pre-create failures write no Run/Stage/Candidate/Artifact and reserve no slot.

## Stage plan

Always creates the frozen 10 stages. Unused stages are `skipped` with reason
`MODULE_NOT_REQUESTED`. First-four modules execute sequentially:

`book_overview` → `structure_stages` → `chapter_functions` → `storylines`

## Ports

V defines Fake Ports only; Integration adapts to Agent U services:

- `PrivateLabPreflightPort`
- `PrivateLabEstimatePort`
- `PrivateLabConsentValidationPort`
- `PrivateLabProviderExecutionPort`

No hardcoded token/cost truth. No second public DTO source.

## Persistence

`Phase1BCandidatePersistenceSink` remains the ORM path via Phase 1B services.
Explicit Lab methods: `persist_entities`, `persist_assets`, `persist_relations`,
`persist_asset_evidence`, `persist_relation_evidence`, `persist_conflicts`,
`persist_stage_artifact`. Candidate-only; no auto canonical/confirm/lock.

Evidence provenance via parent Version / attributes_json (no new `run_id` column).

## Isolation

- Default `WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED=false`
- Shared `main.py` mount left to Integration (CHG-048)
- Formal Run create remains disabled
- Mock Lab untouched
- No Migration / VERSION / ship-flag flips
