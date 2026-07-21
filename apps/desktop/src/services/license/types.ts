/**
 * StoryLens VIP license client types and future license-service contracts.
 *
 * Real payment / Afdian / remote signing are intentionally out of scope for
 * this foundation stage. See docs/vip-license-plan.md.
 */

/** Client-facing authorization state machine. */
export type LicenseStatus =
  | "FREE"
  | "VIP_ACTIVE"
  | "VIP_EXPIRED"
  | "VIP_OFFLINE_GRACE"
  | "VIP_INVALID";

export type LicensePlan = "free" | "vip";

/**
 * Signed license payload fields persisted locally.
 * Must never include novel body text or API keys.
 * Client stores only the signature blob + public verification material later;
 * signing private keys never ship in the open-source client.
 */
export type LicenseInfo = {
  license_id: string;
  plan: LicensePlan;
  issued_at: string;
  expires_at: string | null;
  device_limit: number;
  features: string[];
  last_verified_at: string | null;
  signature: string;
};

export type LicenseSnapshot = {
  status: LicenseStatus;
  license: LicenseInfo | null;
  /** Human label for UI, e.g. 免费版 / VIP. */
  editionLabel: string;
  /** True when the active backend is the development mock. */
  usingMockService: boolean;
  /** True when real paid activation is not available yet. */
  commerceComingSoon: boolean;
};

/** Persisted envelope written under the reserved license path. */
export type StoredLicensePayload = {
  /** Schema marker so future formats can migrate. */
  schema_version: 1;
  /** Explicit marker that mock payloads are not paid entitlements. */
  source: "mock_dev" | "license_service";
  status: LicenseStatus;
  license: LicenseInfo | null;
  /** Offline grace window start (ISO), if applicable. */
  offline_grace_started_at?: string | null;
};

// ---------------------------------------------------------------------------
// Future license service HTTP contracts (not implemented in this stage)
// ---------------------------------------------------------------------------

/** POST /license/activate */
export type ActivateLicenseRequest = {
  code: string;
  device_id: string;
  app_version?: string;
};

/** POST /license/activate */
export type ActivateLicenseResponse = {
  status: LicenseStatus;
  license: LicenseInfo;
};

/** POST /license/refresh */
export type RefreshLicenseRequest = {
  license_id: string;
  device_id: string;
  signature: string;
};

/** POST /license/refresh */
export type RefreshLicenseResponse = {
  status: LicenseStatus;
  license: LicenseInfo;
};

/** POST /license/deactivate */
export type DeactivateLicenseRequest = {
  license_id: string;
  device_id: string;
  signature: string;
};

/** POST /license/deactivate */
export type DeactivateLicenseResponse = {
  status: "FREE";
  ok: true;
};

/** GET /license/status?license_id=&device_id= */
export type GetLicenseStatusResponse = {
  status: LicenseStatus;
  license: LicenseInfo | null;
};

export type LicenseServiceErrorCode =
  | "coming_soon"
  | "mock_only_in_dev"
  | "invalid_code"
  | "invalid_signature"
  | "expired"
  | "storage_unavailable"
  | "unknown";

export class LicenseServiceError extends Error {
  readonly code: LicenseServiceErrorCode;

  constructor(code: LicenseServiceErrorCode, message: string) {
    super(message);
    this.name = "LicenseServiceError";
    this.code = code;
  }
}
