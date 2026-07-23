# Phase 2B Module Execution Spec

## Single authority: WholeBookModuleExecutionSpec

Fields: `module_key`, `module_version`, `display_name`, `supported_modes`, `required_stage_keys`, `producer_stage_keys`, `product_result_stage_dependencies`, `required_context_levels`, `output_schema_ref`, `evidence_policy_ref`, `validation_policy_ref`, `asset_type_outputs`, `relation_type_outputs`, `supports_partial`, `supports_resume`, `private_implementation_required`

## Three dependency views (derived, not independent tables)

| View | Meaning |
|------|---------|
| Engine Planning Stages | Stages the engine plans for the module |
| Producer Stages | Stages that produce module outputs |
| Product Result Dependencies | Stages the product result view depends on |

Compatibility adapters (temporary):

- `ENGINE_MODULE_PLANNING_STAGES` / `ENGINE_MODULE_PLANNING_STAGES_FROM_SPEC`
- `PRODUCT_MODULE_STAGE_DEPENDENCIES` / `PRODUCT_MODULE_STAGE_DEPENDENCIES_FROM_SPEC`
- `MODULE_PRODUCER_STAGES`

## Registry rules

- Module Registry unique; Stage Registry unique
- All stages must be legal catalog keys
- Producer stages ⊆ Planning closure
- Result dependencies ⊆ Planning closure
- Frontend must not maintain a fourth mapping copy
- Legacy constants retained only via compatibility adapters

## WholeBookModuleRunner (protocol)

`validate_request` · `prepare_context` · `execute` · `validate_output` · `collect_evidence` · `build_candidates` · `build_checkpoint` · `resume` · `health_check`

Runner: no ORM / License / Credential; Provider Gateway only; structured DTOs; no confirm/lock/canonical; no raw model JSON as Asset; supports cancel + budget; binds Prompt Pack version. Phase 2B-P: Protocol + Fake Runner only.
