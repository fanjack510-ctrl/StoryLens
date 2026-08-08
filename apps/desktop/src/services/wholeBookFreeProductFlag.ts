/**
 * Formal Free whole-book product UI gate (V1.2.0).
 * Production default ON. Does not enable diagnostics, fixture preview, or Pro.
 * Explicit env false/0/off still disables.
 */
export const WHOLE_BOOK_FREE_PRODUCT_ENABLED_ENV = "STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED";

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

/** Desktop formal whole-book product entry + page gate. */
export function isWholeBookFreeProductEnabled(): boolean {
  const fromVite =
    typeof import.meta !== "undefined"
      ? (import.meta as ImportMeta & { env?: Record<string, string> }).env?.[
          "VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED"
        ]
      : undefined;
  if (fromVite !== undefined && String(fromVite).trim() !== "") {
    return envFlagTruthy(fromVite);
  }
  if (typeof __STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED__ !== "undefined") {
    return __STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED__ === true;
  }
  if (typeof process !== "undefined" && process.env?.[WHOLE_BOOK_FREE_PRODUCT_ENABLED_ENV]) {
    const raw = process.env[WHOLE_BOOK_FREE_PRODUCT_ENABLED_ENV];
    if (envFlagExplicitFalse(raw)) return false;
    return envFlagTruthy(raw);
  }
  // V1.2.0 Free contract: formal entry enabled when no explicit override.
  return true;
}
