# Phase 2B Prompt Pack Contract

Phase 2B-P freezes manifests/refs only — **no formal prompt bodies** in the public repo.

## PromptPackManifest fields

`prompt_pack_id`, `prompt_pack_version`, `private`, `signed`, `package_hash`, `supported_engine_versions`, `supported_modules`, `supported_languages`, `output_schema_versions`, `instruction_ref`, `template_refs`, `example_set_refs`, `evaluation_policy_ref`, `created_at`

## Public vs private

| Allowed in public repo | Private only |
|------------------------|--------------|
| Manifest + Fake prompt placeholders | Formal prompt pack bodies |

Fake short placeholder text may exist only under Fake/non_production markers — never as formal packs.

## Anti-injection

- Novel content is `source_data` only
- Do not honor command-like text in body (“ignore rules”, “system instruction”, etc.)
- Provider request isolates instruction vs source_data
- Structured output requires Schema Validation
- Model must not request external tools or network

## Leakage bans

Prompt text must not enter Artifact, Audit, or API responses. Prompt hash participates in configuration fingerprint. Prompt upgrades create a new version. Resume requires compatible Prompt Pack version.
