import { api } from "./apiClient";

export const PRO_FEATURE_KEYS = [
  "whole_book_analysis",
  "narrative_asset_library",
  "story_lab",
  "cross_book_search",
  "advanced_export",
  "pro_whole_book_insights",
] as const;

export type ProFeatureKey = (typeof PRO_FEATURE_KEYS)[number];

export type EntitlementSnapshot = {
  edition: "free" | "pro";
  edition_label: string;
  license_id: string | null;
  license_id_masked: string | null;
  major_version: number | null;
  activated_at: string | null;
  features: Record<string, boolean>;
  pro_active: boolean;
  commerce: {
    afdian_product_url: string;
    product_code: string;
    product_label: string;
  };
  key_id?: string;
  license_trust_mode?: "production" | "development";
  license_issuance_ready?: boolean;
  license_issuance_message?: string | null;
};

export type FeatureEntitlement = {
  enabled: boolean;
  reason: string | null;
  source: string;
  edition: string;
  license_id: string | null;
  major_version: number | null;
  feature_key: string;
};

export type ActivateLicenseResult = {
  ok: boolean;
  already_active?: boolean;
  error_code?: string | null;
  user_message: string;
  entitlement: EntitlementSnapshot;
};

export const entitlementApi = {
  snapshot: () => api<EntitlementSnapshot>("/api/v1/entitlements"),
  feature: (featureKey: string) =>
    api<FeatureEntitlement>(`/api/v1/entitlements/features/${encodeURIComponent(featureKey)}`),
  activate: (licenseCode: string) =>
    api<ActivateLicenseResult>("/api/v1/licenses/activate", {
      method: "POST",
      body: JSON.stringify({ license_code: licenseCode }),
    }),
};

/** Unified feature gate — never scatter isVip checks in business UI. */
export async function canUseFeature(featureKey: string): Promise<FeatureEntitlement> {
  return entitlementApi.feature(featureKey);
}

export function maskLicenseCode(code: string): string {
  const compact = code.replace(/\s+/g, "");
  if (compact.length <= 16) return compact;
  return `${compact.slice(0, 10)}…${compact.slice(-6)}`;
}
