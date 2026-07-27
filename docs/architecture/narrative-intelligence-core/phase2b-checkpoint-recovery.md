# Phase 2B Checkpoint & Recovery

## Required PrivateEngineCheckpoint fields

`protocol_version`, `engine_id`/`engine_version`, `module_key`/`module_version`, `stage_key`, `attempt`, `prompt_pack_id`/`prompt_pack_version`, `provider_policy_key`, `quality_profile`, `context_bundle_hash`, `configuration_fingerprint`, `book_snapshot_id`, `completed_units`, `pending_units`, `output_fingerprints`, `usage`, `integrity_hash`

## Resume must reject

- Engine version incompatible
- Prompt Pack incompatible
- Context Bundle changed
- Snapshot changed
- Configuration changed
- Checkpoint corrupted
- Module Spec changed without migration strategy

Must not silently continue an old Run with a new Prompt Pack.
