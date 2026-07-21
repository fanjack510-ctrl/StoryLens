/**
 * License storage abstraction.
 *
 * Reserved production path (Windows):
 *   %LOCALAPPDATA%/StoryLens/license/storylens.license
 *
 * Requirements:
 * - Outside the install directory (survives upgrades)
 * - Never committed to Git
 * - Never stores API keys or novel body text
 * - Never stores signing private keys (future: public verify key only)
 *
 * The browser/Vite layer cannot safely write %LOCALAPPDATA% without a Tauri
 * command. This module provides an interface + in-memory / localStorage mocks
 * for development and tests. Do not bypass Tauri FS security boundaries.
 */

import type { StoredLicensePayload } from "./types";

/** Documented reserved path for the future Tauri-backed writer. */
export const LICENSE_FILE_RELATIVE_PATH = "license/storylens.license";

export const LICENSE_STORAGE_TARGET_DESCRIPTION =
  "%LOCALAPPDATA%/StoryLens/license/storylens.license";

const FORBIDDEN_PAYLOAD_KEYS = [
  "api_key",
  "apiKey",
  "ALIYUN",
  "novel_text",
  "novelText",
  "chapter_text",
  "paragraph_text",
  "private_key",
  "privateKey",
  "signing_key",
] as const;

export type LicenseStorage = {
  readonly kind: "memory" | "local_storage_dev" | "tauri_reserved";
  readonly targetPathDescription: string;
  read(): Promise<StoredLicensePayload | null>;
  write(payload: StoredLicensePayload): Promise<void>;
  clear(): Promise<void>;
};

export function assertSafeLicensePayload(payload: StoredLicensePayload): void {
  const raw = JSON.stringify(payload);
  for (const key of FORBIDDEN_PAYLOAD_KEYS) {
    if (raw.toLowerCase().includes(key.toLowerCase())) {
      throw new Error(
        `License payload must not contain sensitive field marker: ${key}`,
      );
    }
  }
  if (payload.license) {
    const licenseKeys = Object.keys(payload.license);
    const allowed = new Set([
      "license_id",
      "plan",
      "issued_at",
      "expires_at",
      "device_limit",
      "features",
      "last_verified_at",
      "signature",
    ]);
    for (const key of licenseKeys) {
      if (!allowed.has(key)) {
        throw new Error(`Unexpected license field: ${key}`);
      }
    }
  }
}

/** In-memory storage for unit tests and ephemeral sessions. */
export function createMemoryLicenseStorage(
  initial: StoredLicensePayload | null = null,
): LicenseStorage {
  let current = initial;
  return {
    kind: "memory",
    targetPathDescription: "memory://storylens.license",
    async read() {
      return current;
    },
    async write(payload) {
      assertSafeLicensePayload(payload);
      current = structuredClone(payload);
    },
    async clear() {
      current = null;
    },
  };
}

const LOCAL_STORAGE_KEY = "storylens.license.dev.mock";

/**
 * DEV-ONLY localStorage-backed mock. Explicitly not the production path.
 * Production must use a future Tauri command writing LICENSE_STORAGE_TARGET_DESCRIPTION.
 */
export function createDevLocalStorageLicenseStorage(): LicenseStorage {
  return {
    kind: "local_storage_dev",
    targetPathDescription: `localStorage:${LOCAL_STORAGE_KEY} (DEV MOCK — not ${LICENSE_STORAGE_TARGET_DESCRIPTION})`,
    async read() {
      try {
        const raw = localStorage.getItem(LOCAL_STORAGE_KEY);
        if (!raw) return null;
        return JSON.parse(raw) as StoredLicensePayload;
      } catch {
        return null;
      }
    },
    async write(payload) {
      assertSafeLicensePayload(payload);
      localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(payload));
    },
    async clear() {
      localStorage.removeItem(LOCAL_STORAGE_KEY);
    },
  };
}

/**
 * Reserved Tauri-backed storage stub.
 * Does not write files from the frontend; awaits a future secure invoke.
 */
export function createReservedTauriLicenseStorage(): LicenseStorage {
  return {
    kind: "tauri_reserved",
    targetPathDescription: LICENSE_STORAGE_TARGET_DESCRIPTION,
    async read() {
      return null;
    },
    async write() {
      throw new Error(
        `Tauri license filesystem bridge is not implemented. Reserved path: ${LICENSE_STORAGE_TARGET_DESCRIPTION}`,
      );
    },
    async clear() {
      throw new Error(
        `Tauri license filesystem bridge is not implemented. Reserved path: ${LICENSE_STORAGE_TARGET_DESCRIPTION}`,
      );
    },
  };
}
