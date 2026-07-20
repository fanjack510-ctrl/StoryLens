export const TELEMETRY_EVENTS = [
  "app_launched",
  "analysis_started",
  "analysis_completed",
  "feature_used",
  "update_installed",
] as const;

export type TelemetryEventName = (typeof TELEMETRY_EVENTS)[number];

export const TELEMETRY_PROPERTY_KEYS = [
  "app_version",
  "os_family",
  "locale",
  "feature_key",
  "execution_mode",
  "status",
  "duration_bucket",
  "scene_count_bucket",
  "from_version",
  "to_version",
] as const;

export type TelemetryPropertyKey = (typeof TELEMETRY_PROPERTY_KEYS)[number];

/** Property keys that must never appear on outbound events. */
export const FORBIDDEN_PROPERTY_KEYS = [
  "book_title",
  "chapter_title",
  "paragraph_text",
  "novel_text",
  "file_path",
  "api_key",
  "prompt_text",
  "raw_error",
  "username",
  "machine_name",
  "user_name",
  "hostname",
] as const;

const EVENT_SET = new Set<string>(TELEMETRY_EVENTS);
const ALLOWED_PROP_SET = new Set<string>(TELEMETRY_PROPERTY_KEYS);
const FORBIDDEN_PROP_SET = new Set<string>(FORBIDDEN_PROPERTY_KEYS);

export type TelemetryScalar = string | number | boolean;

export type ValidatedTelemetryPayload = {
  event: TelemetryEventName;
  properties: Partial<Record<TelemetryPropertyKey, TelemetryScalar>>;
};

export type TelemetryValidationResult =
  | { ok: true; payload: ValidatedTelemetryPayload }
  | { ok: false; reason: string };

function isScalar(value: unknown): value is TelemetryScalar {
  const t = typeof value;
  return t === "string" || t === "number" || t === "boolean";
}

export function validateTelemetryPayload(
  event: string,
  properties: Record<string, unknown>,
): TelemetryValidationResult {
  if (!EVENT_SET.has(event)) {
    return { ok: false, reason: `unknown_event:${event}` };
  }

  const sanitized: Partial<Record<TelemetryPropertyKey, TelemetryScalar>> = {};

  for (const [key, value] of Object.entries(properties)) {
    if (FORBIDDEN_PROP_SET.has(key)) {
      return { ok: false, reason: `forbidden_property:${key}` };
    }
    if (!ALLOWED_PROP_SET.has(key)) {
      return { ok: false, reason: `unknown_property:${key}` };
    }
    if (!isScalar(value)) {
      return { ok: false, reason: `invalid_property_value:${key}` };
    }
    sanitized[key as TelemetryPropertyKey] = value;
  }

  return {
    ok: true,
    payload: {
      event: event as TelemetryEventName,
      properties: sanitized,
    },
  };
}
