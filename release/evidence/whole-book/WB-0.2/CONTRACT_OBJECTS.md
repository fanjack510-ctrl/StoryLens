# Whole-Book Contract V1 Objects

Contract: `whole_book_contract_v1`

Migration needs summarized from `V1_PERSISTENCE_MAPPING.md`.

## BookSnapshotMetadataV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `snapshot_id`: type=integer; nullable=False
  - `book_id`: type=integer; nullable=False
  - `snapshot_version`: type=integer; nullable=False
  - `status`: type=#/$defs/SnapshotStatus; nullable=False
  - `content_hash`: type=string; nullable=False
  - `chapter_count`: type=integer; nullable=False
  - `paragraph_count`: type=integer; nullable=False
  - `character_count`: type=integer; nullable=False
  - `created_at`: type=string; nullable=False
  - `completed_at`: type=[{'format': 'date-time', 'type': 'string'}, {'type': 'null'}]; nullable=True
- Validation: pydantic `extra=forbid` + model validators

## SnapshotChapterV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `snapshot_chapter_id`: type=integer; nullable=False
  - `snapshot_id`: type=integer; nullable=False
  - `chapter_id`: type=integer; nullable=False
  - `chapter_index`: type=integer; nullable=False
  - `title`: type=string; nullable=True
  - `chapter_hash`: type=string; nullable=False
  - `paragraph_count`: type=integer; nullable=False
  - `character_count`: type=integer; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## SnapshotParagraphV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `snapshot_paragraph_id`: type=integer; nullable=False
  - `snapshot_id`: type=integer; nullable=False
  - `snapshot_chapter_id`: type=integer; nullable=False
  - `chapter_id`: type=integer; nullable=False
  - `chapter_index`: type=integer; nullable=False
  - `paragraph_index`: type=integer; nullable=False
  - `global_paragraph_index`: type=integer; nullable=False
  - `text`: type=string; nullable=False
  - `text_hash`: type=string; nullable=False
  - `character_count`: type=integer; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## SnapshotEvidenceLocatorV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `locator_version`: type=string; nullable=True
  - `snapshot_id`: type=integer; nullable=False
  - `snapshot_chapter_id`: type=integer; nullable=False
  - `snapshot_paragraph_id`: type=integer; nullable=False
  - `chapter_id`: type=integer; nullable=False
  - `chapter_index`: type=integer; nullable=False
  - `paragraph_index`: type=integer; nullable=False
  - `global_paragraph_index`: type=integer; nullable=False
  - `start_offset`: type=integer; nullable=False
  - `end_offset`: type=integer; nullable=False
  - `quote_text`: type=string; nullable=False
  - `quote_hash`: type=string; nullable=False
  - `paragraph_text_hash`: type=string; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## WholeBookRunV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `run_id`: type=integer; nullable=False
  - `book_id`: type=integer; nullable=False
  - `snapshot_id`: type=integer; nullable=False
  - `mode`: type=#/$defs/WholeBookMode; nullable=False
  - `status`: type=#/$defs/WholeBookRunStatus; nullable=False
  - `current_stage_code`: type=[{'type': 'string'}, {'type': 'null'}]; nullable=True
  - `idempotency_key`: type=string; nullable=False
  - `engine_id`: type=string; nullable=False
  - `engine_version`: type=string; nullable=False
  - `contract_version`: type=string; nullable=True
  - `prompt_version`: type=[{'maxLength': 128, 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `result_origin`: type=#/$defs/ResultOrigin; nullable=False
  - `input_usage`: type=#/$defs/WholeBookInputUsageV1; nullable=False
  - `consent_id`: type=[{'exclusiveMinimum': 0, 'type': 'integer'}, {'type': 'null'}]; nullable=True
  - `cost_policy_id`: type=[{'exclusiveMinimum': 0, 'type': 'integer'}, {'type': 'null'}]; nullable=True
  - `created_at`: type=string; nullable=False
  - `started_at`: type=[{'format': 'date-time', 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `paused_at`: type=[{'format': 'date-time', 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `completed_at`: type=[{'format': 'date-time', 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `failed_at`: type=[{'format': 'date-time', 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `cancelled_at`: type=[{'format': 'date-time', 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `failure_code`: type=[{'maxLength': 128, 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `failure_message_safe`: type=[{'maxLength': 500, 'type': 'string'}, {'type': 'null'}]; nullable=True
- Validation: pydantic `extra=forbid` + model validators

## WholeBookWindowV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `window_id`: type=integer; nullable=False
  - `run_id`: type=integer; nullable=False
  - `snapshot_id`: type=integer; nullable=False
  - `window_index`: type=integer; nullable=False
  - `first_global_paragraph_index`: type=integer; nullable=False
  - `last_global_paragraph_index`: type=integer; nullable=False
  - `chapter_start_index`: type=integer; nullable=False
  - `chapter_end_index`: type=integer; nullable=False
  - `paragraph_count`: type=integer; nullable=False
  - `character_count`: type=integer; nullable=False
  - `token_estimate`: type=integer; nullable=False
  - `overlap_before_paragraphs`: type=integer; nullable=False
  - `overlap_after_paragraphs`: type=integer; nullable=False
  - `window_hash`: type=string; nullable=False
  - `idempotency_key`: type=string; nullable=False
  - `status`: type=#/$defs/WholeBookUnitStatus; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## WholeBookWindowCoverageV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `snapshot_id`: type=integer; nullable=False
  - `run_id`: type=integer; nullable=False
  - `total_paragraphs`: type=integer; nullable=False
  - `covered_unique_paragraphs`: type=integer; nullable=False
  - `duplicated_paragraphs`: type=integer; nullable=False
  - `uncovered_paragraphs`: type=integer; nullable=False
  - `coverage_ratio`: type=number; nullable=False
  - `order_valid`: type=boolean; nullable=False
  - `first_global_paragraph_index`: type=[{'minimum': 0, 'type': 'integer'}, {'type': 'null'}]; nullable=True
  - `last_global_paragraph_index`: type=[{'minimum': 0, 'type': 'integer'}, {'type': 'null'}]; nullable=True
- Validation: pydantic `extra=forbid` + model validators

## AnalysisProvenanceV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `provenance_version`: type=string; nullable=True
  - `run_id`: type=integer; nullable=False
  - `snapshot_id`: type=integer; nullable=False
  - `window_ids`: type=array; nullable=True
  - `engine_id`: type=string; nullable=False
  - `engine_version`: type=string; nullable=False
  - `contract_version`: type=string; nullable=True
  - `prompt_version`: type=[{'maxLength': 128, 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `provider_id`: type=[{'maxLength': 128, 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `model_name`: type=[{'maxLength': 128, 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `result_origin`: type=#/$defs/ResultOrigin; nullable=False
  - `source_mode`: type=#/$defs/WholeBookMode; nullable=False
  - `deterministic`: type=boolean; nullable=False
  - `config_hashes`: type=object; nullable=True
  - `generated_at`: type=string; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## WholeBookInputUsageV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `full_text_snapshot_used`: type=boolean; nullable=False
  - `chapter_analysis_asset_count`: type=integer; nullable=False
  - `reader_journey_asset_count`: type=integer; nullable=False
  - `confirmed_whole_book_asset_count`: type=integer; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## WholeBookWindowAnalysisRequestV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `contract_version`: type=string; nullable=True
  - `run`: type=#/$defs/WholeBookRunV1; nullable=False
  - `snapshot`: type=#/$defs/BookSnapshotMetadataV1; nullable=False
  - `window`: type=#/$defs/WholeBookWindowV1; nullable=False
  - `paragraphs`: type=array; nullable=False
  - `existing_confirmed_entities`: type=array; nullable=True
  - `existing_confirmed_assets`: type=array; nullable=True
- Validation: pydantic `extra=forbid` + model validators

## CandidateEvidenceV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `evidence_key`: type=string; nullable=False
  - `locator`: type=#/$defs/SnapshotEvidenceLocatorV1; nullable=False
  - `confidence`: type=number; nullable=False
  - `note_safe`: type=[{'maxLength': 500, 'type': 'string'}, {'type': 'null'}]; nullable=True
- Validation: pydantic `extra=forbid` + model validators

## CandidateEntityAliasV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `name`: type=string; nullable=False
  - `confidence`: type=number; nullable=False
  - `evidence_keys`: type=array; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## CandidateEntityV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `candidate_key`: type=string; nullable=False
  - `entity_type`: type=#/$defs/EntityType; nullable=False
  - `canonical_name`: type=string; nullable=False
  - `aliases`: type=array; nullable=True
  - `confidence`: type=number; nullable=False
  - `evidence_keys`: type=array; nullable=False
  - `attributes`: type=object; nullable=True
- Validation: pydantic `extra=forbid` + model validators

## CandidateAssetV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `candidate_key`: type=string; nullable=False
  - `asset_type`: type=string; nullable=False
  - `title`: type=string; nullable=False
  - `summary`: type=string; nullable=False
  - `payload`: type=object; nullable=True
  - `confidence`: type=number; nullable=False
  - `subject_entity_keys`: type=array; nullable=True
  - `evidence_keys`: type=array; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## CandidateNarrativeRefV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `kind`: type=#/$defs/NarrativeRefKind; nullable=False
  - `candidate_key`: type=string; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## CandidateRelationV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `candidate_key`: type=string; nullable=False
  - `relation_type`: type=string; nullable=False
  - `subject`: type=#/$defs/CandidateNarrativeRefV1; nullable=False
  - `object`: type=#/$defs/CandidateNarrativeRefV1; nullable=False
  - `confidence`: type=number; nullable=False
  - `evidence_keys`: type=array; nullable=False
  - `attributes`: type=object; nullable=True
- Validation: pydantic `extra=forbid` + model validators

## WholeBookWindowAnalysisResponseV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `contract_version`: type=string; nullable=True
  - `run_id`: type=integer; nullable=False
  - `snapshot_id`: type=integer; nullable=False
  - `window_id`: type=integer; nullable=False
  - `entities`: type=array; nullable=True
  - `assets`: type=array; nullable=True
  - `evidences`: type=array; nullable=True
  - `relations`: type=array; nullable=True
  - `warnings`: type=array; nullable=True
  - `provenance`: type=#/$defs/AnalysisProvenanceV1; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## PersistedNarrativeEntityV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `entity_id`: type=integer; nullable=False
  - `snapshot_id`: type=integer; nullable=False
  - `entity_type`: type=#/$defs/EntityType; nullable=False
  - `canonical_name`: type=string; nullable=False
  - `aliases`: type=array; nullable=True
  - `state`: type=#/$defs/ArtifactState; nullable=False
  - `confidence`: type=number; nullable=False
  - `current_version_no`: type=integer; nullable=False
  - `created_by_run_id`: type=integer; nullable=False
  - `updated_by_run_id`: type=[{'exclusiveMinimum': 0, 'type': 'integer'}, {'type': 'null'}]; nullable=True
  - `user_confirmed_at`: type=[{'format': 'date-time', 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `evidence_ids`: type=array; nullable=True
  - `provenance`: type=#/$defs/AnalysisProvenanceV1; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## PersistedNarrativeAssetV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `asset_id`: type=integer; nullable=False
  - `snapshot_id`: type=integer; nullable=False
  - `asset_type`: type=string; nullable=False
  - `title`: type=string; nullable=False
  - `state`: type=#/$defs/ArtifactState; nullable=False
  - `confidence`: type=number; nullable=False
  - `subject_entity_ids`: type=array; nullable=True
  - `current_version_id`: type=integer; nullable=False
  - `created_by_run_id`: type=integer; nullable=False
  - `updated_by_run_id`: type=[{'exclusiveMinimum': 0, 'type': 'integer'}, {'type': 'null'}]; nullable=True
  - `evidence_ids`: type=array; nullable=True
  - `provenance`: type=#/$defs/AnalysisProvenanceV1; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## NarrativeAssetVersionV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `asset_version_id`: type=integer; nullable=False
  - `asset_id`: type=integer; nullable=False
  - `version_no`: type=integer; nullable=False
  - `state`: type=#/$defs/ArtifactState; nullable=False
  - `payload`: type=object; nullable=True
  - `payload_hash`: type=string; nullable=False
  - `source_run_id`: type=integer; nullable=False
  - `source_window_ids`: type=array; nullable=True
  - `evidence_ids`: type=array; nullable=True
  - `created_by`: type=string; nullable=False
  - `created_at`: type=string; nullable=False
  - `is_current`: type=boolean; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## PersistedEvidenceV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `evidence_id`: type=integer; nullable=False
  - `snapshot_id`: type=integer; nullable=False
  - `locator`: type=#/$defs/SnapshotEvidenceLocatorV1; nullable=False
  - `state`: type=#/$defs/EvidenceState; nullable=False
  - `confidence`: type=number; nullable=False
  - `created_by_run_id`: type=integer; nullable=False
  - `created_at`: type=string; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## NarrativeRefV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `kind`: type=#/$defs/NarrativeRefKind; nullable=False
  - `id`: type=integer; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## PersistedNarrativeRelationV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `relation_id`: type=integer; nullable=False
  - `snapshot_id`: type=integer; nullable=False
  - `relation_type`: type=string; nullable=False
  - `subject`: type=#/$defs/NarrativeRefV1; nullable=False
  - `object`: type=#/$defs/NarrativeRefV1; nullable=False
  - `state`: type=#/$defs/ArtifactState; nullable=False
  - `confidence`: type=number; nullable=False
  - `current_version_id`: type=integer; nullable=False
  - `evidence_ids`: type=array; nullable=False
  - `created_by_run_id`: type=integer; nullable=False
  - `provenance`: type=#/$defs/AnalysisProvenanceV1; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## AnalysisConflictV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `conflict_id`: type=integer; nullable=False
  - `snapshot_id`: type=integer; nullable=False
  - `target`: type=#/$defs/NarrativeRefV1; nullable=False
  - `confirmed_version_id`: type=integer; nullable=False
  - `proposed_version_id`: type=integer; nullable=False
  - `conflict_type`: type=string; nullable=False
  - `status`: type=#/$defs/ConflictStatus; nullable=False
  - `summary_safe`: type=string; nullable=False
  - `created_by_run_id`: type=integer; nullable=False
  - `created_at`: type=string; nullable=False
  - `resolved_at`: type=[{'format': 'date-time', 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `resolution_note`: type=[{'maxLength': 1000, 'type': 'string'}, {'type': 'null'}]; nullable=True
- Validation: pydantic `extra=forbid` + model validators

## BookOverviewClaimV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `claim_key`: type=string; nullable=False
  - `availability`: type=#/$defs/OverviewClaimAvailability; nullable=False
  - `summary`: type=[{'maxLength': 5000, 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `confidence`: type=[{'maximum': 1.0, 'minimum': 0.0, 'type': 'number'}, {'type': 'null'}]; nullable=True
  - `evidence_ids`: type=array; nullable=True
  - `supporting_asset_ids`: type=array; nullable=True
  - `conflict_ids`: type=array; nullable=True
- Validation: pydantic `extra=forbid` + model validators

## BookOverviewResultV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `result_version`: type=string; nullable=True
  - `contract_version`: type=string; nullable=True
  - `run_id`: type=integer; nullable=False
  - `book_id`: type=integer; nullable=False
  - `snapshot_id`: type=integer; nullable=False
  - `mode`: type=#/$defs/WholeBookMode; nullable=False
  - `result_origin`: type=#/$defs/ResultOrigin; nullable=False
  - `status`: type=string; nullable=False
  - `claims`: type=array; nullable=False
  - `important_entity_ids`: type=array; nullable=True
  - `key_event_asset_ids`: type=array; nullable=True
  - `coverage`: type=#/$defs/WholeBookWindowCoverageV1; nullable=False
  - `input_usage`: type=#/$defs/WholeBookInputUsageV1; nullable=False
  - `warnings`: type=array; nullable=True
  - `provenance`: type=#/$defs/AnalysisProvenanceV1; nullable=False
  - `created_at`: type=string; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## WholeBookSynthesisRequestV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `contract_version`: type=string; nullable=True
  - `run`: type=#/$defs/WholeBookRunV1; nullable=False
  - `snapshot`: type=#/$defs/BookSnapshotMetadataV1; nullable=False
  - `coverage`: type=#/$defs/WholeBookWindowCoverageV1; nullable=False
  - `entities`: type=array; nullable=True
  - `assets`: type=array; nullable=True
  - `relations`: type=array; nullable=True
  - `evidences`: type=array; nullable=True
  - `open_conflicts`: type=array; nullable=True
- Validation: pydantic `extra=forbid` + model validators

## WholeBookSynthesisResponseV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public+Private Wire
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `contract_version`: type=string; nullable=True
  - `result`: type=#/$defs/BookOverviewResultV1; nullable=False
- Validation: pydantic `extra=forbid` + model validators

## WholeBookRunStageV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public-only (not in wire identity hash)
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `stage_id`: type=integer; nullable=False
  - `run_id`: type=integer; nullable=False
  - `stage_code`: type=string; nullable=False
  - `sequence`: type=integer; nullable=False
  - `status`: type=#/$defs/WholeBookStageStatus; nullable=False
  - `progress_current`: type=integer; nullable=False
  - `progress_total`: type=integer; nullable=False
  - `started_at`: type=[{'format': 'date-time', 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `completed_at`: type=[{'format': 'date-time', 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `last_error_code`: type=[{'maxLength': 128, 'type': 'string'}, {'type': 'null'}]; nullable=True
  - `last_error_message_safe`: type=[{'maxLength': 500, 'type': 'string'}, {'type': 'null'}]; nullable=True
- Validation: pydantic `extra=forbid` + model validators

## WholeBookCheckpointV1

- Function: Wire/persistence DTO for whole-book analysis V1
- Public / Private: Public-only (not in wire identity hash)
- WB-0.4 Migration: see V1_PERSISTENCE_MAPPING.md
- Lifecycle: contract-validated object; no DB write in WB-0.2
- Fields:
  - `checkpoint_id`: type=integer; nullable=False
  - `run_id`: type=integer; nullable=False
  - `stage_code`: type=string; nullable=False
  - `checkpoint_key`: type=string; nullable=False
  - `sequence_no`: type=integer; nullable=False
  - `completed_unit_count`: type=integer; nullable=False
  - `last_completed_window_id`: type=[{'exclusiveMinimum': 0, 'type': 'integer'}, {'type': 'null'}]; nullable=True
  - `payload_hash`: type=string; nullable=False
  - `checkpoint_payload`: type=object; nullable=True
  - `created_at`: type=string; nullable=False
- Validation: pydantic `extra=forbid` + model validators

