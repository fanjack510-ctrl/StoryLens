/**
 * DEV MOCK license backend.
 *
 * This module is a development stand-in only. It MUST NOT be presented as a
 * real paid entitlement, Afdian fulfillment, or cryptographically verified
 * license authority. Signatures below are opaque mock tokens, not real signatures.
 */

import type { LicenseInfo, LicenseStatus, StoredLicensePayload } from "./types";
import { LicenseServiceError } from "./types";

export const MOCK_LICENSE_SERVICE_MARKER =
  "DEV_MOCK_LICENSE_SERVICE — not a real paid entitlement";

/** Well-known mock activation codes for local development / tests. */
export const MOCK_ACTIVATION_CODES = {
  ACTIVE: "MOCK-VIP-ACTIVE",
  EXPIRED: "MOCK-VIP-EXPIRED",
  OFFLINE_GRACE: "MOCK-VIP-OFFLINE-GRACE",
  INVALID: "MOCK-VIP-INVALID",
} as const;

const MOCK_FEATURES = [
  "batch_analysis",
  "novel_rhythm_map",
  "character_arc",
  "foreshadow_tracking",
  "novel_comparison",
  "advanced_report",
  "inspiration_center",
] as const;

function isoDaysFromNow(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString();
}

function isoDaysAgo(days: number): string {
  return isoDaysFromNow(-days);
}

function buildLicense(partial: Partial<LicenseInfo> & Pick<LicenseInfo, "license_id" | "signature">): LicenseInfo {
  const now = new Date().toISOString();
  return {
    license_id: partial.license_id,
    plan: partial.plan ?? "vip",
    issued_at: partial.issued_at ?? isoDaysAgo(7),
    expires_at: partial.expires_at ?? isoDaysFromNow(30),
    device_limit: partial.device_limit ?? 2,
    features: partial.features ?? [...MOCK_FEATURES],
    last_verified_at: partial.last_verified_at ?? now,
    signature: partial.signature,
  };
}

export function isMockActivationAllowed(): boolean {
  return import.meta.env.DEV === true;
}

export type MockActivateResult = {
  status: LicenseStatus;
  license: LicenseInfo | null;
  offline_grace_started_at?: string | null;
};

/**
 * Resolve a mock activation code into a StoredLicensePayload-shaped result.
 * Caller (licenseService) must enforce DEV-only gating before invoking.
 */
export function mockActivate(code: string): MockActivateResult {
  const normalized = code.trim().toUpperCase();

  switch (normalized) {
    case MOCK_ACTIVATION_CODES.ACTIVE:
      return {
        status: "VIP_ACTIVE",
        license: buildLicense({
          license_id: "mock-license-active",
          signature: "mock-sig-active-NOT-REAL",
        }),
      };
    case MOCK_ACTIVATION_CODES.EXPIRED:
      return {
        status: "VIP_EXPIRED",
        license: buildLicense({
          license_id: "mock-license-expired",
          expires_at: isoDaysAgo(3),
          last_verified_at: isoDaysAgo(3),
          signature: "mock-sig-expired-NOT-REAL",
        }),
      };
    case MOCK_ACTIVATION_CODES.OFFLINE_GRACE:
      return {
        status: "VIP_OFFLINE_GRACE",
        license: buildLicense({
          license_id: "mock-license-offline-grace",
          last_verified_at: isoDaysAgo(5),
          signature: "mock-sig-offline-grace-NOT-REAL",
        }),
        offline_grace_started_at: isoDaysAgo(2),
      };
    case MOCK_ACTIVATION_CODES.INVALID:
      return {
        status: "VIP_INVALID",
        license: buildLicense({
          license_id: "mock-license-invalid",
          signature: "mock-sig-INVALID-TAMPERED",
        }),
      };
    default:
      throw new LicenseServiceError(
        "invalid_code",
        "无效的 Mock 激活码。开发可用：MOCK-VIP-ACTIVE / EXPIRED / OFFLINE-GRACE / INVALID。",
      );
  }
}

export function mockRefresh(current: StoredLicensePayload | null): MockActivateResult {
  if (!current?.license) {
    return { status: "FREE", license: null };
  }
  if (current.status === "VIP_INVALID") {
    throw new LicenseServiceError("invalid_signature", "Mock：签名无效，无法刷新。");
  }
  if (current.status === "VIP_EXPIRED") {
    return {
      status: "VIP_EXPIRED",
      license: {
        ...current.license,
        last_verified_at: new Date().toISOString(),
      },
    };
  }
  if (current.status === "VIP_OFFLINE_GRACE") {
    // Successful mock refresh restores active.
    return {
      status: "VIP_ACTIVE",
      license: {
        ...current.license,
        last_verified_at: new Date().toISOString(),
        signature: "mock-sig-refreshed-NOT-REAL",
      },
    };
  }
  return {
    status: current.status,
    license: {
      ...current.license,
      last_verified_at: new Date().toISOString(),
    },
  };
}

export function toStoredPayload(result: MockActivateResult): StoredLicensePayload {
  return {
    schema_version: 1,
    source: "mock_dev",
    status: result.status,
    license: result.license,
    offline_grace_started_at: result.offline_grace_started_at ?? null,
  };
}
