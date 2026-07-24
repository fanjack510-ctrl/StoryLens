# Phase 2B Fake Prompt Pack

Service: `apps/api/app/narrative_core/services/fake_prompt_pack.py`

## Surfaces

- `FakePromptPackServiceManifest`
- `FakePromptInstructionRefs` (`fake://book-overview/system`, …)
- `FakeResponseSchemaRefs` (`dto://BookOverviewResultDto`, …)

## Rules

1. Hash + HMAC test signature are deterministic and testable.
2. `prompt_hash` participates in fingerprint (`prompt_pack_hash=…`).
3. Compatible with first-four modules.
4. Locales `zh-CN` / `en-US` and source languages are enumerable for tests.
5. No Artifact/Audit bodies; no frontend emission of pack bodies.
6. `reject_fake_prompt_pack_in_production(production=True)` raises.
7. No formal analysis instruction text.
