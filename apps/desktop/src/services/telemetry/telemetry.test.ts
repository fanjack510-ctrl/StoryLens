import { describe, expect, it, vi, beforeEach } from "vitest";
import {
  TelemetryClient,
  validateTelemetryPayload,
  getOrCreateInstallId,
  resetInstallId,
  NoopTelemetryTransport,
  HttpTelemetryTransport,
  type TelemetryStorage,
} from "./index";

function memoryStorage(): TelemetryStorage & { dump: () => Record<string, string> } {
  const map = new Map<string, string>();
  return {
    getItem: (k) => map.get(k) ?? null,
    setItem: (k, v) => {
      map.set(k, v);
    },
    removeItem: (k) => {
      map.delete(k);
    },
    dump: () => Object.fromEntries(map),
  };
}

describe("telemetry schema", () => {
  it("accepts whitelisted events and properties", () => {
    const result = validateTelemetryPayload("app_launched", {
      app_version: "0.1.0",
      os_family: "windows",
      locale: "zh-CN",
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.payload.event).toBe("app_launched");
    }
  });

  it("rejects unknown events", () => {
    const result = validateTelemetryPayload("chapter_opened", { app_version: "1" });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/unknown_event/);
  });

  it("rejects unknown properties", () => {
    const result = validateTelemetryPayload("feature_used", {
      feature_key: "export_png",
      mystery_field: "x",
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/unknown_property/);
  });

  it("rejects sensitive properties", () => {
    const result = validateTelemetryPayload("analysis_started", {
      book_title: "secret",
      app_version: "0.1.0",
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/forbidden_property/);
  });
});

describe("TelemetryClient consent gate", () => {
  let storage: ReturnType<typeof memoryStorage>;
  const send = vi.fn(async () => {});
  const transport = { send };

  beforeEach(() => {
    storage = memoryStorage();
    send.mockClear();
  });

  function client(consent: "UNKNOWN" | "ENABLED" | "DISABLED") {
    return new TelemetryClient({
      getConsent: () => consent,
      storage,
      transport,
      getContext: () => ({
        app_version: "0.1.0",
        os_family: "windows",
        locale: "zh-CN",
      }),
    });
  }

  it("does not send by default (UNKNOWN)", () => {
    expect(client("UNKNOWN").track("app_launched")).toBe(false);
    expect(send).not.toHaveBeenCalled();
  });

  it("sends after user consent (ENABLED)", async () => {
    expect(client("ENABLED").track("app_launched")).toBe(true);
    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith(
      "app_launched",
      expect.objectContaining({ app_version: "0.1.0" }),
      expect.any(String),
    );
  });

  it("does not send after user disables", () => {
    expect(client("DISABLED").track("app_launched")).toBe(false);
    expect(send).not.toHaveBeenCalled();
  });

  it("rejects invalid payloads without sending", () => {
    expect(client("ENABLED").track("not_allowed", {})).toBe(false);
    expect(send).not.toHaveBeenCalled();
  });
});

describe("install_id", () => {
  it("can be reset", () => {
    const storage = memoryStorage();
    const first = getOrCreateInstallId(storage);
    const second = resetInstallId(storage);
    expect(second).not.toBe(first);
    expect(getOrCreateInstallId(storage)).toBe(second);
  });
});

describe("HttpTelemetryTransport", () => {
  it("does not throw on network failure", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error("network down");
    });
    const transport = new HttpTelemetryTransport({
      endpoint: "https://example.test/capture/",
      projectKey: "phc_test",
      fetchImpl,
      timeoutMs: 100,
    });
    await expect(
      transport.send("app_launched", { app_version: "0.1.0" }, "install-1"),
    ).resolves.toBeUndefined();
  });
});

describe("NoopTelemetryTransport", () => {
  it("is used when transport is noop", async () => {
    const t = new NoopTelemetryTransport();
    await expect(t.send("app_launched", {}, "x")).resolves.toBeUndefined();
  });
});
