/** Backend UTC timestamp parsing (CHG-041 Round 4). */

/**
 * Parse API timestamps.
 * - Z / offset: normal
 * - naive legacy values: treat as UTC
 * - null / invalid: null
 */
export function parseBackendUtcTimestamp(value: string | null | undefined): number | null {
  if (value == null) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  let normalized = raw.includes("T") ? raw : raw.replace(" ", "T");
  const hasTz = /Z$/i.test(normalized) || /[+-]\d{2}:?\d{2}$/.test(normalized);
  if (!hasTz) {
    normalized = `${normalized}Z`;
  }
  const ms = Date.parse(normalized);
  if (!Number.isFinite(ms)) return null;
  return ms;
}
