# Phase 2B Module Runtime Implementation

## Components

1. **WholeBookModuleSpecRegistry** — register/get/list/validate + planning/producer/result views.
2. **BaseWholeBookModuleRunner** — Protocol methods; Context Bundle validation; Prompt Pack binding; cancel/budget propagation.
3. **ModuleProviderExecutionAdapter** — calls `WholeBookProviderGateway` only; Fake gateway in this Change.
4. **Four Fake runners** — synthetic/empty/fixture outputs for `book_overview`, `structure_stages`, `chapter_functions`, `storylines`.
5. **DefaultModuleOutputValidator** — ordered validation before Candidate build.
6. **ModuleCandidateBuilder** — command/DTO only.
7. **Checkpoint builder/validator** — resume compatibility gates.
8. **Evaluation harness** — synthetic contract metrics + metamorphic identity checks.

## Runtime rules

- Runner depends on Protocols, not ORM / License / Credential / concrete Provider SDK.
- Prompt Pack version required on request.
- Context Bundle must validate before execute.
- Budget denied / cancel → no Candidate write.
- Provider failure does not fabricate success outputs.
- Fake outputs always marked `fake` / `synthetic` / `non-production`.
