# Phase 2B Runtime Adapter

`PrivateWholeBookEngineRuntimeAdapter` connects Phase 1C WholeBook concerns to `storylens.private_engine.v1` DTOs.

## Methods

`validate_execution_request` · `translate_request` · `execute` · `resume` · `cancel` · `translate_result` · `health_check`

## Boundaries

- No ORM / License / Credential reads
- Accepts `context_bundle_ref` only (not unbounded full text)
- Requires Snapshot + configuration fingerprint binding
- Prompt Pack version checked on resume
- BudgetGuard + cancellation_ref propagation
- Result passes public DTO guard; never writes Assets; never becomes canonical
- This phase executes `FakePrivateWholeBookEngine` only
