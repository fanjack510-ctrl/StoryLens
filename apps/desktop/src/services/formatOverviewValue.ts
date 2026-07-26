/**
 * Format Native Overview field values for product UI (not raw JSON).
 * CHG-20260727-015 / STEP 2.8-FIX-NATIVE-RESULT-PRESENTATION-01
 */

export type FormattedOverviewValue =
  | { kind: "empty" }
  | { kind: "text"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "unsupported" };

const LONG_ITEM_CHARS = 40;

function asDisplayString(item: unknown): string {
  if (item == null) return "";
  if (typeof item === "string" || typeof item === "number" || typeof item === "boolean") {
    return String(item).trim();
  }
  if (typeof item === "object" && !Array.isArray(item)) {
    const record = item as Record<string, unknown>;
    for (const key of ["summary", "text", "name", "title", "description"] as const) {
      const candidate = record[key];
      if (typeof candidate === "string" && candidate.trim()) {
        return candidate.trim();
      }
    }
  }
  return "";
}

/** Normalize overview field values for result cards. */
export function formatOverviewValue(value: unknown): FormattedOverviewValue {
  if (value == null) return { kind: "empty" };
  if (typeof value === "string") {
    const text = value.trim();
    return text ? { kind: "text", text } : { kind: "empty" };
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return { kind: "text", text: String(value) };
  }
  if (Array.isArray(value)) {
    const items = value.map(asDisplayString).filter(Boolean);
    if (items.length === 0) return { kind: "empty" };
    if (items.length === 1) return { kind: "text", text: items[0]! };
    const hasLong = items.some((item) => item.length > LONG_ITEM_CHARS);
    if (hasLong) return { kind: "list", items };
    return { kind: "text", text: items.join("、") };
  }
  if (typeof value === "object") {
    const text = asDisplayString(value);
    if (text) return { kind: "text", text };
    return { kind: "unsupported" };
  }
  return { kind: "unsupported" };
}
