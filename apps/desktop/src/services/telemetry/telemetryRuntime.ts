import { getTelemetryConsent } from "../../stores/telemetry/telemetryStore";
import { readTelemetryBuildConfig } from "./config";
import { createBrowserTelemetryStorage } from "./installId";
import { TelemetryClient } from "./telemetryClient";
import { createTelemetryTransportFromConfig } from "./transport";

const APP_LAUNCHED_SESSION_KEY = "storylens.telemetry.app_launched.handled";

let client: TelemetryClient | null = null;

export function getAppTelemetryClient(): TelemetryClient {
  if (!client) {
    client = new TelemetryClient({
      getConsent: getTelemetryConsent,
      storage: createBrowserTelemetryStorage(),
      transport: createTelemetryTransportFromConfig(readTelemetryBuildConfig()),
    });
  }
  return client;
}

/** Once per browser session after local API is ready; HMR-safe; respects consent. */
export function trackAppLaunchedOncePerSession(): void {
  if (typeof sessionStorage === "undefined") return;
  if (sessionStorage.getItem(APP_LAUNCHED_SESSION_KEY)) return;
  sessionStorage.setItem(APP_LAUNCHED_SESSION_KEY, "1");
  getAppTelemetryClient().track("app_launched");
}
