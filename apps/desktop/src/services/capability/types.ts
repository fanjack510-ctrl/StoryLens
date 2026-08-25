/** Phase 1C-P frozen capability contract types (Agent I implements client/store). */

export type CapabilityAvailability = "unavailable" | "preview" | "available";

export type CapabilityReasonCode =
  | "CAPABILITY_NOT_SHIPPED"
  | "CAPABILITY_NOT_LICENSED"
  | "CAPABILITY_QUOTA_EXCEEDED"
  | "CAPABILITY_OFFLINE_NOT_ALLOWED"
  | "CAPABILITY_LICENSE_EXPIRED"
  | "CAPABILITY_LICENSE_INVALID"
  | "CAPABILITY_AVAILABLE"
  | "CAPABILITY_PREVIEW_ONLY"
  | "CAPABILITY_UNKNOWN"
  | "CAPABILITY_MODE_NOT_SUPPORTED";

export type WholeBookAnalysisMode = "whole_book_native" | "whole_book_enhanced";

export type CostClass = "free" | "low" | "medium" | "high";

export type CapabilityKey =
  | "whole_book_analysis"
  | "narrative_asset_library"
  | "story_lab"
  | "cross_book_search"
  | "advanced_export"
  | "pro_whole_book_insights"
  | "whole_book_native"
  | "whole_book_enhanced"
  | "chapter_aggregate_insights"
  | "common_patterns"
  | "knowledge_extraction"
  | "book_skill_generation";

export type QuotaDecisionDto = {
  allowed: boolean;
  reasonCode: CapabilityReasonCode;
  policyKey?: string;
  policyKind?: string;
  limit?: number | null;
  used?: number | null;
  reserved?: number | null;
  remaining?: number | null;
  resetAt?: string | null;
  message?: string;
};

export type CapabilityMetadata = {
  key: CapabilityKey;
  displayName: string;
  description: string;
  shipped: boolean;
  requiresLicense: boolean;
  availability: CapabilityAvailability;
  previewVisible?: boolean;
  supportedModes?: WholeBookAnalysisMode[];
  quotaPolicyKey?: string;
  estimatedCostClass?: CostClass;
  offlineAllowed?: boolean;
  /** @deprecated use displayName */
  label?: string;
};

export type CapabilityDecisionDto = {
  capabilityKey: CapabilityKey;
  allowed: boolean;
  reasonCode: CapabilityReasonCode;
  availability: CapabilityAvailability;
  displayMessage?: string;
  supportedModes?: WholeBookAnalysisMode[];
  quota?: QuotaDecisionDto | null;
  usage?: number | null;
  remaining?: number | null;
  offlineStatus?: string;
  licenseStatus?: string;
  evaluatedAt?: string;
  previewOnly?: boolean;
  /** @deprecated use displayMessage */
  message?: string;
};

/** @deprecated Prefer CapabilityDecisionDto */
export type CapabilityDecision = CapabilityDecisionDto;

/** @deprecated Prefer QuotaDecisionDto */
export type QuotaDecision = QuotaDecisionDto;

export type ProFeaturePresentation = {
  capabilityKey: CapabilityKey;
  state:
    | "usable"
    | "preview_only"
    | "not_licensed"
    | "not_shipped"
    | "quota_exceeded"
    | "license_invalid"
    | "offline_unavailable";
  title: string;
  description: string;
  ctaLabel?: string;
};

/** Narrative foundation storage is NOT Pro-gated at public asset API layer. */
export const NARRATIVE_FOUNDATION_CAPABILITY_KEYS = [
  "narrative_asset_library",
] as const satisfies readonly CapabilityKey[];

export function isProGatedCapability(key: CapabilityKey | string): boolean {
  return !(NARRATIVE_FOUNDATION_CAPABILITY_KEYS as readonly string[]).includes(key);
}
