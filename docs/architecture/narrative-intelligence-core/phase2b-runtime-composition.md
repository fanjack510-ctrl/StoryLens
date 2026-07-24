# Phase 2B Runtime Composition

**Change:** CHG-20260723-040
**Module:** `apps/api/app/narrative_core/services/private_whole_book_analysis_runtime.py`

## Composition root

`PrivateWholeBookAnalysisRuntime` is the single wiring point for Agent P (engine/provider), Agent Q (context/evidence), and Agent R (modules). Integration constructs it via `create_private_whole_book_analysis_runtime(...)`; tests inject isolated instances. Aliases: `PrivateEngineRuntimeContainer`, `PrivateWholeBookRuntime`.

Schema: `storylens.phase2b.private_analysis_runtime` / version `1.0.0`.

### Agent P (engine / provider)

| Component | Role |
|-----------|------|
| `DefaultPrivateWholeBookEngineLoader` | Load signed Fake engine package |
| `PrivateWholeBookEngineRuntimeAdapter` | Request/result translation, health check |
| `DefaultWholeBookProviderGateway` | Provider registry + routing |
| `FakeProviderAdapter` | Synthetic provider responses |
| `NoCredentialFakeResolver` | No credential reads in Fake path |
| `FakePrivateWholeBookEngine` | Non-production engine stub |
| `FakePromptPackServiceManifest` | Fake prompt pack (not formal prompts) |

### Agent Q (context / evidence)

| Component | Role |
|-----------|------|
| `DefaultWholeBookContextPipeline` | Snapshot → context units |
| `WholeBookContextBundleBuilder` | Native/Enhanced bundle assembly |
| `ParagraphGroupingPolicy` | Versioned grouping config |
| `HierarchicalContextPlanner` | Multi-level context planning |
| `DefaultEvidenceValidator` | Paragraph-hash evidence checks |
| `EvidenceCandidateBuilder` / `EvidenceCoverageCalculator` | Evidence pipeline helpers |
| `AuxiliaryContextSource` | Enhanced-mode aux fixtures |

### Agent R (modules)

| Component | Role |
|-----------|------|
| `WholeBookModuleSpecRegistry` | First-four module specs |
| `build_first_four_fake_runners` | Fake runners per module key |
| `DefaultModuleOutputValidator` | Schema/ref/evidence validation |
| `ModuleCandidateBuilder` | Candidate command assembly |
| `ModuleCheckpointBuilder` / `ModuleCheckpointValidator` | Checkpoint/resume |
| `WholeBookEvaluationHarness` | Evaluation fixtures |

### Integration adapters

| Adapter | Bridges |
|---------|---------|
| `WholeBookContextBundleMapper` | `WholeBookContextBundle` ↔ contract `ContextBundle` |
| `DefaultEvidenceValidatorRuntimeAdapter` | R Protocol → Q `DefaultEvidenceValidator` |
| `CandidatePersistenceAdapter` | `RecordingCandidatePersistenceSink` (record only) |

## Factory policy

- `create_private_whole_book_analysis_runtime(production=True)` raises immediately
- `production=False`, `synthetic=True`, `non_production=True` enforced in `__post_init__`
- No global mutable production singleton
- Optional `session`, `package_root`, `grouping_policy`, `auxiliary_source`, `persistence` injection

## Pipeline entry points

| Method | Path |
|--------|------|
| `build_native_context_bundle` | Snapshot → units → mapper → contract bundle |
| `build_enhanced_context_bundle` | Native + aux source; degraded coverage on stale/missing |
| `prepare_engine_packages` | Write signed Fake engine + prompt pack (test only) |
| `execute_module_pipeline` | Runner → provider → output validator → candidate builder → persistence sink |
| `assert_production_isolation` | Prove gates reject Fake runtime/engine/pack |

## Module pipeline order

On `execute_module_pipeline`:

1. Resolve contract bundle from `context_bundle_ref`
2. `make_execution_request` + `assert_request_has_no_forbidden_fields`
3. `runtime_adapter.translate_request` + health check
4. `runner.execute` via `ModuleProviderExecutionAdapter` → gateway → Fake provider
5. `runtime_adapter.translate_result`
6. `output_validator.validate` (Q evidence via adapter)
7. `candidate_builder.build` → `persistence.persist_commands` (record only when accepted)
