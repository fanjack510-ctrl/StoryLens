/**
 * Open an https commerce / external URL outside the app.
 * Browser local: new tab. Tauri webview: audited native command opens the system browser.
 * Never accepts javascript:/file:/data:/localhost or non-https targets.
 */

const USER_UNCONFIGURED = "专业版购买地址尚未配置。";
const USER_OPEN_FAILED = "未能打开购买页面，请稍后重试。";

export type OpenExternalResult = { ok: boolean; message?: string; code?: string };

/** Validate a StoryLens commerce / purchase URL. Rejects non-https and local targets. */
export function validateHttpsCommerceUrl(url: string): { ok: true; url: string } | { ok: false; code: string } {
  const trimmed = url.trim();
  if (!trimmed) {
    return { ok: false, code: "COMMERCE_URL_MISSING" };
  }

  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    return { ok: false, code: "COMMERCE_URL_INVALID" };
  }

  const protocol = parsed.protocol.toLowerCase();
  if (protocol !== "https:") {
    return { ok: false, code: "COMMERCE_URL_INVALID" };
  }

  // Defense: block dangerous schemes even if somehow embedded.
  const lower = trimmed.toLowerCase();
  if (
    lower.startsWith("javascript:") ||
    lower.startsWith("file:") ||
    lower.startsWith("data:") ||
    lower.startsWith("vbscript:")
  ) {
    return { ok: false, code: "COMMERCE_URL_INVALID" };
  }

  const host = parsed.hostname.toLowerCase();
  if (
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "::1" ||
    host === "[::1]" ||
    host.endsWith(".localhost")
  ) {
    return { ok: false, code: "COMMERCE_URL_INVALID" };
  }

  return { ok: true, url: parsed.toString() };
}

/** Open an https URL outside the app (new browser tab / OS handler). */
export async function openExternalUrl(url: string): Promise<OpenExternalResult> {
  const checked = validateHttpsCommerceUrl(url);
  if (!checked.ok) {
    return { ok: false, code: checked.code, message: USER_UNCONFIGURED };
  }

  try {
    if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("open_external_https_url", { url: checked.url });
      return { ok: true };
    }
    const opened = window.open(checked.url, "_blank", "noopener,noreferrer");
    if (opened == null) {
      return { ok: false, code: "COMMERCE_OPEN_FAILED", message: USER_OPEN_FAILED };
    }
    return { ok: true };
  } catch {
    return { ok: false, code: "COMMERCE_OPEN_FAILED", message: USER_OPEN_FAILED };
  }
}
