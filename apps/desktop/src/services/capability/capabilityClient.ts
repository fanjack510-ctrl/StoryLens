/**
 * Capability HTTP client — allowed comes only from backend Decision.
 * Does not read License credentials or recompute entitlement locally.
 */

import { api, ApiError } from "../apiClient";
import {
  denyDecision,
  parseCapabilityDecision,
  parseCapabilityList,
  parseCapabilityMetadata,
  CapabilityDtoError,
} from "./capabilityDto";
import { isCapabilityKey, type CapabilityKey } from "./keys";
import type { CapabilityDecisionDto, CapabilityMetadata } from "./types";

const CAPABILITIES_BASE = "/api/v1/capabilities";

export type CapabilityEvaluateContext = Record<string, string | number | boolean | null | undefined>;

export class CapabilityClientError extends Error {
  constructor(
    message: string,
    public readonly code:
      | "UNKNOWN_KEY"
      | "NETWORK"
      | "OFFLINE"
      | "DTO_INVALID"
      | "HTTP",
    public readonly cause?: unknown,
  ) {
    super(message);
    this.name = "CapabilityClientError";
  }
}

function assertKnownKey(key: string): CapabilityKey {
  if (!isCapabilityKey(key)) {
    throw new CapabilityClientError(
      `Unknown capability key is not allowed: ${key}`,
      "UNKNOWN_KEY",
    );
  }
  return key;
}

function toClientError(error: unknown): CapabilityClientError {
  if (error instanceof CapabilityClientError) return error;
  if (error instanceof CapabilityDtoError) {
    return new CapabilityClientError(error.message, error.code === "UNKNOWN_KEY" ? "UNKNOWN_KEY" : "DTO_INVALID", error);
  }
  if (error instanceof ApiError) {
    if (error.code === "BACKEND_OFFLINE" || error.status === 0) {
      return new CapabilityClientError(
        "离线状态下无法验证授权",
        "OFFLINE",
        error,
      );
    }
    return new CapabilityClientError(error.message || "Capability request failed", "HTTP", error);
  }
  if (error instanceof TypeError) {
    return new CapabilityClientError("离线状态下无法验证授权", "OFFLINE", error);
  }
  return new CapabilityClientError(
    error instanceof Error ? error.message : "Capability request failed",
    "NETWORK",
    error,
  );
}

function buildQuery(context?: CapabilityEvaluateContext): string {
  if (!context) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(context)) {
    if (value === undefined || value === null) continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/**
 * Offline / transport failure fallback — never defaults to allowed=true.
 */
export function offlineFallbackDecision(key: CapabilityKey): CapabilityDecisionDto {
  return denyDecision(
    key,
    "CAPABILITY_OFFLINE_NOT_ALLOWED",
    "离线状态下无法验证授权",
  );
}

export function networkFallbackDecision(key: CapabilityKey, message?: string): CapabilityDecisionDto {
  return denyDecision(
    key,
    "CAPABILITY_UNKNOWN",
    message || "无法获取能力授权状态，请稍后重试",
  );
}

export const capabilityClient = {
  /** GET /api/v1/capabilities */
  async list(): Promise<CapabilityMetadata[]> {
    try {
      const raw = await api<unknown>(CAPABILITIES_BASE);
      return parseCapabilityList(raw);
    } catch (error) {
      throw toClientError(error);
    }
  },

  /** GET /api/v1/capabilities/{key} — returns Decision (not recomputed). */
  async get(key: string): Promise<CapabilityDecisionDto> {
    const capabilityKey = assertKnownKey(key);
    try {
      const raw = await api<unknown>(`${CAPABILITIES_BASE}/${encodeURIComponent(capabilityKey)}`);
      // Backend may return decision directly, or wrap {decision|capability}.
      if (raw && typeof raw === "object" && "decision" in (raw as object)) {
        return parseCapabilityDecision((raw as { decision: unknown }).decision);
      }
      if (raw && typeof raw === "object" && "allowed" in (raw as object)) {
        return parseCapabilityDecision(raw);
      }
      // Metadata-only response: treat as not a grant; caller should use evaluate.
      const meta = parseCapabilityMetadata(raw);
      return denyDecision(
        meta.key,
        meta.shipped ? "CAPABILITY_UNKNOWN" : "CAPABILITY_NOT_SHIPPED",
        meta.shipped
          ? "能力状态不完整，无法确认授权"
          : "该功能尚未发布",
        meta.availability,
      );
    } catch (error) {
      const clientError = toClientError(error);
      if (clientError.code === "UNKNOWN_KEY" || clientError.code === "DTO_INVALID") {
        throw clientError;
      }
      if (clientError.code === "OFFLINE") {
        return offlineFallbackDecision(capabilityKey);
      }
      return networkFallbackDecision(capabilityKey, clientError.message);
    }
  },

  /**
   * Evaluate capability with optional context query params.
   * `allowed` is always the backend Decision value (or fail-closed fallback).
   */
  async evaluate(
    key: string,
    context?: CapabilityEvaluateContext,
  ): Promise<CapabilityDecisionDto> {
    const capabilityKey = assertKnownKey(key);
    try {
      const raw = await api<unknown>(
        `${CAPABILITIES_BASE}/${encodeURIComponent(capabilityKey)}${buildQuery(context)}`,
      );
      if (raw && typeof raw === "object" && "decision" in (raw as object)) {
        return parseCapabilityDecision((raw as { decision: unknown }).decision);
      }
      return parseCapabilityDecision(raw);
    } catch (error) {
      const clientError = toClientError(error);
      if (clientError.code === "UNKNOWN_KEY" || clientError.code === "DTO_INVALID") {
        throw clientError;
      }
      if (clientError.code === "OFFLINE") {
        return offlineFallbackDecision(capabilityKey);
      }
      return networkFallbackDecision(capabilityKey, clientError.message);
    }
  },
};

export type CapabilityClient = typeof capabilityClient;
