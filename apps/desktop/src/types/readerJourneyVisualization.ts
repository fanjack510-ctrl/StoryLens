export type JourneySceneRole = "core" | "secondary" | "beat";

export type JourneyCurveMetric =
  | "engagement"
  | "valence"
  | "arousal"
  | "curiosity"
  | "tension"
  | "payoff"
  | "hook"
  | "dropoff_risk";

export type JourneyCurvePoint = {
  scene_ordinal: number;
  value?: number;
  start?: number;
  end?: number;
  /** When false, Beat auxiliary points are excluded from equal-weight main polyline. */
  include_in_main_curve?: boolean;
  node_type?: "scene" | "beat";
};

export type JourneyPhaseVisualization = {
  ordinal: number;
  title: string;
  start_scene_ordinal: number;
  end_scene_ordinal: number;
  primary_reader_question: string;
  dominant_emotion: string;
  reading_payoff: string;
  continuation_motivation: string;
  summary: string;
  confidence: number;
  average_engagement: number;
  core_scene_count: number;
  beat_count: number;
  scene_span: number;
};

export type JourneyQuestionLifecycleEntry = {
  scene_ordinal: number;
  status: string;
};

export type JourneyQuestionChain = {
  canonical_id: string;
  canonical_question: string;
  aliases: string[];
  source_chain_ids: string[];
  created_scene: number;
  carried_scene_ordinals: number[];
  transformed_scenes: number[];
  answered_scene: number | null;
  status: string;
  strength: number;
  open_at_chapter_end: boolean;
  confidence: number;
  merge_reason: string;
  question_type: string;
  auto_merged: boolean;
  lifecycle: JourneyQuestionLifecycleEntry[];
  importance?: number;
  importance_formula_version?: string;
};

export type JourneyQuestionClusterMember = {
  chain_id: string;
  question: string;
  relationship: string;
  importance: number;
  created_scene: number;
  status: string;
};

export type JourneyQuestionCluster = {
  cluster_id: string;
  cluster_type: string;
  cluster_title: string;
  member_chain_ids: string[];
  primary_chain_id: string;
  members: JourneyQuestionClusterMember[];
  relationships: { from_chain_id: string; to_chain_id: string; relationship: string }[];
  confidence: number;
  merge_reason: string;
  importance: number;
  created_scene: number;
  primary_question: string;
};

export type JourneyMarker = {
  scene_ordinal: number;
  scene_id: number;
  type?: string;
  summary?: string;
  strength?: number;
  gap?: string;
  continue_drive?: string;
  evidence_paragraph_ids?: string[];
  visible?: boolean;
  suppression_reason?: string;
};

export type JourneyRiskPenalty = {
  code: string;
  amount: number;
  label?: string;
};

export type JourneyRiskInterval = {
  risk_type: string;
  start_scene_ordinal: number;
  end_scene_ordinal: number;
  span: number;
  summary?: string;
  trigger?: string;
  needs_review?: boolean;
  question?: string;
  strength?: number;
  /** V2 dropoff panel: field used for the formula (e.g. reading_momentum). */
  field_used?: string;
  penalties?: JourneyRiskPenalty[];
  final_risk?: number;
};

export type JourneySceneNodeScores = {
  curiosity: number;
  tension: number;
  payoff: number;
  hook: number;
  information_gain: number;
  emotional_resonance: number;
  cognitive_load: number;
  dropoff_risk: number;
  valence_start: number;
  valence_end: number;
  arousal_start: number;
  arousal_end: number;
  /** Optional v2 derived / mapped fields (absent on legacy payloads). */
  reading_momentum?: number;
  plot_progress?: number;
  reading_tension?: number;
  pacing_speed?: number;
  pacing_fit?: number;
  emotional_investment?: number;
  clarity?: number;
};

export type JourneyReaderQuestionItem = {
  question?: string;
  source?: string;
  origin?: string;
  strength?: number;
  answer_summary?: string;
  answer_degree?: string;
  trigger_summary?: string;
  confidence?: number;
  hook_type?: string;
  evidence_paragraph_ids?: string[];
};

export type JourneyPayoffHookItem = {
  type?: string;
  summary?: string;
  strength?: number;
  known?: string;
  gap?: string;
  continue_drive?: string;
  next_handoff?: string;
  evidence_paragraph_ids?: string[];
};

export type JourneyRiskPoint = {
  type?: string;
  summary?: string;
  severity?: number;
  evidence_paragraph_ids?: string[];
};

export type JourneyWritingTakeaway = {
  summary: string;
  applicable_when?: string;
  avoid_when?: string;
};

export type JourneyTechniqueItem = {
  code?: string;
  name?: string;
  summary?: string;
  mechanism?: string;
  reader_effect?: string;
  transfer_formula?: string;
  risk?: string;
  evidence_paragraph_ids?: string[];
};

export type JourneyInformationChange = {
  type?: string;
  summary?: string;
  certainty?: string;
  evidence_paragraph_ids?: string[];
};

export type JourneyCharacterEffect = {
  character_name?: string;
  character?: string;
  trait_or_change?: string;
  effect?: string;
  method?: string;
  evidence_paragraph_ids?: string[];
};

export type JourneySceneClassification = {
  scene_ordinal: number;
  importance_score: number;
  percentile: number;
  forced_floor_reason: string | null;
  final_level: JourneySceneRole;
  classification_reasons: string[];
  importance_formula_version: string;
};

export type JourneySceneNode = {
  scene_id: number;
  scene_ordinal: number;
  paragraph_range: {
    start_paragraph_id: string;
    end_paragraph_id: string;
  };
  paragraph_count: number;
  phase_ordinal: number | null;
  role: JourneySceneRole;
  importance_score: number;
  importance_formula_version: string;
  deterministic_reasons: string[];
  percentile?: number;
  forced_floor_reason?: string | null;
  classification_reasons?: string[];
  final_level?: JourneySceneRole;
  scene_value_summary: string;
  dominant_emotion: string;
  engagement: {
    engagement_score: number;
    [key: string]: unknown;
  };
  scores: JourneySceneNodeScores;
  reader_question_in: JourneyReaderQuestionItem[];
  reader_question_created: JourneyReaderQuestionItem[];
  reader_question_answered: JourneyReaderQuestionItem[];
  reader_question_out: JourneyReaderQuestionItem[];
  payoffs: JourneyPayoffHookItem[];
  hooks: JourneyPayoffHookItem[];
  techniques: JourneyTechniqueItem[];
  risk_points: JourneyRiskPoint[];
  information_changes?: JourneyInformationChange[];
  character_effects: JourneyCharacterEffect[];
  writing_takeaways: Array<JourneyWritingTakeaway | string>;
  evidence_paragraph_ids: string[];
  evidence_count: number;
  confidence: number;
  primary_payoff: JourneyPayoffHookItem | null;
  primary_hook: JourneyPayoffHookItem | null;
  primary_risk: JourneyRiskPoint | null;
  /** Optional v2 presentation fields (legacy payloads omit these). */
  node_type?: "scene" | "beat";
  include_in_main_curve?: boolean;
  include_in_chapter_mean?: boolean;
  scene_role?: string;
  primary_diagnosis?: string | null;
  secondary_diagnoses?: string[];
  positive_mechanism?: string | null;
  data_quality_issue?: string | null;
};

export type JourneyChapterSummary = {
  chapter_id: number;
  chapter_title: string;
  diagnosis: string;
  primary_traction: string;
  primary_cluster_title?: string;
  core_scene_count?: number;
  strong_hook_count?: number;
  stage_payoff_count?: number;
  max_low_payoff_interval?: JourneyRiskInterval | null;
  max_fragmentation_interval?: JourneyRiskInterval | null;
  strongest_payoff: JourneyMarker | null;
  strongest_hook: JourneyMarker | null;
  weak_interval: string;
  counts: {
    scene_count: number;
    phase_count: number;
    question_chain_count: number;
    canonical_chain_count: number;
    core: number;
    secondary: number;
    beat: number;
  };
  peaks: {
    engagement_peak: { scene_ordinal: number; value: number };
    engagement_valley: { scene_ordinal: number; value: number };
    engagement_average: number;
  };
  expanded_diagnosis: {
    pacing_diagnosis?: unknown[];
    chapter_strengths?: string[];
    chapter_risks?: string[];
    positive_feedback_distribution?: Record<string, unknown>;
    hook_distribution?: Record<string, unknown>;
    one_sentence_diagnosis?: string;
  };
};

export type JourneyFormulaVersions = {
  visualization_version: string;
  chain_rank_formula_version: string;
  importance_formula_version: string;
  chain_merge_formula_version: string;
  engagement_formula_version: string;
  hook_select_formula_version?: string;
  payoff_derive_formula_version?: string;
  cluster_formula_version?: string;
};

export type JourneyCalibrationStatus = {
  scene_contract_version?: string;
  scene_prompt_version?: string;
  planner_version?: string;
  formula_version?: string;
  source_mode?: string;
  display_banner?: string;
  semantic_source?: string;
  calibrated?: boolean;
  latest_audit?: Record<string, unknown>;
  evidence_coverage?: number;
};

export type JourneyDensityWarning = {
  code: string;
  message: string;
};

export type ReaderJourneyVisualization = {
  visualization_version: string;
  chapter_summary: JourneyChapterSummary;
  phases: JourneyPhaseVisualization[];
  curve_series: Record<JourneyCurveMetric, JourneyCurvePoint[]>;
  scene_nodes: JourneySceneNode[];
  role_counts: {
    core: number;
    secondary: number;
    beat: number;
  };
  primary_question_chain: JourneyQuestionChain | null;
  phase_question_chains: JourneyQuestionChain[];
  secondary_question_chains: JourneyQuestionChain[];
  question_clusters?: JourneyQuestionCluster[];
  visible_question_clusters?: JourneyQuestionCluster[];
  all_hook_count?: number;
  visible_hook_count?: number;
  suppressed_hook_count?: number;
  suppressed_hooks?: JourneyMarker[];
  semantic_payoff_count?: number;
  derived_payoff_count?: number;
  deduped_payoff_count?: number;
  visible_payoff_count?: number;
  semantic_payoffs?: Record<string, unknown>[];
  derived_micro_payoffs?: Record<string, unknown>[];
  scene_level_distribution?: {
    role_counts: { core: number; secondary: number; beat: number };
    classifications: JourneySceneClassification[];
  };
  visual_density_warnings?: JourneyDensityWarning[];
  payoff_markers: JourneyMarker[];
  hook_markers: JourneyMarker[];
  risk_intervals: JourneyRiskInterval[];
  formula_versions: JourneyFormulaVersions;
  calibration_status: JourneyCalibrationStatus;
  /** V2 question lifecycle records (presentation); absent on legacy. */
  question_lifecycle?: Array<{
    question_id: string;
    question_text: string;
    setup_scene: number;
    development_scenes: number[];
    payoff_scene: number | null;
    status: string;
    strength?: number;
  }>;
};
