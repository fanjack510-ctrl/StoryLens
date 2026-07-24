# Phase 2B Integration Report

**Change:** CHG-20260723-040
**Branch:** `integration/narrative-phase2b`
**Worktree:** `D:\Dstorylens-wt-narrative-phase2b-integration`
**Source commit:** `f2ce37afd75e5773c4a30c0cf005603610ebac60`
**VERSION:** 1.0.5 (unchanged)

## Scope

Cherry-pick Agent P → Agent Q → Agent R (no merge of agent branches), wire composition root in `private_whole_book_analysis_runtime.py`, run Fake Provider E2E tests, document boundaries.
**Not in scope:** formal prompts, real model calls, production whole-book run, new migrations/tables, VERSION bump, push/build/publish.

## Merge order (cherry-pick)

1. **Agent P** (`feature/narrative-phase2b-engine-runtime`) — `b6c60b5`, `209521f`, `dbe6aca` — engine manifest loader, provider gateway, fake private engine, runtime adapter
2. **Agent Q** (`feature/narrative-phase2b-context-evidence`) — `f522352`, `bfbee8e`, `5f85c9c` — context pipeline, evidence validator, bundle builder
3. **Agent R** (`feature/narrative-phase2b-core-modules`) — `f63b9f6`, `35fee2b`, `856d18e` — first-four module runners, output validator, candidate builder, evaluation harness

Cherry-picks applied on integration branch; agent worktrees untouched.

## Integration-only deliverables

| Area | Integration ownership |
|------|----------------------|
| Composition root | `private_whole_book_analysis_runtime.py` — wires P + Q + R |
| Factory | `create_private_whole_book_analysis_runtime` (`production=True` raises) |
| Bundle mapper | `WholeBookContextBundleMapper` — explicit contract transport |
| Persistence boundary | `CandidatePersistenceAdapter` + `RecordingCandidatePersistenceSink` (no ORM write) |
| E2E | `test_narrative_phase2b_integration.py` (8 scenarios) |
| Docs | This report + companion integration docs (CHG-040) |

## Corrections at merge boundary

- Unique composition root: `PrivateWholeBookAnalysisRuntime` (+ aliases `PrivateEngineRuntimeContainer`, `PrivateWholeBookRuntime`)
- `WholeBookContextBundleMapper` freezes `ContextBundle` as cross-component contract; no implicit field compatibility
- `ParagraphGroupingPolicy` versioned config; defaults `max=40`, `overlap=2` are initial only (`defaults_are_initial_only`)
- `DefaultEvidenceValidatorRuntimeAdapter` bridges Agent R Protocol → Agent Q `DefaultEvidenceValidator`
- `ModuleProviderExecutionAdapter` keeps Protocol; `DefaultWholeBookProviderGateway` + `FakeProviderAdapter` from Agent P
- Enhanced fixtures via `AuxiliaryContextSource`; Scene ORM E2E not covered

## Production isolation (unchanged)

- `PRO_CAPABILITIES_SHIPPED=false`
- `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`
- `PRODUCTION_DEFAULT_ENGINE_ID=None`
- `WHOLE_BOOK_MOCK_LAB_ENABLED=false`
- No migrations / Pattern tables / VERSION bump

See also: [phase2b-production-isolation-verification.md](./phase2b-production-isolation-verification.md), [phase2b-known-limitations.md](./phase2b-known-limitations.md).
