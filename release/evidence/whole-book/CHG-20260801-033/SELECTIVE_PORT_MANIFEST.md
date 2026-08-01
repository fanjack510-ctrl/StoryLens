# SELECTIVE_PORT_MANIFEST

**Rule:** No whole-branch merge. No raw directory copy. Port only approved items into `integration/1.2.0-after-1.1.2` / private integration.

**Source HEADs (committed base of WIP trees):**  
Public WIP HEAD `10e69badda23c980199e9faad1ea2894a476bb86` + dirty WT  
Private WIP HEAD `5dabfd5eb0d08e03d4fff6adb5d845a16811a39f` + dirty WT  

Target: Public `integration/1.2.0-after-1.1.2`, Private `integration/1.2.0-private-after-1.1.2`.

## Public WIP candidates

| Source | Class | Target | Reason | Novel-custom? | Tests | Agent |
|---|---|---|---|---|---|---|
| `.../structure_stages_output_contract_v2.py` (dirty) | PORT_REQUIRED | same path | empty/binding codes + Public validate parity | No | empty_policy + A–J | 1 |
| `.../structure_stages_execution_materialization.py` (untracked) | PORT_REQUIRED | same path | Estimate-frozen coverage binding fingerprint | No | catalog/exec tests | 1 |
| `.../structure_stages_result_mapper_v2.py` (dirty) | PORT_REQUIRED | same path | Asset mapping alignment | No | mapper/A–J | 1 |
| `.../whole_book_module_output_validator.py` (dirty) | PORT_REQUIRED | same path | V2 validator hooks | No | unit/replay | 1 |
| `.../whole_book_provider_gateway.py` (dirty) | PORT_REQUIRED | same path | repair/empty fail-closed | No | A–J | 1 |
| `apps/api/tests/test_structure_stages_output_contract_v2_empty_policy.py` | PORT_REQUIRED | same | empty-policy unit tests | No | self | 1 |
| fixtures `structure_stages_v2_http_empty_*.json`, `no_observation.json` | PORT_REQUIRED | same | empty scenarios | No | replay | 1 |
| dirty fixtures `structure_stages_v2_http_*.json` deltas | PORT_REQUIRED | same | keep A–J coherent with policy | No | A–J | 1 |
| `test_narrative_phase2br1_structure_stages_v2_http_replay.py` dirty | PORT_REQUIRED | same | empty scenarios extension | No | A–J | 1 |
| `product_contract/module_results.py` dirty (+2) | PORT_REQUIRED | same | V2 DTO consistency if delta is empty-policy | No | contract tests | 1 |
| `private_whole_book_analysis_runtime.py` (+504) | CONFLICT_REWRITE_REQUIRED | same | Lab runtime large; port only structure empty-policy call sites, rewrite against current Free/Lab baseline | Unknown until diff review | Lab tests | 1 / Integration |
| `private_lab_run_executor.py` / adapters / diagnostics / lab_run_service | CONFLICT_REWRITE_REQUIRED | same | Lab wiring; selective hunks only | No | Lab | 1 / Integration |
| `release/changes/CHG-20260725-001.json` dirty | DO_NOT_PORT | — | registry noise on protected WIP | — | — | — |
| Free product files (not in WIP) | ALREADY_PRESENT / new work | Free service/router | Baseline Wave D; Agent1 implements wiring (not a WIP port) | — | free tests | 1 |

## Private WIP candidates

| Source | Class | Target | Reason | Novel-custom? | Tests | Agent |
|---|---|---|---|---|---|---|
| `citation/structure_field_policy.py` | PORT_REQUIRED | same | freeze binding + empty observation | No | schema/repair | 1 |
| `citation/structure_schema_v2.py` | PORT_REQUIRED | same | validate empty/binding | No | schema tests | 1 |
| `citation/structure_repair.py` | PORT_REQUIRED | same | EMPTY_RESULT_AFTER_REPAIR | No | repair tests | 1 |
| `citation/structure_prompt_render.py` | PORT_REQUIRED | same | empty repair instructions | No | repair | 1 |
| `citation/structure_contract.py` | PORT_REQUIRED | same | failure code constants | No | — | 1 |
| `citation/__init__.py` exports | PORT_REQUIRED | same | export surface | No | import tests | 1 |
| `modules/structure_stages/runner.py` | PORT_REQUIRED | same | capabilities/binding integration | Review for sample hooks | runner tests | 1 |
| `modules/structure_stages/result_mapper_v2.py` | PORT_REQUIRED | same | mapper | No | mapper tests | 1 |
| `tests/test_structure_stages_*` dirty | PORT_REQUIRED | same | lock policy | No | self | 1 |

## Counts (this freeze)

| Class | Count (approx) |
|---|---|
| PORT_REQUIRED | **22** |
| CONFLICT_REWRITE_REQUIRED | **4** (Lab runtime/executor/adapters/diagnostics clusters) |
| DO_NOT_PORT | **1** (+ any novel-specific hunks if found during port review) |
| ALREADY_PRESENT | Baseline Lab V2 without empty-policy binding freeze |
| EXPERIMENT_ONLY | None flagged by name; large Lab runtime hunks treated as rewrite-required not blind port |
| OBSOLETE | None confirmed |

## Port review gate

Before each file lands: Agent1 must `git diff` WIP vs baseline and reject hunks containing book titles, sample chapter counts as hard gates, or keyword detectors. Such hunks → **DO_NOT_PORT**.
