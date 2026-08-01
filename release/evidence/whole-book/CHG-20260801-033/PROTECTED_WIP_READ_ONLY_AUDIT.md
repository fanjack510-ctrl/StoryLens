# PROTECTED_WIP_READ_ONLY_AUDIT

## Audit mode

READ-ONLY only: `git status/branch/rev-parse/log/diff`, `Get-Content`, `rg`, file hash.  
No checkout/reset/clean/stash/merge/commit/write into protected trees.

## Before fingerprint

| Tree | Branch | HEAD |
|---|---|---|
| Public WIP | `fix/narrative-phase2br1-structure-empty-policy` | `10e69badda23c980199e9faad1ea2894a476bb86` |
| Private WIP | `fix/phase2br1-structure-empty-policy` | `5dabfd5eb0d08e03d4fff6adb5d845a16811a39f` |

Public WIP dirty (porcelain=v2 summary): **21 modified + 5 untracked**  
Private WIP dirty: **11 modified**

Fingerprint file: `%TEMP%\chg033-wip-before.txt`

### Public WIP key SHA256 (working tree)

| File | SHA256 |
|---|---|
| `structure_stages_output_contract_v2.py` | E367336F143D642D27D7B46B30B3CFBB6A464EE82CA57489F699E15B377F2E8E |
| `structure_stages_execution_materialization.py` (untracked) | E16356CC2DE5335DD0F30B11A35E71669F776C029502B8EA9EB219620A376A3F |
| `test_structure_stages_output_contract_v2_empty_policy.py` (untracked) | 1761D7AE92F1334FDCF09EEB759390746D9768648C8D516251555F7BCEF5F69B |
| `whole_book_provider_gateway.py` | A9B19592E64AF111130CBE95B2A41279282805FF42688BC5BAE09508BE99FFEE |

### Private WIP key SHA256 (working tree)

| File | SHA256 |
|---|---|
| `structure_field_policy.py` | 2EDE3ED2F05A0C0FA65CAC7A80C8FF6136466E70CE206F3C741702FF323AC9BC |
| `structure_schema_v2.py` | 83535985B55A6EA08910BEE5E7DBD4BAA9D32BE5F9C7261B92A4985D43EA79A7 |
| `structure_repair.py` | 98C2DAD2775FCAF02DE350155F5712CD5F363902566BEA57BFB95CBD72B45287 |
| `structure_contract.py` | 59CB74449161A898284FC6A656C6F4A89E80A7D616CF1814B2643EAA61D8C91F |
| `structure_prompt_render.py` | DE8E10C08BCE9ACE5C61D73BD770C6006E21F249E9A5D4C3E7175F874CBD65CD |

## Empty-policy findings (from WIP)

### 1–2. insufficient / stages=[]

Server freezes `StructureCoverageBinding` via `freeze_structure_coverage_binding(capabilities)`:

- If `can_identify_local_stages == false` → `expected_coverage_scope=insufficient`, `permits_empty_observation=true`, `requires_stage_observation=false`.  
- Else expected ∈ {`local`,`partial_span`,`full_selected_range`}, `requires_stage_observation=true`, empty stages **forbidden**.

`stages=[]` is legal **only** when actual `coverage_scope` equals frozen expected `insufficient`.

Capabilities derive from selection metadata only (`derive_structure_context_capabilities`):  
`can_identify_local_stages = (selected_chapter_count > 0 OR selected_paragraph_count > 0)`.  
No novel title / keyword / per-book thresholds found in policy derivation.

### 3. turning_points=[]

Independently allowed when stages present if turning-point fields are `allowed_absent` / `can_identify_turning_points` gates permit absence. Empty TPs with non-empty stages is a valid product outcome.

### 4–6. Short/missing/empty provider output

- Capability false → expected insufficient; provider must return empty stages with that scope.  
- Capability true + empty stages → `STRUCTURE_REQUIRED_STAGE_MISSING` (or binding mismatch if scope wrong).  
- After one targeted repair still empty/illegal → `STRUCTURE_EMPTY_RESULT_AFTER_REPAIR` (fail-closed).

### 7. Repair

Max 1 contract repair (`structure_stages_contract_repair`). Empty/binding failures use `structure_empty_result_repair_instruction` — instructs **not** to invent stages when insufficient; when observation required, must return ≥1 legal stage with frozen scope.

### 8. Three-act placeholder

Forbidden in prompts/policy language and Phase2B rules. No forced 3-act generation.

### 9. confidence / limitations

V2 allows `analysis_confidence` / `overall_confidence` optional; `limitations` tuple (e.g. `RESOURCE_LIMIT_TRUNCATED` interacts with full_selected_range validity).

### 10. coverage_scope enum

`local` | `partial_span` | `full_selected_range` | `insufficient`  
Provider may only emit the **single** server-frozen expected scope (schema enum injected).

### 11. Evidence insufficient

Per-stage citation failures reject that validation path; empty observation when required fails module (repair then fail-closed). Does **not** silently invent stages. Insufficient path is capability-driven empty result, not “drop bad stages and keep fake remainder” as a confirmed product rule in WIP tests.

### 12. Public vs Private consistency

Public contract prefers Private `validate_structure_stages_result_v2` + shared failure code strings; Public `_public_shape_validate` mirrors empty/binding rules (see untracked Public empty-policy tests).

### 13. WIP tests

Public untracked: `test_structure_stages_output_contract_v2_empty_policy.py` + empty fixtures (`empty_initial`, `empty_after_repair`, `no_observation`) + expanded A–J replay.  
Private dirty: schema / mapper / repair tests extended.

### 14–15. Mature vs experiment

Mature: coverage binding freeze, empty observation rules, repair fail-closed, failure codes, FakeHttp fixtures.  
Lab-heavy / large dirty: `private_whole_book_analysis_runtime.py` (+504), lab executor adapters — treat as **selective** port, not wholesale.  
No novel-specific keyword gates observed in capability derivation; reject any such if discovered during port review.

## After fingerprint

| Tree | Branch | HEAD |
|---|---|---|
| Public WIP | `fix/narrative-phase2br1-structure-empty-policy` | `10e69badda23c980199e9faad1ea2894a476bb86` |
| Private WIP | `fix/phase2br1-structure-empty-policy` | `5dabfd5eb0d08e03d4fff6adb5d845a16811a39f` |

| Check | Result |
|---|---|
| HEAD match before | YES |
| Branch match before | YES |
| `git status --porcelain=v2` match before | YES |
| Key file hashes match before | YES |

**PROTECTED WIP UNCHANGED：YES**
