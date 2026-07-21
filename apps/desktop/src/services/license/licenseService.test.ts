import { beforeEach, describe, expect, it } from "vitest";
import {
  createLicenseService,
  createMemoryLicenseStorage,
  FEATURE_KEYS,
  FEATURE_REGISTRY,
  hasFeature,
  LICENSE_STORAGE_TARGET_DESCRIPTION,
  MOCK_ACTIVATION_CODES,
  MOCK_LICENSE_SERVICE_MARKER,
  setLicenseServiceForTests,
} from "./index";
import { assertSafeLicensePayload } from "./storage";
import type { StoredLicensePayload } from "./types";

describe("license foundation", () => {
  beforeEach(() => {
    setLicenseServiceForTests(null);
  });

  it("defaults to FREE with no license payload", async () => {
    const service = createLicenseService({
      storage: createMemoryLicenseStorage(),
      allowMockInTests: true,
    });
    const snap = await service.hydrate();
    expect(snap.status).toBe("FREE");
    expect(snap.license).toBeNull();
    expect(snap.editionLabel).toBe("免费版");
    expect(snap.commerceComingSoon).toBe(true);
    expect(service.getLicenseStatus().status).toBe("FREE");
  });

  it("mock-activates VIP_ACTIVE and persists without novel body or API keys", async () => {
    const storage = createMemoryLicenseStorage();
    const service = createLicenseService({ storage, allowMockInTests: true });
    const snap = await service.activateLicense(MOCK_ACTIVATION_CODES.ACTIVE);
    expect(snap.status).toBe("VIP_ACTIVE");
    expect(snap.license?.license_id).toBe("mock-license-active");
    expect(snap.license?.plan).toBe("vip");
    expect(snap.license?.signature).toContain("NOT-REAL");
    expect(snap.usingMockService).toBe(true);

    const stored = await storage.read();
    expect(stored?.source).toBe("mock_dev");
    expect(stored?.status).toBe("VIP_ACTIVE");
    assertSafeLicensePayload(stored!);
    const raw = JSON.stringify(stored);
    expect(raw.toLowerCase()).not.toContain("api_key");
    expect(raw.toLowerCase()).not.toContain("novel_text");
    expect(raw.toLowerCase()).not.toContain("private_key");
    expect(MOCK_LICENSE_SERVICE_MARKER).toContain("DEV_MOCK");
  });

  it("mock-activates VIP_EXPIRED", async () => {
    const service = createLicenseService({
      storage: createMemoryLicenseStorage(),
      allowMockInTests: true,
    });
    const snap = await service.activateLicense(MOCK_ACTIVATION_CODES.EXPIRED);
    expect(snap.status).toBe("VIP_EXPIRED");
    expect(snap.license?.expires_at).toBeTruthy();
    expect(new Date(snap.license!.expires_at!).getTime()).toBeLessThan(Date.now());
  });

  it("mock-activates VIP_OFFLINE_GRACE and refresh restores VIP_ACTIVE", async () => {
    const service = createLicenseService({
      storage: createMemoryLicenseStorage(),
      allowMockInTests: true,
    });
    const grace = await service.activateLicense(MOCK_ACTIVATION_CODES.OFFLINE_GRACE);
    expect(grace.status).toBe("VIP_OFFLINE_GRACE");
    const refreshed = await service.refreshLicense();
    expect(refreshed.status).toBe("VIP_ACTIVE");
  });

  it("treats invalid signature as VIP_INVALID and blocks refresh", async () => {
    const service = createLicenseService({
      storage: createMemoryLicenseStorage(),
      allowMockInTests: true,
    });
    const snap = await service.activateLicense(MOCK_ACTIVATION_CODES.INVALID);
    expect(snap.status).toBe("VIP_INVALID");
    await expect(service.refreshLicense()).rejects.toMatchObject({
      code: "invalid_signature",
    });
  });

  it("deactivateLicense returns FREE and clears storage", async () => {
    const storage = createMemoryLicenseStorage();
    const service = createLicenseService({ storage, allowMockInTests: true });
    await service.activateLicense(MOCK_ACTIVATION_CODES.ACTIVE);
    const cleared = await service.deactivateLicense();
    expect(cleared.status).toBe("FREE");
    expect(cleared.license).toBeNull();
    expect(await storage.read()).toBeNull();
  });

  it("hasFeature uses registry and does not VIP-lock current product", () => {
    for (const key of FEATURE_KEYS) {
      const result = hasFeature(key);
      expect(result.status === "free" || result.status === "not_enabled").toBe(true);
      if (result.status === "not_enabled") {
        expect(result.allowed).toBe(false);
      }
      if (result.status === "free") {
        expect(result.allowed).toBe(true);
      }
    }
    expect(FEATURE_REGISTRY.batch_analysis.phaseAccess).toBe("not_enabled");
    // Existing analysis / reader journey are not gated by VIP in this stage.
    expect(hasFeature("scene_analysis").allowed).toBe(false);
    expect(hasFeature("scene_analysis").status).toBe("not_enabled");
  });

  it("rejects unsafe license payloads that look like API keys or novel body", () => {
    const tainted = {
      schema_version: 1,
      source: "mock_dev",
      status: "VIP_ACTIVE",
      license: {
        license_id: "x",
        plan: "vip",
        issued_at: new Date().toISOString(),
        expires_at: null,
        device_limit: 1,
        features: [],
        last_verified_at: null,
        signature: "sig",
        api_key: "sk-test",
      },
    } as unknown as StoredLicensePayload;
    expect(() => assertSafeLicensePayload(tainted)).toThrow();
  });

  it("documents reserved LOCALAPPDATA license path", () => {
    expect(LICENSE_STORAGE_TARGET_DESCRIPTION).toContain("%LOCALAPPDATA%/StoryLens/license");
    expect(LICENSE_STORAGE_TARGET_DESCRIPTION).toContain("storylens.license");
  });

  it("rejects unknown mock codes", async () => {
    const service = createLicenseService({
      storage: createMemoryLicenseStorage(),
      allowMockInTests: true,
    });
    await expect(service.activateLicense("NOT-A-REAL-CODE")).rejects.toMatchObject({
      code: "invalid_code",
    });
  });

  it("marks commerce as coming soon without locking existing features", async () => {
    const service = createLicenseService({
      storage: createMemoryLicenseStorage(),
      allowMockInTests: true,
    });
    const snap = await service.hydrate();
    expect(snap.commerceComingSoon).toBe(true);
    expect(snap.status).toBe("FREE");
    // Feature gate independent of FREE status for registered VIP keys.
    expect(service.hasFeature("batch_analysis").status).toBe("not_enabled");
  });
});
