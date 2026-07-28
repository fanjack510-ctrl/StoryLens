/**
 * Wave D — fixture preview button gate for formal whole-book product page.
 * Default OFF; never labels fixture flow as formal analysis.
 */
export const WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED_ENV =
  "STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED";

function envFlagTruthy(raw: unknown): boolean {
  const value = String(raw ?? "")
    .trim()
    .toLowerCase();
  return value === "1" || value === "true" || value === "yes" || value === "on";
}

/** Whether the formal page may offer fixture preview transport. */
export function isWholeBookFixturePreviewEnabled(): boolean {
  const fromVite =
    typeof import.meta !== "undefined"
      ? (import.meta as ImportMeta & { env?: Record<string, string> }).env?.[
          "VITE_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED"
        ]
      : undefined;
  if (fromVite !== undefined && String(fromVite).trim() !== "") {
    return envFlagTruthy(fromVite);
  }
  if (
    typeof __STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED__ !== "undefined" &&
    __STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED__ === true
  ) {
    return true;
  }
  if (typeof process !== "undefined" && process.env?.[WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED_ENV]) {
    return envFlagTruthy(process.env[WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED_ENV]);
  }
  return false;
}
