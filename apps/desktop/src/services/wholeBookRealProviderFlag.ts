/**
 * Formal Free whole-book real-provider UI gate (V1.2.0).
 * Production default ON (aligned with sidecar STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED).
 * Explicit env false/0/off still disables. Diagnostics harness stays separate.
 */
export const WHOLE_BOOK_REAL_PROVIDER_ENABLED_ENV = "STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED";

declare const __STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED__: boolean | undefined;

function envFlagTruthy(raw: unknown): boolean {
  const value = String(raw ?? "")
    .trim()
    .toLowerCase();
  return value === "1" || value === "true" || value === "yes" || value === "on";
}

function envFlagExplicitFalse(raw: unknown): boolean {
  const value = String(raw ?? "")
    .trim()
    .toLowerCase();
  return value === "0" || value === "false" || value === "no" || value === "off";
}

/** Whether formal Free whole-book may start real Provider analysis. */
export function isWholeBookRealProviderEnabled(): boolean {
  const fromVite =
    typeof import.meta !== "undefined"
      ? (import.meta as ImportMeta & { env?: Record<string, string> }).env?.[
          "VITE_WHOLE_BOOK_REAL_PROVIDER_ENABLED"
        ]
      : undefined;
  if (fromVite !== undefined && String(fromVite).trim() !== "") {
    return envFlagTruthy(fromVite);
  }
  if (typeof __STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED__ !== "undefined") {
    return __STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED__ === true;
  }
  if (typeof process !== "undefined" && process.env?.[WHOLE_BOOK_REAL_PROVIDER_ENABLED_ENV]) {
    const raw = process.env[WHOLE_BOOK_REAL_PROVIDER_ENABLED_ENV];
    if (envFlagExplicitFalse(raw)) return false;
    return envFlagTruthy(raw);
  }
  // V1.2.0 Free contract: formal real Provider path ON when no explicit override.
  return true;
}
