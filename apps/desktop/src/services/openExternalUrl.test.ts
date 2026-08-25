import { afterEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { openExternalUrl, validateHttpsCommerceUrl } from "./openExternalUrl";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

describe("validateHttpsCommerceUrl", () => {
  it("accepts afdian https product URL", () => {
    const url = "https://afdian.com/item/5fa7eeba857211f1b8fc52540025c377";
    expect(validateHttpsCommerceUrl(url)).toEqual({ ok: true, url });
  });

  it("rejects empty, javascript, file, data, localhost, and http", () => {
    expect(validateHttpsCommerceUrl("").ok).toBe(false);
    expect(validateHttpsCommerceUrl("javascript:alert(1)").ok).toBe(false);
    expect(validateHttpsCommerceUrl("file:///C:/secret").ok).toBe(false);
    expect(validateHttpsCommerceUrl("data:text/html,hi").ok).toBe(false);
    expect(validateHttpsCommerceUrl("https://localhost/item").ok).toBe(false);
    expect(validateHttpsCommerceUrl("https://127.0.0.1/item").ok).toBe(false);
    expect(validateHttpsCommerceUrl("http://afdian.com/item/x").ok).toBe(false);
  });
});

describe("openExternalUrl", () => {
  afterEach(() => {
    Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
    vi.restoreAllMocks();
    vi.mocked(invoke).mockReset();
  });

  it("opens https URL in the system browser for Tauri", async () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", {
      configurable: true,
      value: {},
    });
    const url = "https://afdian.com/item/5fa7eeba857211f1b8fc52540025c377";
    const result = await openExternalUrl(url);
    expect(result.ok).toBe(true);
    expect(invoke).toHaveBeenCalledWith("open_external_https_url", { url });
  });

  it("distinguishes an opener failure from a missing URL", async () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", {
      configurable: true,
      value: {},
    });
    vi.mocked(invoke).mockRejectedValue(new Error("blocked"));
    const result = await openExternalUrl("https://afdian.com/item/x");
    expect(result).toEqual({
      ok: false,
      code: "COMMERCE_OPEN_FAILED",
      message: "未能打开购买页面，请稍后重试。",
    });
  });

  it("opens https URL in a new tab", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue({} as Window);
    const url = "https://afdian.com/item/5fa7eeba857211f1b8fc52540025c377";
    const result = await openExternalUrl(url);
    expect(result.ok).toBe(true);
    expect(open).toHaveBeenCalledWith(url, "_blank", "noopener,noreferrer");
  });

  it("returns user-facing unconfigured message without technical details", async () => {
    const result = await openExternalUrl("javascript:alert(1)");
    expect(result.ok).toBe(false);
    expect(result.message).toBe("专业版购买地址尚未配置。");
    expect(result.message).not.toMatch(/javascript|afdian_product_url|Error/i);
  });
});
