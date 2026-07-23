/**
 * Phase 1C-P capability contract exports + Agent I client/store/presentation.
 *
 * Agent I owns:
 * - capabilityClient.ts
 * - capabilityStore.ts
 * - presentation.ts
 * - legacyCompatibility.ts
 * - Pro presentation components (features/capability)
 *
 * Do NOT set PRO_CAPABILITIES_SHIPPED=true in productEdition.ts until product ships.
 */

export * from "./types";
export { CAPABILITY_KEYS, PRO_CAPABILITY_KEYS, isCapabilityKey } from "./keys";
export * from "./legacyMapper";
export * from "./capabilityDto";
export * from "./capabilityClient";
export * from "./capabilityStore";
export * from "./presentation";
export * from "./legacyCompatibility";
export * from "./contractKeys.fixture";
