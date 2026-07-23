# Phase 1B Integration Report

**Change:** CHG-20260723-020  
**Worktree:** `D:\Dstorylens-wt-narrative-phase1b-integration`  
**Depends on:** CHG-20260723-017 (D), CHG-20260723-018 (E), CHG-20260723-019 (F)  
**VERSION:** 1.0.5 (unchanged)

## Cherry-pick / merge order

1. Agent D `feature/narrative-phase1b-entity` — Entity / Alias / merge
2. Agent E `feature/narrative-phase1b-asset` — Asset / Version / Evidence
3. Agent F `feature/narrative-phase1b-relation` — Relation / Evidence / Conflict
4. Integration branch — cross-cutting fixes + E2E verification

## Integration corrections

| Area | Fix |
|------|-----|
| Entity merge | `superseded_by_entity_id` on `narrative_entities` (migration 006 revised); transactional `merge_entities` transfers aliases |
| Alias lookup | Casefold via `normalize_alias_text` (Unicode NFKC + casefold) |
| Relation key | `build_relation_key` uses SHA-256 over book + endpoints + `identity_fingerprint` (no Python `hash()`) |
| Conflict sink | `AnalysisConflictSinkImpl` breaks Asset ↔ Conflict cycle; Asset/Relation record via `ConflictCreateRequest` |
| Evidence gates | Version snapshot must match evidence snapshot; canonical requires `support` evidence |
| Version binding | Shared `validate_version_run_snapshot_binding` for Run / Snapshot consistency |
| Pattern projection | Internal `pattern_projection.py` adapter (no API, no Pattern tables) |

## Key protocols wired

- `NarrativeEntityServiceImpl` — create, alias review, merge, lock
- `NarrativeAssetService` — candidate → evidence → confirm → lock → conflict
- `NarrativeRelationServiceImpl` — same review/canonical path as Asset
- `AnalysisConflictServiceImpl` — cross-book ref validation, open-only blocking conflicts
- `build_pattern_projection_input` — canonical-only read model for future Pattern Map

## Test evidence

Directed suite: `apps/api/tests/test_narrative_phase1b_integration.py`  
Agent suites re-run when shared code touched: D/E/F directed tests.

## Not done

- Phase 2 analysis engine / model calls
- Pattern ORM tables or product routes
- Auto merge of Assets/Relations on entity merge
- Release / push / VERSION bump
