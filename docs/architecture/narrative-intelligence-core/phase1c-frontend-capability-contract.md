# Phase 1C Frontend Capability Contract

Frozen TypeScript types for Agent I — **no** full Pro UI pages in Phase 1C-P.

## Files (Phase 1C-P)

| File | Owner |
|------|-------|
| `apps/desktop/src/services/capability/types.ts` | Phase 1C-P |
| `apps/desktop/src/services/capability/keys.ts` | Phase 1C-P |
| `apps/desktop/src/services/capability/legacyMapper.ts` | Phase 1C-P |
| `apps/desktop/src/services/capability/index.ts` | Phase 1C-P |
| `capabilityClient.ts` | Agent I |
| `capabilityStore.ts` | Agent I |

## Keys

`CAPABILITY_KEYS` must match Python `CapabilityKey` enum (verified in contract tests).

## Legacy map

VIP `FEATURE_KEYS` from `license/features.ts` → `CapabilityKey | null` via `legacyMapper.ts` (mirrors backend `capability_legacy.py`).

## Hard boundary

`PRO_CAPABILITIES_SHIPPED` in `productEdition.ts` **must remain `false`** until product explicitly ships Pro capabilities.

Existing `entitlementApi.PRO_FEATURE_KEYS` unchanged; optional cross-reference via mapper comments only.
