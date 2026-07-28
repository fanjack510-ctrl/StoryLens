# Whole-Book Contract V1 → Persistence Mapping

**Contract:** `whole_book_contract_v1`  
**Step:** WB-0.2-DATA-CONTRACTS  
**Change:** CHG-20260728-003  
**Rule:** Contract semantics are frozen. DB gaps are recorded; **no migration in this Step**.

Mapping Status values: `reuse` | `adapter` | `extend_later` | `new_in_wb_0_4` | `not_applicable`

| Contract Object | Contract Field | Existing Model | Existing Field | Mapping Status | Migration Required | Notes |
|---|---|---|---|---|---|---|
| BookSnapshotMetadataV1 | snapshot_id | BookSnapshot | id | reuse | NO | |
| BookSnapshotMetadataV1 | book_id | BookSnapshot | book_id | reuse | NO | |
| BookSnapshotMetadataV1 | snapshot_version | — | — | new_in_wb_0_4 | YES | No dedicated version column today |
| BookSnapshotMetadataV1 | status | BookSnapshot | snapshot_status | adapter | NO | Enum string align (`building`/`completed`/`invalid`) |
| BookSnapshotMetadataV1 | content_hash | BookSnapshot | content_hash | reuse | NO | |
| BookSnapshotMetadataV1 | chapter_count | BookSnapshot | chapter_count | reuse | NO | |
| BookSnapshotMetadataV1 | paragraph_count | BookSnapshot | paragraph_count | reuse | NO | |
| BookSnapshotMetadataV1 | character_count | BookSnapshot | character_count | reuse | NO | |
| BookSnapshotMetadataV1 | created_at | BookSnapshot | created_at | reuse | NO | |
| BookSnapshotMetadataV1 | completed_at | — | — | new_in_wb_0_4 | YES | Status-derived today; needs explicit timestamp |
| SnapshotChapterV1 | snapshot_chapter_id | BookSnapshotChapter | id | reuse | NO | |
| SnapshotChapterV1 | snapshot_id | BookSnapshotChapter | snapshot_id | reuse | NO | |
| SnapshotChapterV1 | chapter_id | BookSnapshotChapter | source_chapter_id | adapter | NO | Nullable FK today |
| SnapshotChapterV1 | chapter_index | BookSnapshotChapter | chapter_order | adapter | NO | 0-based contract vs order |
| SnapshotChapterV1 | title | BookSnapshotChapter | title | reuse | NO | |
| SnapshotChapterV1 | chapter_hash | BookSnapshotChapter | content_hash | adapter | NO | Rename only |
| SnapshotChapterV1 | paragraph_count | — | — | extend_later | YES | Derive or store |
| SnapshotChapterV1 | character_count | — | — | extend_later | YES | Derive from content_text |
| SnapshotParagraphV1 | snapshot_paragraph_id | BookSnapshotParagraph | id | reuse | NO | |
| SnapshotParagraphV1 | snapshot_id | BookSnapshotParagraph | snapshot_id | reuse | NO | |
| SnapshotParagraphV1 | snapshot_chapter_id | BookSnapshotParagraph | snapshot_chapter_id | reuse | NO | |
| SnapshotParagraphV1 | chapter_id | BookSnapshotChapter | source_chapter_id | adapter | NO | Via chapter join |
| SnapshotParagraphV1 | paragraph_index | BookSnapshotParagraph | paragraph_order | adapter | NO | |
| SnapshotParagraphV1 | global_paragraph_index | — | — | new_in_wb_0_4 | YES | Not stored; must be computed/persisted |
| SnapshotParagraphV1 | text | BookSnapshotChapter | content_text[+offsets] | adapter | NO | Paragraph text sliced from chapter; contract stores explicit text |
| SnapshotParagraphV1 | text_hash | BookSnapshotParagraph | content_hash | adapter | NO | Must match stored Snapshot text |
| SnapshotParagraphV1 | character_count | — | — | adapter | NO | `end_offset-start_offset` today |
| SnapshotEvidenceLocatorV1 | * | NarrativeAssetEvidence / NarrativeRelationEvidence | offsets + paragraph FK + hash | adapter | NO | Wire locator is stricter (quote_text/quote_hash/global index) |
| SnapshotEvidenceLocatorV1 | quote_text | — | — | extend_later | YES | Not persisted as first-class column |
| SnapshotEvidenceLocatorV1 | quote_hash | — | — | new_in_wb_0_4 | YES | |
| SnapshotEvidenceLocatorV1 | global_paragraph_index | — | — | new_in_wb_0_4 | YES | |
| WholeBookRunV1 | run_id | AnalysisRun | id | reuse | NO | Shared run table; whole-book mode fields partial |
| WholeBookRunV1 | book_id | AnalysisRun | book_id | reuse | NO | |
| WholeBookRunV1 | snapshot_id | AnalysisRun / artifacts | book_snapshot_id (partial) | extend_later | YES | Must be immutable bind for WB runs |
| WholeBookRunV1 | mode | — | — | new_in_wb_0_4 | YES | native/enhanced |
| WholeBookRunV1 | status | AnalysisRun | status | adapter | NO | Expand enum values (`recoverable`, etc.) |
| WholeBookRunV1 | current_stage_code | AnalysisRunStage | stage_key | adapter | NO | |
| WholeBookRunV1 | idempotency_key | — | — | new_in_wb_0_4 | YES | |
| WholeBookRunV1 | engine_id / engine_version | AnalysisRun | provider/model fields (partial) | adapter | NO | Do not store API keys |
| WholeBookRunV1 | contract_version | — | — | new_in_wb_0_4 | YES | |
| WholeBookRunV1 | result_origin | — | — | new_in_wb_0_4 | YES | formal/fixture |
| WholeBookRunV1 | input_usage | — | — | new_in_wb_0_4 | YES | JSON blob acceptable |
| WholeBookRunV1 | consent_id / cost_policy_id | — | — | new_in_wb_0_4 | YES | WB-0.3 cost step |
| WholeBookRunV1 | lifecycle timestamps | AnalysisRun | created/started/completed (partial) | extend_later | YES | paused/failed/cancelled explicit |
| WholeBookRunV1 | failure_code / failure_message_safe | AnalysisRun | error fields (partial) | adapter | NO | Safe message constraints |
| WholeBookRunStageV1 | * | AnalysisRunStage | * | adapter | NO | progress_current/total missing → extend_later |
| WholeBookRunStageV1 | progress_current/total | — | — | new_in_wb_0_4 | YES | |
| WholeBookCheckpointV1 | checkpoint_payload | AnalysisRunStage | checkpoint_json | adapter | NO | Sensitivity scanner required |
| WholeBookCheckpointV1 | checkpoint_key / sequence_no / payload_hash | — | — | new_in_wb_0_4 | YES | |
| WholeBookWindowV1 | * | WholeBookRunWindow | window_index/status/input_hash | adapter | NO | Existing window rows are Overview-runtime; align fields in WB-0.4 |
| WholeBookWindowV1 | first/last_global_paragraph_index | — | — | new_in_wb_0_4 | YES | |
| WholeBookWindowV1 | window_hash / idempotency_key | WholeBookRunWindow | input_hash (partial) | adapter | NO | |
| WholeBookWindowCoverageV1 | * | — | — | new_in_wb_0_4 | YES | Computed report; optional persist |
| AnalysisProvenanceV1 | * | — / artifact metadata | partial fingerprints | new_in_wb_0_4 | YES | Wire provenance not first-class table |
| WholeBookInputUsageV1 | * | — | — | new_in_wb_0_4 | YES | |
| WholeBookWindowAnalysisRequestV1 | * | Private engine wire (legacy overview_v1) | Window input DTOs | adapter | NO | Legacy IDs are strings; new contract uses ints |
| Candidate* / Window Response | * | Private `whole_book_overview_v1` candidates | candidate_* | adapter | NO | Legacy ≠ Formal Contract; adapter only |
| PersistedNarrativeEntityV1 | entity_id | NarrativeEntity | id | reuse | NO | |
| PersistedNarrativeEntityV1 | snapshot_id | — | — | new_in_wb_0_4 | YES | Entity today is book-scoped, not snapshot-scoped |
| PersistedNarrativeEntityV1 | entity_type / canonical_name | NarrativeEntity | entity_type / canonical_name | reuse | NO | |
| PersistedNarrativeEntityV1 | state | NarrativeEntity | lifecycle_status | adapter | NO | Map to ArtifactState |
| PersistedNarrativeEntityV1 | confidence / provenance / evidence_ids | — | — | new_in_wb_0_4 | YES | |
| PersistedNarrativeEntityV1 | user_confirmed_at | — | — | new_in_wb_0_4 | YES | |
| EntityAliasV1 | name | NarrativeEntityAlias | alias_text | reuse | NO | |
| EntityAliasV1 | confidence / evidence_ids | — | — | new_in_wb_0_4 | YES | |
| PersistedNarrativeAssetV1 | asset_id | NarrativeAsset | id | reuse | NO | |
| PersistedNarrativeAssetV1 | snapshot_id | NarrativeAssetVersion | book_snapshot_id | adapter | NO | On version today |
| PersistedNarrativeAssetV1 | asset_type / title | NarrativeAssetVersion | asset_type / title | adapter | NO | Type lives on version |
| PersistedNarrativeAssetV1 | state | NarrativeAssetVersion | review_status | adapter | NO | |
| PersistedNarrativeAssetV1 | current_version_id | NarrativeAssetVersion | id where is_canonical | adapter | NO | |
| NarrativeAssetVersionV1 | * | NarrativeAssetVersion | * | adapter | NO | payload_hash / source_window_ids missing |
| NarrativeAssetVersionV1 | payload_hash | — | — | new_in_wb_0_4 | YES | Confirmed protection depends on it |
| NarrativeAssetVersionV1 | source_window_ids | — | — | new_in_wb_0_4 | YES | |
| PersistedEvidenceV1 | evidence_id | NarrativeAssetEvidence | id | reuse | NO | Relation evidence is separate table |
| PersistedEvidenceV1 | locator | NarrativeAssetEvidence | paragraph FK + offsets + hash | adapter | NO | |
| PersistedEvidenceV1 | state | — | — | new_in_wb_0_4 | YES | valid/stale/unresolved |
| PersistedNarrativeRelationV1 | * | NarrativeRelation (+Version) | asset↔asset endpoints | extend_later | YES | Contract allows entity|asset refs; ORM is asset-only |
| NarrativeRefV1 | kind/id | AnalysisConflict left/right refs (partial) | left_ref_type/id | adapter | NO | |
| AnalysisConflictV1 | conflict_id | AnalysisConflict | id | reuse | NO | |
| AnalysisConflictV1 | snapshot_id | AnalysisConflict | book_snapshot_id | adapter | NO | |
| AnalysisConflictV1 | target / confirmed_version_id / proposed_version_id | AnalysisConflict | left/right refs | adapter | NO | Semantically different; need adapter |
| AnalysisConflictV1 | status enum | AnalysisConflict | status | extend_later | YES | New resolution statuses |
| BookOverviewClaimV1 | * | Insights/Lab projection DTOs | OverviewField | adapter | NO | **Not** Native fact source; Legacy adapter only |
| BookOverviewResultV1 | * | Whole-book artifact / projection | — | new_in_wb_0_4 | YES | Formal result persistence |
| WholeBookSynthesisRequest/Response | * | Private overview synthesis DTOs | SynthesisInput / ProjectionCandidate | adapter | NO | Legacy shapes retained until cutover |
| Lab V2 DTO | * | reader_journey_v2 schemas | * | not_applicable | NO | Must not be marked Formal Contract |
| Insights DTO | * | chapter-aggregate insights | * | not_applicable | NO | Not Native full-text fact source |
| Scene analysis schemas | * | scene.py AnalysisRunResponse | * | not_applicable | NO | v1.1.1 single-chapter path unchanged |

## Migration Delta Summary (WB-0.4 only)

Identified (not executed):

1. Snapshot version + completed_at  
2. Paragraph global index + explicit paragraph text policy  
3. Evidence quote_text/quote_hash + EvidenceState  
4. Whole-book run mode/origin/input_usage/idempotency  
5. Stage progress counters + checkpoint identity  
6. Window global range + coverage report  
7. Provenance persistence  
8. Entity snapshot binding + confirmation timestamps  
9. Asset version payload_hash + window provenance  
10. Relation endpoint kind expansion (entity|asset)  
11. Conflict target/version fields alignment  
12. Formal BookOverviewResult persistence  

**Duplicate production modeling:** NO — this Step adds Wire/DTO contracts only; reuses existing Narrative Asset ORM Protocols.

**Insights as Native fact source:** NO (explicit `not_applicable`).
