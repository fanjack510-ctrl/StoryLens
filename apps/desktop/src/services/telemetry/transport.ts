import type { TelemetryEventName, TelemetryScalar } from "./schema";

export interface TelemetryTransport {
  send(
    event: TelemetryEventName,
    properties: Record<string, TelemetryScalar>,
    distinctId: string,
  ): Promise<void>;
}

export class NoopTelemetryTransport implements TelemetryTransport {
  async send(
    _event: TelemetryEventName,
    _properties: Record<string, TelemetryScalar>,
    _distinctId: string,
  ): Promise<void> {
    /* intentionally empty */
  }
}

export type HttpTelemetryTransportOptions = {
  endpoint: string;
  projectKey: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
};

/**
 * Minimal PostHog-compatible HTTP capture (`/capture/` or full URL).
 * No session replay, autocapture, or error stack collection.
 */
export class HttpTelemetryTransport implements TelemetryTransport {
  private readonly endpoint: string;
  private readonly projectKey: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: HttpTelemetryTransportOptions) {
    this.endpoint = options.endpoint;
    this.projectKey = options.projectKey;
    this.timeoutMs = options.timeoutMs ?? 8_000;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  async send(
    event: TelemetryEventName,
    properties: Record<string, TelemetryScalar>,
    distinctId: string,
  ): Promise<void> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      await this.fetchImpl(this.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: this.projectKey,
          event,
          properties: {
            ...properties,
            distinct_id: distinctId,
          },
        }),
        signal: controller.signal,
      });
    } catch {
      /* network failure: silent degrade */
    } finally {
      clearTimeout(timer);
    }
  }
}

export function createTelemetryTransportFromConfig(
  config: { endpoint: string | null; projectKey: string | null },
  overrides?: { fetchImpl?: typeof fetch; timeoutMs?: number },
): TelemetryTransport {
  if (!config.endpoint || !config.projectKey) {
    return new NoopTelemetryTransport();
  }
  return new HttpTelemetryTransport({
    endpoint: config.endpoint,
    projectKey: config.projectKey,
    fetchImpl: overrides?.fetchImpl,
    timeoutMs: overrides?.timeoutMs,
  });
}
