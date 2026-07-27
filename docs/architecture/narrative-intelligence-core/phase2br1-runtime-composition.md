# Phase 2B-R1 Runtime Composition

## Public root

`PrivateWholeBookLiveReadinessRuntime` (`private_whole_book_live_readiness_runtime.py`)

| Port (V) | Adapter | U service |
|----------|---------|-----------|
| Preflight | `PrivateLabPreflightServiceAdapter` | Snapshot/env/module + credential status |
| Estimate | `PrivateLabEstimateServiceAdapter` | `WholeBookProviderEstimateService` + Manifest |
| Consent | `PrivateLabConsentServiceAdapter` | `PrivateEngineDataTransferConsentGuard` + BudgetGuard |
| Provider | `PrivateLabProviderExecutionServiceAdapter` | `DefaultWholeBookProviderGateway` + Bailian |

## Private root

`compose_private_lab_runtime` → `PrivateWholeBookLabRuntimeContainer`

- `PrivateProviderInputBundleResolver`
- Four module runners (overview → structure → chapter_functions → storylines)
- Optional message assembly injected into pipeline (no circular import)

## Isolation rules

1. Runtime depends on Protocols; no global mutable singleton for production
2. Tests construct isolated runtimes
3. Production must not construct enabled Lab runtime
4. Credential only at Provider execute boundary
5. Candidate persistence never sees credentials
6. Context resolver never touches License
7. Provider adapter never touches ORM
