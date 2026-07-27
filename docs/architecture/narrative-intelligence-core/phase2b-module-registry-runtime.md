# Phase 2B Module Registry & Runtime

**Change:** CHG-20260723-040
**Modules:** `whole_book_module_runner.py`, `private_whole_book_analysis_runtime.py`

## Registry

`WholeBookModuleSpecRegistry` holds `WholeBookModuleExecutionSpec` entries for the **first four module keys**:

| Module key | Role |
|------------|------|
| `book_overview` | Overview / protagonist policy |
| `structure_stages` | Non-template structure stages |
| `chapter_functions` | Chapter function labels |
| `storylines` | Storyline type/status taxonomy |

Built via `build_default_module_spec_registry()`; validated on runtime `__post_init__` (`module_registry.validate()`).

## Runners

`build_first_four_fake_runners(prompt_pack, gateway, output_validator)` produces one `BaseWholeBookModuleRunner` per key. Each runner:

- Holds module spec from registry
- Uses `ModuleProviderExecutionAdapter(gateway=...)` for provider calls
- Shares `output_validator` wired to Q evidence adapter
- Receives contract bundles from composition root after context build

## Planning / Producer / Result consistency

Integration verifies Module Spec fields align across:

- Context bundle `module_specs` resolution
- Runner `spec` (module_key, module_version)
- `make_execution_request` / checkpoint binding
- `ModulePipelineResultDTO` (module_key, module_version, configuration_fingerprint)

## Checkpoint / resume

`ModuleCheckpointBuilder` emits checkpoint on execute; `ModuleCheckpointValidator` gates resume:

- Prompt pack version change → `PROMPT_PACK_INCOMPATIBLE`
- Context bundle hash change → `ENGINE_CHECKPOINT_INCOMPATIBLE`
- Output dedupe on repeated resume (`resumed_deduplicated`)

Test: `test_scenario_resume` in integration suite.

## Candidate persistence boundary

`ModuleCandidateBuilder.build(..., mock=True)` assembles asset/relation/evidence/conflict commands. `RecordingCandidatePersistenceSink`:

- Records calls; `orm_written=False` always
- Rejects `allow_production_write`, auto confirm/lock, canonical overwrite
- No Phase 1B ORM persistence wiring in Integration

See [phase2b-candidate-persistence.md](./phase2b-candidate-persistence.md) for contract baseline.
