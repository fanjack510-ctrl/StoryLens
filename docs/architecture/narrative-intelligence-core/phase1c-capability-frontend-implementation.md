# Phase 1C Capability Frontend Implementation (Agent I)

Change: **CHG-20260723-024**  
Branch: `feature/narrative-phase1c-capability-frontend`  
Baseline: `a275e837a392a1d21a11040cc71670548b1160ef`

## Scope delivered

| Area | Path |
|------|------|
| Client | `apps/desktop/src/services/capability/capabilityClient.ts` |
| DTO guards | `apps/desktop/src/services/capability/capabilityDto.ts` |
| Store | `apps/desktop/src/services/capability/capabilityStore.ts` |
| Presentation | `apps/desktop/src/services/capability/presentation.ts` |
| Legacy compatibility | `apps/desktop/src/services/capability/legacyCompatibility.ts` |
| Contract fixture | `apps/desktop/src/services/capability/contractKeys.fixture.ts` |
| Isolated UI | `apps/desktop/src/features/capability/` (+ `components/capability` re-export) |
| Key check script | `scripts/check_capability_keys.py` |

Frozen Phase 1C-P files reused without contract mutation:

- `keys.ts` / `types.ts` / `legacyMapper.ts`

## Capability Client

- `list()` → `GET /api/v1/capabilities`
- `get(key)` / `evaluate(key, context?)` → `GET /api/v1/capabilities/{key}`
- `allowed` is always backend Decision (or fail-closed fallback)
- Unknown keys throw; never silently accepted
- Offline / network failures return deny decisions (`CAPABILITY_OFFLINE_NOT_ALLOWED` / `CAPABILITY_UNKNOWN`)
- No credential read; paths centralized (no URL assembly in components)
- Uses existing `api()` + loopback base URL rules

## Capability Store (Zustand)

State: `decisions`, `metadata`, `loading`, `error`, `lastEvaluatedAt`, `licenseEpoch`

API: `loadCapabilities`, `refreshCapability`, `getCapabilityDecision`, `hasCapability`, `getCapabilityAvailability`, `clearCapabilityCache`, `onLicenseChanged`

Rules:

1. `hasCapability` reads only `decision.allowed`
2. Unloaded default is `false`
3. Cache is in-memory only (restart does not restore stale `allowed`)
4. TTL helper `isDecisionStale` (5 minutes)
5. License change clears cache then reloads
6. Failed refresh cannot promote prior deny → allow
7. No commercial pricing fields

## Legacy mapper

- Frozen `mapLegacyFeatureKey` retained
- Agent I adds `resolveLegacyKey` / `mapLegacyFeatureKeyStrict` / mode detection
- `whole_book_native` / `whole_book_enhanced` resolve as **analysis modes**, not features
- Unknown legacy keys do not silently map
- VIP boolean helper always returns `false` for allow purposes

## Explicit non-goals (this change)

- No backend Capability service
- No formal whole-book analysis page / Pro nav
- No `PRO_CAPABILITIES_SHIPPED` flip
- No License / Engine / payment / Narrative Asset edits
- No production / Windows build / push

## Integration notes

Agent H capability routes are not merged yet. Client targets the contract path `/api/v1/capabilities`; live parity is Integration (`CHG-20260723-025`).
