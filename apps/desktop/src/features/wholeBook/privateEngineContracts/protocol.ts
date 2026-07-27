/** Minimal public private-engine protocol types (Phase 2B-P). */

export const PRIVATE_ENGINE_PROTOCOL_ID = "storylens.private_engine.v1" as const;

export const WHOLE_BOOK_ANALYSIS_MODES = [
  "whole_book_native",
  "whole_book_enhanced",
] as const;

export type WholeBookAnalysisMode = (typeof WHOLE_BOOK_ANALYSIS_MODES)[number];

export const WHOLE_BOOK_QUALITY_PROFILES = [
  "fast",
  "balanced",
  "high_quality",
  "custom",
] as const;

export type WholeBookQualityProfileKey = (typeof WHOLE_BOOK_QUALITY_PROFILES)[number];

/** Analysis Mode ≠ Quality Profile ≠ Model Route (provider policy). */
export const SEPARATION_NOTES = {
  analysisMode: "whole_book_native | whole_book_enhanced",
  qualityProfile: "fast | balanced | high_quality | custom",
  modelRoute: "decided by provider policy only",
} as const;
