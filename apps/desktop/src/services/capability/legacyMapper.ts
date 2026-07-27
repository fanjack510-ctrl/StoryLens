/**
 * Legacy VIP FEATURE_KEYS (license/features.ts) → CapabilityKey | null.
 *
 * See backend capability_legacy.py for the authoritative mapping table.
 */

import type { CapabilityKey } from "./keys";

const LEGACY_TO_CAPABILITY: Record<string, CapabilityKey> = {
  batch_analysis: "whole_book_analysis",
  novel_rhythm_map: "whole_book_analysis",
  character_arc: "whole_book_analysis",
  foreshadow_tracking: "whole_book_analysis",
  novel_comparison: "cross_book_search",
  advanced_report: "advanced_export",
  inspiration_center: "story_lab",
};

export function mapLegacyFeatureKey(legacyKey: string): CapabilityKey | null {
  return LEGACY_TO_CAPABILITY[legacyKey] ?? null;
}

/** Re-export note: entitlementApi.PRO_FEATURE_KEYS uses canonical keys directly. */
export { PRO_FEATURE_KEYS as ENTITLEMENT_CANONICAL_KEYS } from "../entitlementApi";
