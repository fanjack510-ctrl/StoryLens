# Phase 1C Legacy VIP Audit (Agent I)

Change: **CHG-20260723-024**

This audit inventories frontend VIP / Pro judgments. Phase 1C only replaces low-risk capability infrastructure call sites; business pages are **not** mass-migrated.

## Search coverage

Patterns: `isVip`, `is_vip`, `hasVipFeature`, `vipFeatures`, `license.vip`, `user.vip`, `featureFlags`, `CANONICAL_FEATURES`, `whole_book_analysis`, `story_lab`, `pro_active`, `hasFeature`, `canUseFeature`, `PRO_FEATURE_KEYS`, `VIP_ACTIVE`.

## Inventory

| File | Current judgment | Suggested replacement | Modified in CHG-024 | Follow-up |
|------|------------------|----------------------|---------------------|-----------|
| `services/license/features.ts` | `hasFeature(FEATURE_KEYS)` phaseAccess free/not_enabled | `mapLegacyFeatureKeyStrict` + `hasCapability` | No | UI migration after Integration |
| `stores/license/licenseStore.ts` | `hasFeature` + VIP status labels | Keep license identity; feature allow via Capability Store; call `onLicenseChanged` on activate/refresh | No (hook available) | Settings / hydrate wiring |
| `services/license/licenseService.ts` | Mock VIP status machine + `hasFeature` | License lifecycle only; never map VIP→allowed | No | none in 1C |
| `services/license/mockLicenseService.ts` | VIP_ACTIVE / EXPIRED / OFFLINE_GRACE | Remains mock license | No | none |
| `services/entitlementApi.ts` | `canUseFeature` / `pro_active` / `PRO_FEATURE_KEYS` | Prefer `capabilityClient.evaluate` for Pro gates; keep entitlement for edition identity | No | CHG-025 |
| `services/productEdition.ts` | `is_pro` from `pro_active`; `PRO_CAPABILITIES_SHIPPED` | Edition identity stays; do not use as feature allow; **must remain false shipped flag** | No | none |
| `components/settings/LicenseSettingsCard.tsx` | `pro_active` + capability label list | Optional later: `CapabilityStatusBadge` / presentation | No | settings polish |
| `components/product/ProductEditionBadge.tsx` | `edition.is_pro` | Keep (product identity ≠ capability allow) | No | none |
| `components/product/DocumentTitleSync.tsx` | `edition.is_pro` title | Keep identity | No | none |
| `components/layout/AppShell.tsx` | `edition.is_pro` nav class | Keep styling; no Pro nav entry added | No | when Pro nav ships |
| `services/capability/legacyMapper.ts` | Legacy→canonical map | Reused; enhanced via `legacyCompatibility.ts` | Compatibility layer added | none |
| `services/pro_license_local.test.tsx` | entitlement mocks | Update when Settings migrate | No | with Settings change |
| `services/product_edition_identity_local.test.tsx` | `pro_active` fixtures | Keep | No | none |

## Explicit findings

- No scattered `user.isVip` / `hasVipFeature` / `license.vip` booleans found in page components under current tree.
- Primary legacy surface is `license/features.ts` FEATURE_KEYS (7 VIP keys) + entitlement `PRO_FEATURE_KEYS` (5 canonical).
- `whole_book_analysis` / `story_lab` appear as **canonical keys** in entitlement/productEdition/capability — not as naked VIP checks in analysis pages.

## This-stage replacements

Low-risk infrastructure only:

- New Capability Client / Store / Presentation / Gate components
- Legacy compatibility helpers + audit list constant `LEGACY_VIP_JUDGMENT_AUDIT`
- No mass page rewrites

## Follow-up Changes

1. **CHG-20260723-025 (Integration)** — live backend Capability routes + end-to-end gate checks  
2. Later Settings polish — present Capability decisions beside License card  
3. Future Pro page work — gate with `CapabilityGate`, never `is_pro` alone
