/**
 * Shared Phase 1C contract fixture for frontend key consistency tests.
 * Agent H backend may not be merged yet — Integration validates live parity later.
 */

export const PHASE1C_CONTRACT_CAPABILITY_KEYS = [
  "whole_book_analysis",
  "narrative_asset_library",
  "story_lab",
  "cross_book_search",
  "advanced_export",
  "pro_whole_book_insights",
  "whole_book_native",
  "whole_book_enhanced",
  "chapter_aggregate_insights",
  "common_patterns",
  "knowledge_extraction",
  "book_skill_generation",
] as const;

export const PHASE1C_CONTRACT_ANALYSIS_MODES = [
  "whole_book_native",
  "whole_book_enhanced",
] as const;

export const PHASE1C_NARRATIVE_FOUNDATION_KEYS = [
  "narrative_asset_library",
] as const;
