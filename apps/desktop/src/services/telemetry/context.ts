import { BUILD_APP_VERSION } from "../../lib/appVersion";

export type TelemetryContext = {
  app_version: string;
  os_family: string;
  locale: string;
};

export function detectOsFamily(userAgent = typeof navigator !== "undefined" ? navigator.userAgent : ""): string {
  if (/Windows/i.test(userAgent)) return "windows";
  if (/Mac OS X|Macintosh/i.test(userAgent)) return "macos";
  if (/Linux/i.test(userAgent)) return "linux";
  return "unknown";
}

export function getDefaultTelemetryContext(): TelemetryContext {
  const locale =
    typeof navigator !== "undefined" && navigator.language ? navigator.language : "unknown";
  return {
    app_version: BUILD_APP_VERSION.trim() || "unknown",
    os_family: detectOsFamily(),
    locale,
  };
}
