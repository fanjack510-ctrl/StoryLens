# Phase 2B Fake Provider E2E

**Change:** CHG-20260723-040
**Test:** `apps/api/tests/test_narrative_phase2b_integration.py`

## Pipeline under test

Snapshot → Context Bundle → Fake Provider → Fake Module Runner → Output/Evidence Validation → Candidate Commands → Result DTO.

No formal prompts, no real model calls, no production whole-book runs.

## Eight E2E scenarios

| Test | Scenario |
|------|----------|
| `test_scenario_overview_native_e2e` | Native overview; fake provider; evidence; candidate sink; no Pattern table |
| `test_overview_no_protagonist_and_multi` | Overview modes: no_central_conflict, multi_protagonist, partial — no forced protagonist |
| `test_scenario_structure_non_three_act` | Five-stage structure; must not force three-act template |
| `test_scenario_chapter_functions` | Side-story/flashback/empty labels; forbidden genre templates absent |
| `test_scenario_storylines` | Quest/paused storyline taxonomy; not character_list |
| `test_scenario_enhanced_degrade` | Enhanced mode + stale aux fixture; degraded coverage |
| `test_scenario_validation_rejection` | Seven rejection markers + bad evidence hash |
| `test_scenario_resume` | Checkpoint resume; prompt pack / context hash incompatibility; dedupe |

## Supporting integration tests

| Test | Surface |
|------|---------|
| `test_runtime_composition_aliases_and_schema` | Schema, aliases, four runners, production factory deny |
| `test_paragraph_grouping_policy_defaults_and_fingerprint` | Defaults 40/2, override shrink, initial-only flag |
| `test_context_bundle_mapper_round_trip` | Hash stability; no full_text in public dict |
| `test_scenario_production_isolation` | `assert_production_isolation()` |
| `test_metamorphic_grouping_and_provider_limit` | Fingerprint divergence on policy/limit |
| `test_provider_gateway_is_agent_p_default` | Gateway + adapter wiring |
| `test_static_security_scan_paths` | Credential/network pattern scan |
| `test_version_and_gates_locked` | VERSION 1.0.5 + gate constants |

## Result DTO invariants

Accepted Fake E2E paths assert:

- `fake=True`, `synthetic=True`, `non_production=True`
- `canonical=False`, `asset_written=False`
- `candidate_summary.orm_written=False`
- `validation.accepted=True` (happy path) or `False` (rejection scenarios)

## Fixtures

- SQLite in-memory book + completed snapshot (Phase 1P migrations applied)
- `RecordingCandidatePersistenceSink` for candidate command recording
- `FixtureAuxiliaryContextSource` + `make_stale_aux_fixture` for Enhanced degrade
- Synthetic evidence via `_first_para_evidence` helper

See [phase2b-runtime-composition.md](./phase2b-runtime-composition.md) for wiring details.
