/** Persisted in the app user-config area (localStorage in the desktop webview). */
export const TELEMETRY_INSTALL_ID_KEY = "storylens.telemetry.install_id";

export type TelemetryStorage = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
};

export function createBrowserTelemetryStorage(): TelemetryStorage {
  return {
    getItem: (key) => {
      try {
        return localStorage.getItem(key);
      } catch {
        return null;
      }
    },
    setItem: (key, value) => {
      try {
        localStorage.setItem(key, value);
      } catch {
        /* ignore quota / private mode */
      }
    },
    removeItem: (key) => {
      try {
        localStorage.removeItem(key);
      } catch {
        /* ignore */
      }
    },
  };
}

function newInstallId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `anon-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

export function getOrCreateInstallId(storage: TelemetryStorage): string {
  const existing = storage.getItem(TELEMETRY_INSTALL_ID_KEY);
  if (existing && existing.length > 0) {
    return existing;
  }
  const id = newInstallId();
  storage.setItem(TELEMETRY_INSTALL_ID_KEY, id);
  return id;
}

export function resetInstallId(storage: TelemetryStorage): string {
  const id = newInstallId();
  storage.setItem(TELEMETRY_INSTALL_ID_KEY, id);
  return id;
}

export function readInstallId(storage: TelemetryStorage): string | null {
  return storage.getItem(TELEMETRY_INSTALL_ID_KEY);
}
