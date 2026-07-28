/**
 * Wave D — formal Free whole-book product UI gate.
 * Default OFF; does not expose diagnostics or real provider.
 */
export const WHOLE_BOOK_FREE_PRODUCT_ENABLED_ENV = "STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED";

function envFlagTruthy(raw: unknown): boolean {
  const value = String(raw ?? "")
    .trim()
    .toLowerCase();
  return value === "1" || value === "true" || value === "yes" || value === "on";
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
  if (
    typeof __STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED__ !== "undefined" &&
    __STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED__ === true
  ) {
    return true;
  }
  if (typeof process !== "undefined" && process.env?.[WHOLE_BOOK_FREE_PRODUCT_ENABLED_ENV]) {
    return envFlagTruthy(process.env[WHOLE_BOOK_FREE_PRODUCT_ENABLED_ENV]);
  }
  return false;
}
