/**
 * Capability Store — caches backend Decisions only.
 * Does not persist allowed across restarts; does not grant from legacy VIP flags.
 */

import { create } from "zustand";
import { capabilityClient } from "./capabilityClient";
import { isCapabilityKey, type CapabilityKey } from "./keys";
import {
  getCapabilityPresentation,
  type CapabilityPresentation,
} from "./presentation";
import type {
  CapabilityAvailability,
  CapabilityDecisionDto,
  CapabilityMetadata,
} from "./types";

/** Soft TTL — decisions older than this should be refreshed when possible. */
export const CAPABILITY_CACHE_TTL_MS = 5 * 60 * 1000;

type CapabilityStoreState = {
  decisions: Partial<Record<CapabilityKey, CapabilityDecisionDto>>;
  metadata: Partial<Record<CapabilityKey, CapabilityMetadata>>;
  loading: boolean;
  error: string | null;
  lastEvaluatedAt: string | null;
  /** Opaque token bumped when license identity changes — triggers refresh hooks. */
  licenseEpoch: number;
  loadCapabilities: () => Promise<void>;
  refreshCapability: (key: CapabilityKey | string) => Promise<CapabilityDecisionDto | null>;
  getCapabilityDecision: (key: CapabilityKey | string) => CapabilityDecisionDto | null;
  hasCapability: (key: CapabilityKey | string) => boolean;
  getCapabilityAvailability: (key: CapabilityKey | string) => CapabilityAvailability | "unknown";
  getCapabilityPresentation: (key: CapabilityKey | string) => CapabilityPresentation;
  clearCapabilityCache: () => void;
  /** Call when entitlement / license snapshot changes — clears stale allowed and reloads. */
  onLicenseChanged: () => Promise<void>;
  isDecisionStale: (key: CapabilityKey | string) => boolean;
};

function emptyState(): Pick<
  CapabilityStoreState,
  "decisions" | "metadata" | "loading" | "error" | "lastEvaluatedAt"
> {
  return {
    decisions: {},
    metadata: {},
    loading: false,
    error: null,
    lastEvaluatedAt: null,
  };
}

/**
 * Merge decision without upgrading a prior deny to allow on failed refresh.
 * Callers pass `previous` when a refresh fails and fallback deny is returned —
 * if previous was deny and incoming is also deny, keep the more specific previous
 * only when incoming is generic unknown/offline; never promote deny → allow on error paths
 * (client already fail-closes; this guards store merge).
 */
export function mergeDecisionSafely(
  previous: CapabilityDecisionDto | undefined,
  incoming: CapabilityDecisionDto,
  opts?: { fromFailure?: boolean },
): CapabilityDecisionDto {
  if (opts?.fromFailure && previous && !previous.allowed && incoming.allowed) {
    return previous;
  }
  return incoming;
}

export const useCapabilityStore = create<CapabilityStoreState>((set, get) => ({
  ...emptyState(),
  licenseEpoch: 0,

  async loadCapabilities() {
    set({ loading: true, error: null });
    try {
      const list = await capabilityClient.list();
      const metadata: Partial<Record<CapabilityKey, CapabilityMetadata>> = {};
      for (const item of list) {
        metadata[item.key] = item;
      }
      // Evaluate each known key — allowed only from backend.
      const decisions: Partial<Record<CapabilityKey, CapabilityDecisionDto>> = {
        ...get().decisions,
      };
      for (const item of list) {
        const previous = decisions[item.key];
        try {
          const evaluated = await capabilityClient.evaluate(item.key);
          decisions[item.key] = mergeDecisionSafely(previous, evaluated);
        } catch {
          // Keep previous deny; do not invent allow.
          if (!previous) {
            decisions[item.key] = {
              capabilityKey: item.key,
              allowed: false,
              reasonCode: "CAPABILITY_UNKNOWN",
              availability: "unavailable",
              displayMessage: "暂时无法确认该功能的授权状态",
              message: "暂时无法确认该功能的授权状态",
            };
          }
        }
      }
      set({
        metadata,
        decisions,
        loading: false,
        error: null,
        lastEvaluatedAt: new Date().toISOString(),
      });
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "加载能力状态失败",
        // Do not clear existing decisions on failure (avoid deny→empty→misread as allow).
      });
    }
  },

  async refreshCapability(key) {
    if (!isCapabilityKey(key)) return null;
    const previous = get().decisions[key];
    try {
      const evaluated = await capabilityClient.evaluate(key);
      const merged = mergeDecisionSafely(previous, evaluated);
      set((state) => ({
        decisions: { ...state.decisions, [key]: merged },
        lastEvaluatedAt: new Date().toISOString(),
        error: null,
      }));
      return merged;
    } catch (error) {
      const fallback: CapabilityDecisionDto = {
        capabilityKey: key,
        allowed: false,
        reasonCode: "CAPABILITY_UNKNOWN",
        availability: "unavailable",
        displayMessage:
          error instanceof Error ? error.message : "刷新能力状态失败",
        message: error instanceof Error ? error.message : "刷新能力状态失败",
      };
      const merged = mergeDecisionSafely(previous, fallback, { fromFailure: true });
      set((state) => ({
        decisions: { ...state.decisions, [key]: merged },
        error: fallback.displayMessage ?? "刷新能力状态失败",
      }));
      return merged;
    }
  },

  getCapabilityDecision(key) {
    if (!isCapabilityKey(key)) return null;
    return get().decisions[key] ?? null;
  },

  hasCapability(key) {
    if (!isCapabilityKey(key)) return false;
    const decision = get().decisions[key];
    // Unloaded default: false. Never infer from VIP / license flags.
    return decision?.allowed === true;
  },

  getCapabilityAvailability(key) {
    if (!isCapabilityKey(key)) return "unknown";
    const decision = get().decisions[key];
    if (decision) return decision.availability;
    const meta = get().metadata[key];
    if (meta) return meta.availability;
    return "unknown";
  },

  getCapabilityPresentation(key) {
    if (!isCapabilityKey(key)) {
      return getCapabilityPresentation(key, null, null);
    }
    return getCapabilityPresentation(key, get().decisions[key], get().metadata[key]);
  },

  clearCapabilityCache() {
    set({
      ...emptyState(),
      licenseEpoch: get().licenseEpoch,
    });
  },

  async onLicenseChanged() {
    set((state) => ({
      ...emptyState(),
      licenseEpoch: state.licenseEpoch + 1,
    }));
    await get().loadCapabilities();
  },

  isDecisionStale(key) {
    if (!isCapabilityKey(key)) return true;
    const decision = get().decisions[key];
    if (!decision?.evaluatedAt) return true;
    const ts = Date.parse(decision.evaluatedAt);
    if (Number.isNaN(ts)) return true;
    return Date.now() - ts > CAPABILITY_CACHE_TTL_MS;
  },
}));

/** Non-hook helpers for services / tests. */
export function hasCapability(key: CapabilityKey | string): boolean {
  return useCapabilityStore.getState().hasCapability(key);
}

export function getCapabilityDecision(
  key: CapabilityKey | string,
): CapabilityDecisionDto | null {
  return useCapabilityStore.getState().getCapabilityDecision(key);
}

export function getStoreCapabilityPresentation(
  key: CapabilityKey | string,
): CapabilityPresentation {
  return useCapabilityStore.getState().getCapabilityPresentation(key);
}

export function clearCapabilityCache(): void {
  useCapabilityStore.getState().clearCapabilityCache();
}

export function loadCapabilities(): Promise<void> {
  return useCapabilityStore.getState().loadCapabilities();
}

export function refreshCapability(
  key: CapabilityKey | string,
): Promise<CapabilityDecisionDto | null> {
  return useCapabilityStore.getState().refreshCapability(key);
}

export function getCapabilityAvailability(
  key: CapabilityKey | string,
): CapabilityAvailability | "unknown" {
  return useCapabilityStore.getState().getCapabilityAvailability(key);
}
