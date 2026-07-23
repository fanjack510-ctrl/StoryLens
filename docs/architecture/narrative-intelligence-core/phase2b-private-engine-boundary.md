# Phase 2B Private Engine Boundary

CHG-20260723-036. Protocol id: `storylens.private_engine.v1`.

## Three layers

| Layer | Location | Allowed in public repo |
|-------|----------|------------------------|
| **Public Application** | App + `private_engine_contract/` | Protocol, Manifest, DTO, Loader interface, Provider Gateway Protocol, validators, Fake/Mock, contract tests, API adapters, error codes |
| **Private Engine** | Sidecar / private package / remote service / hybrid | Formal algorithms, formal prompts, proprietary weights/scoring/routing, private eval corpora |
| **Provider** | Via `WholeBookProviderGateway` only | Model I/O behind gateway; credentials via existing Credential Service |

## Public must not contain

Formal analysis algorithms; formal prompt bodies; prompt assembly rules; proprietary weights/scoring; proprietary model-routing strategies; private evaluation sample full text.

## Private delivery (deferred)

`local_private_sidecar` | `local_private_package` | `remote_private_service` | `hybrid_private_engine` — Phase 2B-P freezes interfaces only; commercial packaging is later.

## Client protection is not absolute

Client binaries cannot be guaranteed “non-decompilable.” Core algorithms and formal prompts **must not** rely on client obfuscation alone. High-value rules belong in private sidecar or server-side execution.

## Module forbidden actions

Modules must not call Bailian/OpenAI/llama-server directly, read API keys, or assemble HTTP requests inside module code. All inference goes through Provider Gateway.

## Code paths

- Public contract: `apps/api/app/narrative_core/private_engine_contract/`
- FE types only: `apps/desktop/src/features/wholeBook/privateEngineContracts/`
- Formal private code must not live under the public contract directories.
