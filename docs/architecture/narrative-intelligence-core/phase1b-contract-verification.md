# Phase 1B-P Contract Verification

## Schema

- [x] Empty DB `create_all` + `apply_narrative_phase1bp_migrations` idempotent
- [x] Simulated Phase 1A DB upgrade preserves old `analysis_runs` / artifacts
- [x] migration_id `006–010` unique; `001–010` order stable
- [x] Table names unique; FK targets exist
- [x] Stable rows separate from version rows
- [x] Partial unique canonical indexes for Asset / Relation versions

## Enums / semantics

- [x] Asset / Relation `review_status` enum
- [x] Lock columns independent of `review_status`
- [x] Evidence requires Snapshot + `paragraph_content_hash` + offsets
- [x] Analysis Conflict status / severity
- [x] Entity lifecycle excludes candidate/confirmed

## Protocols / Pattern boundary

- [x] Protocol imports (Entity / Asset / Relation / Conflict)
- [x] Pattern DTO file present; no Pattern ORM tables
- [x] Old artifact / run readable after upgrade simulation

## Gates run

- [x] `pytest apps/api/tests/test_narrative_phase1bp_contract.py` (+ phase1p contract) — 24 passed
- [x] `python scripts/version_manager.py check`
- [x] `python scripts/change_registry.py check`
- [x] `git diff --check`

## Deferred (Agents D/E/F / Integration)

- Entity/Alias service implementation
- Asset canonical switch transaction service
- Evidence runtime validation against Snapshot gateway
- Relation + Conflict adjudication UI
- Pattern Map adapter / product route
- Full Pytest / Vitest / production build
