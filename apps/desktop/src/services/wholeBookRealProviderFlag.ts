/**
 * Wave C — real provider gate for whole-book diagnostics (UI-only).
 * Default OFF; diagnostics page never exposes real-provider controls.
 */
export const WHOLE_BOOK_REAL_PROVIDER_ENABLED_ENV = "WHOLE_BOOK_REAL_PROVIDER_ENABLED";

function envFlagTruthy(raw: unknown): boolean {
  const value = String(raw ?? "")
    .trim()
    .toLowerCase();
  return value === "1" || value === "true" || value === "yes" || value === "on";
}

/** Whether real provider calls are allowed in diagnostics UI. Always default false. */
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
  if (typeof process !== "undefined" && process.env?.[WHOLE_BOOK_REAL_PROVIDER_ENABLED_ENV]) {
    return envFlagTruthy(process.env[WHOLE_BOOK_REAL_PROVIDER_ENABLED_ENV]);
  }
  return false;
}
