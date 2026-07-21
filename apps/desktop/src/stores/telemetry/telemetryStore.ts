import { create } from "zustand";
import {
  createBrowserTelemetryStorage,
  readInstallId,
  resetInstallId as resetStoredInstallId,
} from "../../services/telemetry/installId";

export type TelemetryConsent = "UNKNOWN" | "ENABLED" | "DISABLED";

const CONSENT_STORAGE_KEY = "storylens.telemetry.consent";

const storage = createBrowserTelemetryStorage();

function readStoredConsent(): TelemetryConsent {
  const raw = storage.getItem(CONSENT_STORAGE_KEY);
  if (raw === "ENABLED" || raw === "DISABLED") {
    return raw;
  }
  return "UNKNOWN";
}

function writeConsent(consent: TelemetryConsent) {
  if (consent === "UNKNOWN") {
    storage.removeItem(CONSENT_STORAGE_KEY);
    return;
  }
  storage.setItem(CONSENT_STORAGE_KEY, consent);
}

type TelemetryStoreState = {
  consent: TelemetryConsent;
  installIdPreview: string | null;
  setAnonymousTelemetryEnabled: (enabled: boolean) => void;
  resetAnonymousInstallId: () => void;
  refreshInstallIdPreview: () => void;
};

export const useTelemetryStore = create<TelemetryStoreState>((set) => ({
  consent: typeof window !== "undefined" ? readStoredConsent() : "UNKNOWN",
  installIdPreview:
    typeof window !== "undefined" ? readInstallId(storage) : null,
  setAnonymousTelemetryEnabled: (enabled) => {
    const next: TelemetryConsent = enabled ? "ENABLED" : "DISABLED";
    writeConsent(next);
    set({ consent: next });
  },
  resetAnonymousInstallId: () => {
    const id = resetStoredInstallId(storage);
    set({ installIdPreview: id });
  },
  refreshInstallIdPreview: () => {
    set({ installIdPreview: readInstallId(storage) });
  },
}));

/** Non-React access for telemetry client wiring. */
export function getTelemetryConsent(): TelemetryConsent {
  return readStoredConsent();
}
