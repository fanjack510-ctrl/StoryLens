# Phase 2B Provider & Runner Integration

**Change:** CHG-20260723-040
**Modules:** `whole_book_provider_gateway.py`, `whole_book_module_runner.py`, `private_whole_book_analysis_runtime.py`

## Provider stack (Agent P)

| Component | Role |
|-----------|------|
| `DefaultWholeBookProviderGateway` | Registry + route selection |
| `FakeProviderAdapter` | Synthetic module outputs; no network |
| `NoCredentialFakeResolver` | Fake path never reads credentials |
| `ModuleProviderExecutionAdapter` | Runner Protocol → gateway (unchanged interface) |

Integration wires gateway at runtime init; registers `FakeProviderAdapter` on gateway registry. Test `test_provider_gateway_is_agent_p_default` asserts gateway and adapter types.

## Execution path

```
execute_module_pipeline
  → runtime_adapter.translate_request
  → runner.execute(translated)
      → provider_adapter.invoke (ModuleProviderExecutionAdapter)
          → gateway.route → FakeProviderAdapter
  → runtime_adapter.translate_result
  → output_validator.validate
```

`provider_policy` dict controls Fake behavior:

- `provider_kind: "fake"`
- `synthetic_output`: mode markers (`overview_mode`, `structure_mode`, `chapter_mode`, `storyline_type`, rejection markers, `skip_provider`, etc.)
- `model_route`: routing label only; no real model

## Forbidden in Fake E2E results

`ModulePipelineResultDTO` flags (always false for real operations in Integration):

| Flag | Expected |
|------|----------|
| `network` | `False` |
| `model_called` | `False` |
| `formal_prompt` | `False` |
| `canonical` | `False` |
| `asset_written` | `False` |

Usage dict tagged `fake=True`, `synthetic=True`.

## Engine package path

`prepare_engine_packages(package_root)` writes signed Fake engine + prompt pack, loads via `DefaultPrivateWholeBookEngineLoader(production=False)`. Production loader rejects Fake engine id — verified in `assert_production_isolation`.

## Static security scan

Integration test scans Phase 2B Python paths for credential/network/provider SDK patterns; allowlisted guard/test/fake lines excluded. Complements Agent P credential boundary docs.

See [phase2b-provider-gateway-implementation.md](./phase2b-provider-gateway-implementation.md), [phase2b-credential-boundary.md](./phase2b-credential-boundary.md).
