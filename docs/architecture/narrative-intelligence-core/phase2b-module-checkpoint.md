# Phase 2B Module Checkpoint

Builder: `ModuleCheckpointBuilder`  
Validator: `ModuleCheckpointValidator` (wraps Phase 2B-P `assert_checkpoint_compatible`)

## Required fields

protocol · engine · module/version · stage · attempt · prompt pack · provider policy · quality profile · context bundle hash · configuration fingerprint · snapshot · completed/pending units · output fingerprints · usage · integrity hash

## Resume rejects

- Engine version incompatible
- Prompt Pack changed
- Context Bundle changed
- Snapshot changed
- Configuration changed
- Integrity failed
- Module Spec changed without migration

No silent Prompt Pack upgrade. Resume dedupes by output fingerprint (identity/hash stability only).
