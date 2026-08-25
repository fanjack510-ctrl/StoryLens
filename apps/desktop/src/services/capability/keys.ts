/** Canonical capability keys — must match backend CapabilityKey enum. */

export const CAPABILITY_KEYS = [
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

export type CapabilityKey = (typeof CAPABILITY_KEYS)[number];

/** Aligns with entitlementApi.PRO_FEATURE_KEYS — unified naming. */
export const PRO_CAPABILITY_KEYS = CAPABILITY_KEYS;

export function isCapabilityKey(value: string): value is CapabilityKey {
  return (CAPABILITY_KEYS as readonly string[]).includes(value);
}
