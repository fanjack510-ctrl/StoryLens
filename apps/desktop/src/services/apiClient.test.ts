/**
 * Unit tests for the single Sidecar API base source of truth.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("apiClient api base readiness", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("exposes get/set/onApiBaseChange and notifies listeners", async () => {
    const mod = await import("./apiClient");
    const seen: string[] = [];
    const unsub = mod.onApiBaseChange((base) => seen.push(base));
    const next = "http://127.0.0.1:19999";
    mod.setApiBase(next);
    expect(mod.getApiBase()).toBe(next);
    expect(seen).toEqual([next]);
    mod.setApiBase(next); // no-op
    expect(seen).toHaveLength(1);
    unsub();
    mod.setApiBase("http://127.0.0.1:19998");
    expect(seen).toHaveLength(1);
  });

  it("isApiBaseReady is true for browser DEV default", async () => {
    const mod = await import("./apiClient");
    // Vite DEV defaults to http://127.0.0.1:8000 when not Tauri.
    expect(mod.isApiBaseReady()).toBe(true);
    expect(mod.getApiBase()).toMatch(/^https?:\/\//);
  });

  it("waitForApiReady resolves immediately in browser", async () => {
    const mod = await import("./apiClient");
    const base = await mod.waitForApiReady(1000);
    expect(base).toBe(mod.getApiBase());
  });
});
