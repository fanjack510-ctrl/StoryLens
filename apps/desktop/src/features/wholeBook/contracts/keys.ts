/** Canonical whole-book module keys — must match backend WholeBookModuleKey. */

export const WHOLE_BOOK_MODULE_KEYS = [
  "book_overview",
  "structure_stages",
  "chapter_functions",
  "storylines",
  "characters",
  "character_arcs",
  "relationships",
  "hooks_payoffs",
  "causal_chain",
  "basic_timeline",
  "diagnostics",
] as const;

export type WholeBookModuleKey = (typeof WHOLE_BOOK_MODULE_KEYS)[number];

export const WHOLE_BOOK_ANALYSIS_MODES = [
  "whole_book_native",
  "whole_book_enhanced",
] as const;

export type WholeBookAnalysisMode = (typeof WHOLE_BOOK_ANALYSIS_MODES)[number];

export const WHOLE_BOOK_RUN_VIEW_STATUSES = [
  "pending",
  "running",
  "paused",
  "interrupted",
  "completed",
  "failed",
  "cancelled",
] as const;

export type WholeBookRunViewStatus = (typeof WHOLE_BOOK_RUN_VIEW_STATUSES)[number];

export const WHOLE_BOOK_MODULE_STATUSES = [
  "not_requested",
  "pending",
  "running",
  "partial",
  "completed",
  "failed",
  "stale",
  "blocked",
] as const;

export type WholeBookModuleStatus = (typeof WHOLE_BOOK_MODULE_STATUSES)[number];

export const STAGE_STATUSES = [
  "pending",
  "running",
  "paused",
  "interrupted",
  "completed",
  "failed",
  "skipped",
  "cancelled",
] as const;

export type StageStatus = (typeof STAGE_STATUSES)[number];

export const RUN_ALLOWED_ACTIONS = [
  "pause",
  "resume",
  "retry",
  "cancel",
  "view_partial_results",
] as const;

export type RunAllowedAction = (typeof RUN_ALLOWED_ACTIONS)[number];

export const EVIDENCE_INTEGRITY_STATUSES = [
  "valid",
  "stale",
  "hash_mismatch",
  "missing",
  "inaccessible",
] as const;

export type EvidenceIntegrityStatus = (typeof EVIDENCE_INTEGRITY_STATUSES)[number];

export const NARRATIVE_REVIEW_ACTIONS = [
  "confirm",
  "correct",
  "reject",
  "lock",
  "unlock",
  "mark_stale",
  "resolve_conflict",
  "dismiss_conflict",
] as const;

export type NarrativeReviewAction = (typeof NARRATIVE_REVIEW_ACTIONS)[number];

export const STRUCTURE_MAP_VIEW_MODES = [
  "structure_stages",
  "storylines",
  "character_growth",
] as const;

export type StructureMapViewMode = (typeof STRUCTURE_MAP_VIEW_MODES)[number];

export const RESULT_NAV_SECTION_KEYS = [
  "overview",
  "structure",
  "storylines",
  "characters",
  "relationships",
  "hooks_payoffs",
  "causal_timeline",
  "diagnostics",
  "evidence_conflicts",
  "structure_map",
] as const;

export type ResultNavSectionKey = (typeof RESULT_NAV_SECTION_KEYS)[number];

/** Product-frozen module → required engine stages (not UI stage keys). */
export const MODULE_STAGE_DEPENDENCIES: Record<
  WholeBookModuleKey,
  readonly string[]
> = {
  book_overview: ["build_fulltext_index"],
  structure_stages: [
    "build_fulltext_index",
    "resolve_entities",
    "analyze_structure",
  ],
  chapter_functions: ["analyze_structure"],
  storylines: [
    "resolve_entities",
    "analyze_structure",
    "analyze_storylines",
  ],
  characters: ["resolve_entities", "analyze_characters"],
  character_arcs: [
    "resolve_entities",
    "analyze_characters",
    "analyze_storylines",
  ],
  relationships: [
    "resolve_entities",
    "analyze_characters",
    "analyze_storylines",
  ],
  hooks_payoffs: [
    "analyze_structure",
    "analyze_storylines",
    "analyze_hooks",
  ],
  causal_chain: ["analyze_storylines", "analyze_causality_timeline"],
  basic_timeline: ["resolve_entities", "analyze_causality_timeline"],
  diagnostics: [
    "analyze_structure",
    "analyze_storylines",
    "analyze_characters",
    "analyze_hooks",
    "analyze_causality_timeline",
    "verify_evidence",
  ],
};

export const STRUCTURE_MAP_DEFAULT_MAX_NODES = 100;
export const STRUCTURE_MAP_DEFAULT_MAX_EDGES = 250;
export const PATTERN_DTO_HAS_ORM_TABLE = false;
