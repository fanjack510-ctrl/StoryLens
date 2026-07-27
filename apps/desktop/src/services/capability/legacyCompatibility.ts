/**
 * Agent I legacy compatibility layer on top of frozen legacyMapper.ts.
 *
 * Mapper only resolves names — never turns legacy VIP booleans into allowed.
 * Analysis modes are NOT capability features.
 */

import { FEATURE_KEYS, type FeatureKey } from "../license/features";
import { mapLegacyFeatureKey } from "./legacyMapper";
import { isCapabilityKey, type CapabilityKey } from "./keys";
import type { WholeBookAnalysisMode } from "./types";

export type LegacyMapKind = "capability" | "analysis_mode" | "unmapped";

export type LegacyResolution =
  | {
      kind: "capability";
      legacyKey: string;
      capabilityKey: CapabilityKey;
    }
  | {
      kind: "analysis_mode";
      legacyKey: string;
      mode: WholeBookAnalysisMode;
      parentCapability: "whole_book_analysis";
    }
  | {
      kind: "unmapped";
      legacyKey: string;
      capabilityKey: null;
    };

const ANALYSIS_MODE_KEYS: Record<string, WholeBookAnalysisMode> = {
  whole_book_native: "whole_book_native",
  whole_book_enhanced: "whole_book_enhanced",
};

/** Known legacy VIP feature keys (license/features.ts). */
export const LEGACY_VIP_FEATURE_KEYS: readonly FeatureKey[] = FEATURE_KEYS;

export function isAnalysisModeKey(value: string): value is WholeBookAnalysisMode {
  return value in ANALYSIS_MODE_KEYS;
}

/**
 * Resolve a legacy string to capability OR analysis mode.
 * Unknown keys are not silently mapped.
 */
export function resolveLegacyKey(legacyKey: string): LegacyResolution {
  if (isAnalysisModeKey(legacyKey)) {
    return {
      kind: "analysis_mode",
      legacyKey,
      mode: ANALYSIS_MODE_KEYS[legacyKey],
      parentCapability: "whole_book_analysis",
    };
  }
  // Canonical capability keys pass through (entitlement already uses them).
  if (isCapabilityKey(legacyKey)) {
    return {
      kind: "capability",
      legacyKey,
      capabilityKey: legacyKey,
    };
  }
  const mapped = mapLegacyFeatureKey(legacyKey);
  if (mapped) {
    return {
      kind: "capability",
      legacyKey,
      capabilityKey: mapped,
    };
  }
  return {
    kind: "unmapped",
    legacyKey,
    capabilityKey: null,
  };
}

/**
 * Map legacy VIP feature key → CapabilityKey.
 * Throws on unknown keys (no silent mapping).
 */
export function mapLegacyFeatureKeyStrict(legacyKey: string): CapabilityKey {
  const resolved = resolveLegacyKey(legacyKey);
  if (resolved.kind === "capability") return resolved.capabilityKey;
  if (resolved.kind === "analysis_mode") {
    throw new Error(
      `${legacyKey} is an analysis mode under whole_book_analysis, not a capability feature`,
    );
  }
  throw new Error(`Unknown legacy feature key (no silent mapping): ${legacyKey}`);
}

/**
 * Legacy VIP boolean must NEVER be treated as capability.allowed.
 * This helper exists so call sites fail the type/audit check deliberately.
 */
export function legacyVipBooleanIsNotAllowed(_vipActive: boolean): false {
  return false;
}

/**
 * Files still using legacy VIP / entitlement judgments (Phase 1C Agent I audit).
 * Full details: docs/.../phase1c-legacy-vip-audit.md
 */
export const LEGACY_VIP_JUDGMENT_AUDIT: readonly {
  file: string;
  judgment: string;
  suggestedReplacement: string;
  modifiedInThisChange: boolean;
  followUpChange: string;
}[] = [
  {
    file: "apps/desktop/src/services/license/features.ts",
    judgment: "hasFeature(legacy FEATURE_KEYS) / phaseAccess",
    suggestedReplacement: "mapLegacyFeatureKeyStrict + hasCapability(capabilityKey)",
    modifiedInThisChange: false,
    followUpChange: "CHG-20260723-025 / later UI migration",
  },
  {
    file: "apps/desktop/src/stores/license/licenseStore.ts",
    judgment: "hasFeature / VIP_ACTIVE status labels",
    suggestedReplacement: "useCapabilityStore.hasCapability after license refresh",
    modifiedInThisChange: false,
    followUpChange: "post-1C license UX cleanup",
  },
  {
    file: "apps/desktop/src/services/entitlementApi.ts",
    judgment: "canUseFeature / PRO_FEATURE_KEYS / pro_active",
    suggestedReplacement: "capabilityClient.evaluate + presentation helpers",
    modifiedInThisChange: false,
    followUpChange: "CHG-20260723-025 integration",
  },
  {
    file: "apps/desktop/src/services/productEdition.ts",
    judgment: "is_pro from snapshot.pro_active; PRO_CAPABILITIES_SHIPPED",
    suggestedReplacement: "edition identity stays; feature gates use Capability Store",
    modifiedInThisChange: false,
    followUpChange: "keep edition badge; migrate feature gates only",
  },
  {
    file: "apps/desktop/src/components/settings/LicenseSettingsCard.tsx",
    judgment: "pro_active / PRO_FEATURE_KEYS list UI",
    suggestedReplacement: "CapabilityStatusBadge + getCapabilityPresentation",
    modifiedInThisChange: false,
    followUpChange: "settings polish after backend Capability ships",
  },
  {
    file: "apps/desktop/src/components/product/ProductEditionBadge.tsx",
    judgment: "edition.is_pro",
    suggestedReplacement: "keep for product identity; do not use as feature allow",
    modifiedInThisChange: false,
    followUpChange: "none (identity ≠ capability)",
  },
  {
    file: "apps/desktop/src/components/layout/AppShell.tsx",
    judgment: "edition.is_pro nav styling",
    suggestedReplacement: "keep identity styling; gate Pro nav via Capability later",
    modifiedInThisChange: false,
    followUpChange: "when Pro nav is introduced",
  },
  {
    file: "apps/desktop/src/services/license/mockLicenseService.ts",
    judgment: "VIP status machine + legacy feature list",
    suggestedReplacement: "remain mock license only; capability decisions from API",
    modifiedInThisChange: false,
    followUpChange: "none in 1C",
  },
];
