/**
 * Unified VIP license client API.
 *
 * activateLicense / refreshLicense / deactivateLicense / getLicenseStatus / hasFeature
 *
 * This stage wires a clearly marked DEV mock. Real HTTP license service is not
 * implemented; see types.ts for reserved contracts and docs/vip-license-plan.md.
 */

import { hasFeature as gateHasFeature, type FeatureGateResult, type FeatureKey } from "./features";
import {
  isMockActivationAllowed,
  MOCK_LICENSE_SERVICE_MARKER,
  mockActivate,
  mockRefresh,
  toStoredPayload,
} from "./mockLicenseService";
import {
  createDevLocalStorageLicenseStorage,
  createMemoryLicenseStorage,
  type LicenseStorage,
} from "./storage";
import {
  LicenseServiceError,
  type LicenseSnapshot,
  type LicenseStatus,
  type StoredLicensePayload,
} from "./types";

export type LicenseService = {
  activateLicense(code: string): Promise<LicenseSnapshot>;
  refreshLicense(): Promise<LicenseSnapshot>;
  deactivateLicense(): Promise<LicenseSnapshot>;
  getLicenseStatus(): LicenseSnapshot;
  hasFeature(featureKey: FeatureKey): FeatureGateResult;
  /** Load persisted state (call once at app bootstrap). */
  hydrate(): Promise<LicenseSnapshot>;
  /** Test / DI helper. */
  getStorage(): LicenseStorage;
};

function editionLabelFor(status: LicenseStatus): string {
  switch (status) {
    case "VIP_ACTIVE":
    case "VIP_OFFLINE_GRACE":
      return "VIP";
    case "VIP_EXPIRED":
      return "VIP（已过期）";
    case "VIP_INVALID":
      return "VIP（无效）";
    case "FREE":
    default:
      return "免费版";
  }
}

function toSnapshot(payload: StoredLicensePayload | null): LicenseSnapshot {
  const status = payload?.status ?? "FREE";
  return {
    status,
    license: payload?.license ?? null,
    editionLabel: editionLabelFor(status),
    usingMockService: true,
    commerceComingSoon: true,
  };
}

export type CreateLicenseServiceOptions = {
  storage?: LicenseStorage;
  /** Force mock activation even when import.meta.env.DEV is false (tests only). */
  allowMockInTests?: boolean;
};

let sharedService: LicenseService | null = null;

export function createLicenseService(options: CreateLicenseServiceOptions = {}): LicenseService {
  const storage =
    options.storage ??
    (typeof window !== "undefined"
      ? createDevLocalStorageLicenseStorage()
      : createMemoryLicenseStorage());

  let cached: StoredLicensePayload | null = null;
  let hydrated = false;

  const allowMock = () => options.allowMockInTests === true || isMockActivationAllowed();

  const service: LicenseService = {
    getStorage() {
      return storage;
    },

    async hydrate() {
      cached = await storage.read();
      hydrated = true;
      return toSnapshot(cached);
    },

    getLicenseStatus() {
      if (!hydrated) {
        return toSnapshot(null);
      }
      return toSnapshot(cached);
    },

    hasFeature(featureKey: FeatureKey) {
      return gateHasFeature(featureKey);
    },

    async activateLicense(code: string) {
      if (!allowMock()) {
        throw new LicenseServiceError(
          "coming_soon",
          "VIP 授权服务即将开放。当前版本为免费版，不限制已有功能。",
        );
      }
      if (!code.trim()) {
        throw new LicenseServiceError("invalid_code", "请输入激活码。");
      }
      // DEV MOCK path — not a real paid activation.
      void MOCK_LICENSE_SERVICE_MARKER;
      const result = mockActivate(code);
      const payload = toStoredPayload(result);
      await storage.write(payload);
      cached = payload;
      hydrated = true;
      return toSnapshot(cached);
    },

    async refreshLicense() {
      if (!allowMock()) {
        throw new LicenseServiceError(
          "coming_soon",
          "VIP 授权服务即将开放，暂无法刷新远程授权。",
        );
      }
      if (!hydrated) {
        cached = await storage.read();
        hydrated = true;
      }
      const result = mockRefresh(cached);
      const payload = toStoredPayload(result);
      await storage.write(payload);
      cached = payload;
      return toSnapshot(cached);
    },

    async deactivateLicense() {
      await storage.clear();
      cached = null;
      hydrated = true;
      return toSnapshot(null);
    },
  };

  return service;
}

/** Process-wide singleton used by the settings card and store. */
export function getLicenseService(): LicenseService {
  if (!sharedService) {
    sharedService = createLicenseService();
  }
  return sharedService;
}

/** Test helper to replace the singleton. */
export function setLicenseServiceForTests(service: LicenseService | null): void {
  sharedService = service;
}

export {
  FEATURE_KEYS,
  FEATURE_REGISTRY,
  hasFeature,
  listVipFeatureDefinitions,
  type FeatureGateResult,
  type FeatureKey,
} from "./features";

export {
  LICENSE_FILE_RELATIVE_PATH,
  LICENSE_STORAGE_TARGET_DESCRIPTION,
  createMemoryLicenseStorage,
  createDevLocalStorageLicenseStorage,
  createReservedTauriLicenseStorage,
} from "./storage";

export {
  MOCK_ACTIVATION_CODES,
  MOCK_LICENSE_SERVICE_MARKER,
  isMockActivationAllowed,
} from "./mockLicenseService";

export type {
  LicenseInfo,
  LicenseSnapshot,
  LicenseStatus,
  StoredLicensePayload,
  ActivateLicenseRequest,
  ActivateLicenseResponse,
  RefreshLicenseRequest,
  RefreshLicenseResponse,
  DeactivateLicenseRequest,
  DeactivateLicenseResponse,
  GetLicenseStatusResponse,
} from "./types";

export { LicenseServiceError } from "./types";
