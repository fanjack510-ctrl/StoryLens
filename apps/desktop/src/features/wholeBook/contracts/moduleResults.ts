export interface EvidenceRefLite {
  evidence_id: number | string;
  evidence_role: string;
}

export interface BookOverviewResultDto {
  logline: string;
  premise: string;
  central_question: string;
  primary_conflict: string;
  protagonist_asset_id: number | null;
  major_storyline_ids: number[];
  structure_summary: string;
  ending_state: string;
  evidence_refs: EvidenceRefLite[];
  confidence: number | null;
}

export interface StructureStagesResultDto {
  stages: Array<{
    stage_id: string;
    label: string;
    chapter_range: [number | null, number | null];
    narrative_function: string;
    order: number;
  }>;
  turning_points: Array<{
    turning_point_id: string;
    label: string;
    chapter_id: number | null;
    summary: string;
  }>;
  act_or_phase_labels: string[];
  chapter_ranges: Array<[number | null, number | null]>;
  narrative_function: string;
  evidence_refs: EvidenceRefLite[];
  confidence: number | null;
}

export interface ChapterFunctionsResultDto {
  chapter_id: number;
  chapter_order: number;
  function_labels: string[];
  primary_storyline_ids: number[];
  character_focus_ids: number[];
  hook_ids: number[];
  payoff_ids: number[];
  change_summary: string;
  evidence_refs: EvidenceRefLite[];
}

export interface StorylinesResultDto {
  storyline_asset_id: number;
  title: string;
  summary: string;
  storyline_type: string;
  chapter_range: [number | null, number | null];
  key_event_ids: number[];
  involved_entity_ids: number[];
  relation_ids: number[];
  status: string;
  evidence_refs: EvidenceRefLite[];
}

export interface CharactersResultDto {
  entity_id: number;
  canonical_name: string;
  aliases: string[];
  role: string;
  goal_asset_ids: number[];
  conflict_asset_ids: number[];
  choice_asset_ids: number[];
  consequence_asset_ids: number[];
  arc_stage_ids: number[];
  chapter_range: [number | null, number | null];
  evidence_refs: EvidenceRefLite[];
}

export interface CharacterArcsResultDto {
  entity_id: number;
  canonical_name: string;
  aliases: string[];
  role: string;
  goal_asset_ids: number[];
  conflict_asset_ids: number[];
  choice_asset_ids: number[];
  consequence_asset_ids: number[];
  arc_stage_ids: number[];
  chapter_range: [number | null, number | null];
  evidence_refs: EvidenceRefLite[];
}

export interface RelationshipsResultDto {
  source_entity_id: number;
  target_entity_id: number;
  relationship_stage: string;
  relation_asset_ids: number[];
  changes: Array<{
    chapter_id: number | null;
    summary: string;
    from_stage: string | null;
    to_stage: string | null;
  }>;
  chapter_range: [number | null, number | null];
  evidence_refs: EvidenceRefLite[];
}

export interface HooksPayoffsResultDto {
  hook_asset_id: number;
  hook_type: string;
  setup_chapter: number | null;
  payoff_asset_ids: number[];
  payoff_status: string;
  payoff_chapters: number[];
  delay: number | null;
  evidence_refs: EvidenceRefLite[];
}

export interface CausalChainResultDto {
  source_asset_id: number;
  target_asset_id: number;
  relation_id: number;
  causal_type: string;
  strength: number | null;
  evidence_refs: EvidenceRefLite[];
}

export interface BasicTimelineResultDto {
  timeline_items: Array<{
    item_id: string;
    story_time: string | null;
    narrative_order: number;
    chapter_id: number | null;
    event_asset_ids: number[];
    certainty: string;
    summary: string;
  }>;
  story_time: string | null;
  narrative_order: number[];
  chapter_id: number | null;
  event_asset_ids: number[];
  certainty: string;
  evidence_refs: EvidenceRefLite[];
}

export interface DiagnosticsResultDto {
  diagnostic_items: Array<{
    diagnostic_id: string;
    category: string;
    severity: string;
    affected_asset_ids: number[];
    affected_chapters: number[];
    evidence_refs: EvidenceRefLite[];
    explanation: string;
    user_actionable: boolean;
    recommendation: string;
  }>;
  category: string | null;
  severity: string | null;
  affected_asset_ids: number[];
  affected_chapters: number[];
  evidence_refs: EvidenceRefLite[];
  explanation: string;
  user_actionable: boolean;
  recommendation: string;
}

export const MODULE_RESULT_DTO_NAMES = [
  "BookOverviewResultDto",
  "StructureStagesResultDto",
  "ChapterFunctionsResultDto",
  "StorylinesResultDto",
  "CharactersResultDto",
  "CharacterArcsResultDto",
  "RelationshipsResultDto",
  "HooksPayoffsResultDto",
  "CausalChainResultDto",
  "BasicTimelineResultDto",
  "DiagnosticsResultDto",
] as const;
