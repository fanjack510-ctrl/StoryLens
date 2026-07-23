# Phase 1D-P Module Result Contracts

DTO freeze only — no analysis algorithms. All 11 module payloads used inside `WholeBookResultEnvelope.payload`.

Shared conventions:

- Every DTO includes `evidence_refs` (or item-level refs) where listed.
- IDs reference Phase 1B Asset / Relation / Entity — not free-form model blobs.
- No full body text; no raw model JSON.

## A. BookOverviewResultDto

Required:

- `logline`
- `premise`
- `central_question`
- `primary_conflict`
- `protagonist_asset_id`
- `major_storyline_ids`
- `structure_summary`
- `ending_state`
- `evidence_refs`
- `confidence`

## B. StructureStagesResultDto

Required:

- `stages`
- `turning_points`
- `act_or_phase_labels`
- `chapter_ranges`
- `narrative_function`
- `evidence_refs`
- `confidence`

Constraint: **不得强制**所有小说使用三幕式。

## C. ChapterFunctionsResultDto

Required (per chapter item / collection contract):

- `chapter_id`
- `chapter_order`
- `function_labels`
- `primary_storyline_ids`
- `character_focus_ids`
- `hook_ids`
- `payoff_ids`
- `change_summary`
- `evidence_refs`

IA placement: under **结构**.

## D. StorylinesResultDto

Required (per storyline item):

- `storyline_asset_id`
- `title`
- `summary`
- `storyline_type`
- `chapter_range`
- `key_event_ids`
- `involved_entity_ids`
- `relation_ids`
- `status`
- `evidence_refs`

## E. CharactersResultDto / CharacterArcsResultDto

Shared required fields (per character / arc item):

- `entity_id`
- `canonical_name`
- `aliases`
- `role`
- `goal_asset_ids`
- `conflict_asset_ids`
- `choice_asset_ids`
- `consequence_asset_ids`
- `arc_stage_ids`
- `chapter_range`
- `evidence_refs`

IA: `character_arcs` under **人物**.

## F. RelationshipsResultDto

Required (per relationship item):

- `source_entity_id`
- `target_entity_id`
- `relationship_stage`
- `relation_asset_ids`
- `changes`
- `chapter_range`
- `evidence_refs`

## G. HooksPayoffsResultDto

Required (per hook item):

- `hook_asset_id`
- `hook_type`
- `setup_chapter`
- `payoff_asset_ids`
- `payoff_status`
- `payoff_chapters`
- `delay`
- `evidence_refs`

## H. CausalChainResultDto

Required (per causal edge item):

- `source_asset_id`
- `target_asset_id`
- `relation_id`
- `causal_type`
- `strength`
- `evidence_refs`

IA: under **因果与时间**.

## I. BasicTimelineResultDto

Required:

- `timeline_items`
- `story_time`
- `narrative_order`
- `chapter_id`
- `event_asset_ids`
- `certainty`
- `evidence_refs`

IA: under **因果与时间**.

## J. DiagnosticsResultDto

Required:

- `diagnostic_items`
- `category`
- `severity`
- `affected_asset_ids`
- `affected_chapters`
- `evidence_refs`
- `explanation`
- `user_actionable`
- `recommendation`

Constraint: 诊断不得只输出分数；必须有 Evidence 与可解释原因。

## Module key catalog (unique)

`book_overview` · `structure_stages` · `chapter_functions` · `storylines` · `characters` · `character_arcs` · `relationships` · `hooks_payoffs` · `causal_chain` · `basic_timeline` · `diagnostics`
