# Phase 2B Candidate Persistence

First four modules may create only:

- candidate Asset Version
- candidate Relation Version
- Evidence
- Conflict Candidate
- Stage Artifact

## Forbidden auto actions

No auto confirm · no auto corrected · no auto lock · no canonical overwrite · no delete of user versions · no mutation of old Snapshot Evidence

## Required provenance on every write

`run_id`, `run_stage_id`, `book_snapshot_id`, `engine_id`/`engine_version`, `module_key`/`module_version`, `prompt_pack_id`/`prompt_pack_version`, `configuration_fingerprint`, `output_fingerprint`, `evidence_refs`, `mock=false`, `private_engine=true`

Production real runs remain disabled; Phase 2B-P freezes fields + Fake fixtures only.
