/**
 * Wave B — Whole-book foundation diagnostics page gate (UI-only).
 * Backend foundation APIs are independent; default remains off in production builds.
 */
export const WHOLE_BOOK_DIAGNOSTICS_ENABLED_ENV = "WHOLE_BOOK_DIAGNOSTICS_ENABLED";

function envFlagTruthy(raw: unknown): boolean {
  const value = String(raw ?? "")
    .trim()
    .toLowerCase();
  return value === "1" || value === "true" || value === "yes" || value === "on";
}

/**
 * Desktop diagnostics page gate.
 * Priority: Vite import.meta env → build-time define → process env.
 */
export function isWholeBookDiagnosticsEnabled(): boolean {
  const fromVite =
    typeof import.meta !== "undefined"
      ? (import.meta as ImportMeta & { env?: Record<string, string> }).env?.[
          "VITE_WHOLE_BOOK_DIAGNOSTICS_ENABLED"
        ]
      : undefined;
  if (fromVite !== undefined && String(fromVite).trim() !== "") {
    return envFlagTruthy(fromVite);
  }
  if (
    typeof __STORYLENS_WHOLE_BOOK_DIAGNOSTICS_ENABLED__ !== "undefined" &&
    __STORYLENS_WHOLE_BOOK_DIAGNOSTICS_ENABLED__ === true
  ) {
    return true;
  }
  if (typeof process !== "undefined" && process.env?.[WHOLE_BOOK_DIAGNOSTICS_ENABLED_ENV]) {
    return envFlagTruthy(process.env[WHOLE_BOOK_DIAGNOSTICS_ENABLED_ENV]);
  }
  return false;
}
