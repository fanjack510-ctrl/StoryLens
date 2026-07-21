import type { TelemetryConsent } from "../../stores/telemetry/telemetryStore";
import { getDefaultTelemetryContext } from "./context";
import { getOrCreateInstallId, type TelemetryStorage } from "./installId";
import { validateTelemetryPayload } from "./schema";
import type { TelemetryTransport } from "./transport";

export type TelemetryClientDeps = {
  getConsent: () => TelemetryConsent;
  storage: TelemetryStorage;
  transport: TelemetryTransport;
  getContext?: () => ReturnType<typeof getDefaultTelemetryContext>;
};

export class TelemetryClient {
  private readonly getConsent: () => TelemetryConsent;
  private readonly storage: TelemetryStorage;
  private readonly transport: TelemetryTransport;
  private readonly getContext: () => ReturnType<typeof getDefaultTelemetryContext>;

  constructor(deps: TelemetryClientDeps) {
    this.getConsent = deps.getConsent;
    this.storage = deps.storage;
    this.transport = deps.transport;
    this.getContext = deps.getContext ?? getDefaultTelemetryContext;
  }

  /** Returns false when gated off or validation fails. */
  track(event: string, extraProperties: Record<string, unknown> = {}): boolean {
    if (this.getConsent() !== "ENABLED") {
      return false;
    }

    const merged = {
      ...this.getContext(),
      ...extraProperties,
    };

    const validation = validateTelemetryPayload(event, merged);
    if (!validation.ok) {
      return false;
    }

    const installId = getOrCreateInstallId(this.storage);
    void this.transport.send(
      validation.payload.event,
      validation.payload.properties as Record<string, string | number | boolean>,
      installId,
    );
    return true;
  }
}
