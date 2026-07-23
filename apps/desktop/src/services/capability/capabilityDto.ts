/**
 * DTO guards + snake_case → camelCase normalization for Capability HTTP responses.
 * Frontend never recomputes `allowed` from license state.
 */

import { isCapabilityKey, type CapabilityKey } from "./keys";
import type {
  CapabilityAvailability,
  CapabilityDecisionDto,
  CapabilityMetadata,
  CapabilityReasonCode,
  CostClass,
  QuotaDecisionDto,
  WholeBookAnalysisMode,
} from "./types";

const AVAILABILITIES = new Set<CapabilityAvailability>([
  "unavailable",
  "preview",
  "available",
]);

const REASON_CODES = new Set<CapabilityReasonCode>([
  "CAPABILITY_NOT_SHIPPED",
  "CAPABILITY_NOT_LICENSED",
  "CAPABILITY_QUOTA_EXCEEDED",
  "CAPABILITY_OFFLINE_NOT_ALLOWED",
  "CAPABILITY_LICENSE_EXPIRED",
  "CAPABILITY_LICENSE_INVALID",
  "CAPABILITY_AVAILABLE",
  "CAPABILITY_PREVIEW_ONLY",
  "CAPABILITY_UNKNOWN",
]);

const MODES = new Set<WholeBookAnalysisMode>([
  "whole_book_native",
  "whole_book_enhanced",
]);

const COST_CLASSES = new Set<CostClass>(["free", "low", "medium", "high"]);

export class CapabilityDtoError extends Error {
  constructor(
    message: string,
    public readonly code: "DTO_INVALID" | "UNKNOWN_KEY" = "DTO_INVALID",
  ) {
    super(message);
    this.name = "CapabilityDtoError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function pickString(raw: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = raw[key];
    if (typeof value === "string") return value;
  }
  return undefined;
}

function pickBoolean(raw: Record<string, unknown>, ...keys: string[]): boolean | undefined {
  for (const key of keys) {
    const value = raw[key];
    if (typeof value === "boolean") return value;
  }
  return undefined;
}

function pickNumber(raw: Record<string, unknown>, ...keys: string[]): number | null | undefined {
  for (const key of keys) {
    const value = raw[key];
    if (value === null) return null;
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return undefined;
}

function requireCapabilityKey(value: unknown, field: string): CapabilityKey {
  if (typeof value !== "string" || !isCapabilityKey(value)) {
    throw new CapabilityDtoError(
      `Unknown or invalid capability key in ${field}: ${String(value)}`,
      "UNKNOWN_KEY",
    );
  }
  return value;
}

function parseAvailability(value: unknown, field: string): CapabilityAvailability {
  if (typeof value === "string" && AVAILABILITIES.has(value as CapabilityAvailability)) {
    return value as CapabilityAvailability;
  }
  throw new CapabilityDtoError(`Invalid availability in ${field}: ${String(value)}`);
}

function parseReasonCode(value: unknown, field: string): CapabilityReasonCode {
  if (typeof value === "string" && REASON_CODES.has(value as CapabilityReasonCode)) {
    return value as CapabilityReasonCode;
  }
  throw new CapabilityDtoError(`Invalid reasonCode in ${field}: ${String(value)}`);
}

function parseModes(value: unknown): WholeBookAnalysisMode[] | undefined {
  if (value === undefined || value === null) return undefined;
  if (!Array.isArray(value)) {
    throw new CapabilityDtoError("supportedModes must be an array");
  }
  const modes: WholeBookAnalysisMode[] = [];
  for (const item of value) {
    if (typeof item !== "string" || !MODES.has(item as WholeBookAnalysisMode)) {
      throw new CapabilityDtoError(`Invalid analysis mode: ${String(item)}`);
    }
    modes.push(item as WholeBookAnalysisMode);
  }
  return modes;
}

function parseQuota(raw: unknown): QuotaDecisionDto | null | undefined {
  if (raw === undefined) return undefined;
  if (raw === null) return null;
  if (!isRecord(raw)) {
    throw new CapabilityDtoError("quota must be an object or null");
  }
  const allowed = pickBoolean(raw, "allowed");
  const reasonRaw = pickString(raw, "reasonCode", "reason_code");
  if (typeof allowed !== "boolean" || reasonRaw === undefined) {
    throw new CapabilityDtoError("quota requires allowed and reasonCode");
  }
  return {
    allowed,
    reasonCode: parseReasonCode(reasonRaw, "quota.reasonCode"),
    policyKey: pickString(raw, "policyKey", "policy_key"),
    policyKind: pickString(raw, "policyKind", "policy_kind"),
    limit: pickNumber(raw, "limit"),
    used: pickNumber(raw, "used"),
    reserved: pickNumber(raw, "reserved"),
    remaining: pickNumber(raw, "remaining"),
    resetAt:
      raw.resetAt === null || raw.reset_at === null
        ? null
        : pickString(raw, "resetAt", "reset_at") ?? undefined,
    message: pickString(raw, "message"),
  };
}

/** Normalize list item / metadata payload from backend. */
export function parseCapabilityMetadata(raw: unknown): CapabilityMetadata {
  if (!isRecord(raw)) {
    throw new CapabilityDtoError("Capability metadata must be an object");
  }
  const key = requireCapabilityKey(pickString(raw, "key", "capabilityKey", "capability_key"), "metadata.key");
  const displayName =
    pickString(raw, "displayName", "display_name", "label") ?? key;
  const description = pickString(raw, "description") ?? "";
  const shipped = pickBoolean(raw, "shipped");
  const requiresLicense = pickBoolean(raw, "requiresLicense", "requires_license");
  const availabilityRaw = pickString(raw, "availability");
  if (typeof shipped !== "boolean" || typeof requiresLicense !== "boolean" || !availabilityRaw) {
    throw new CapabilityDtoError("Capability metadata missing required fields");
  }
  const estimated = pickString(raw, "estimatedCostClass", "estimated_cost_class");
  if (estimated !== undefined && !COST_CLASSES.has(estimated as CostClass)) {
    throw new CapabilityDtoError(`Invalid estimatedCostClass: ${estimated}`);
  }
  return {
    key,
    displayName,
    description,
    shipped,
    requiresLicense,
    availability: parseAvailability(availabilityRaw, "metadata.availability"),
    previewVisible: pickBoolean(raw, "previewVisible", "preview_visible"),
    supportedModes: parseModes(raw.supportedModes ?? raw.supported_modes),
    quotaPolicyKey: pickString(raw, "quotaPolicyKey", "quota_policy_key"),
    estimatedCostClass: estimated as CostClass | undefined,
    offlineAllowed: pickBoolean(raw, "offlineAllowed", "offline_allowed"),
    label: displayName,
  };
}

export function parseCapabilityList(raw: unknown): CapabilityMetadata[] {
  const items = Array.isArray(raw)
    ? raw
    : isRecord(raw) && Array.isArray(raw.items)
      ? raw.items
      : isRecord(raw) && Array.isArray(raw.capabilities)
        ? raw.capabilities
        : null;
  if (!items) {
    throw new CapabilityDtoError("Capability list response must be an array or {items|capabilities}");
  }
  return items.map(parseCapabilityMetadata);
}

/** Normalize decision payload — `allowed` is taken as-is from backend. */
export function parseCapabilityDecision(raw: unknown): CapabilityDecisionDto {
  if (!isRecord(raw)) {
    throw new CapabilityDtoError("Capability decision must be an object");
  }
  const capabilityKey = requireCapabilityKey(
    pickString(raw, "capabilityKey", "capability_key", "key"),
    "decision.capabilityKey",
  );
  const allowed = pickBoolean(raw, "allowed");
  const reasonRaw = pickString(raw, "reasonCode", "reason_code");
  const availabilityRaw = pickString(raw, "availability");
  if (typeof allowed !== "boolean" || !reasonRaw || !availabilityRaw) {
    throw new CapabilityDtoError("Capability decision missing required fields");
  }
  const displayMessage =
    pickString(raw, "displayMessage", "display_message", "message") ?? "";
  return {
    capabilityKey,
    allowed,
    reasonCode: parseReasonCode(reasonRaw, "decision.reasonCode"),
    availability: parseAvailability(availabilityRaw, "decision.availability"),
    displayMessage,
    supportedModes: parseModes(raw.supportedModes ?? raw.supported_modes),
    quota: parseQuota(raw.quota),
    usage: pickNumber(raw, "usage"),
    remaining: pickNumber(raw, "remaining"),
    offlineStatus: pickString(raw, "offlineStatus", "offline_status"),
    licenseStatus: pickString(raw, "licenseStatus", "license_status"),
    evaluatedAt: pickString(raw, "evaluatedAt", "evaluated_at"),
    previewOnly: pickBoolean(raw, "previewOnly", "preview_only"),
    message: displayMessage,
  };
}

/** Fail-closed decision used when network/DTO fails — never grants access. */
export function denyDecision(
  key: CapabilityKey,
  reasonCode: CapabilityReasonCode,
  message: string,
  availability: CapabilityAvailability = "unavailable",
): CapabilityDecisionDto {
  return {
    capabilityKey: key,
    allowed: false,
    reasonCode,
    availability,
    displayMessage: message,
    message,
    previewOnly: false,
    evaluatedAt: new Date().toISOString(),
  };
}
