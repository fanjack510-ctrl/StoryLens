/**
 * Phase 1C-P capability contract exports.
 *
 * Agent I owns:
 * - capabilityClient.ts (API + evaluate flows)
 * - capabilityStore.ts (React state)
 * - Pro presentation components (isolated)
 *
 * Do NOT set PRO_CAPABILITIES_SHIPPED=true in productEdition.ts until product ships.
 */

export * from "./types";
export * from "./keys";
export * from "./legacyMapper";
