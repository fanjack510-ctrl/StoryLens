/** Mock Lab authorization mirror (Phase 2A-P). Default closed. */

export const WHOLE_BOOK_MOCK_LAB_ENABLED = false as const;

export const MOCK_LAB_REQUEST_MARKER_HEADER = "X-StoryLens-Mock-Lab" as const;
export const MOCK_LAB_REQUEST_MARKER_VALUE = "1" as const;
export const MOCK_ENGINE_ID = "mock_whole_book_v0" as const;

export const ALLOWED_MOCK_LAB_ENVIRONMENTS = ["development", "test"] as const;
export type AllowedMockLabEnvironment = (typeof ALLOWED_MOCK_LAB_ENVIRONMENTS)[number];

export const MOCK_LAB_DENY_REASONS = [
  "MOCK_LAB_DISABLED",
  "MOCK_LAB_ENVIRONMENT_NOT_ALLOWED",
  "MOCK_LAB_LOOPBACK_REQUIRED",
  "MOCK_LAB_ENGINE_REQUIRED",
  "MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE",
  "MOCK_LAB_REQUEST_MARKER_REQUIRED",
] as const;

export type MockLabDenyReason = (typeof MOCK_LAB_DENY_REASONS)[number];

export type MockLabAuthorizationDecision = {
  allowed: boolean;
  reason_code: MockLabDenyReason | null;
  environment: string;
  loopback: boolean;
  lab_enabled: boolean;
  requested_engine_id: string | null;
  engine_is_mock: boolean;
  non_production: boolean;
  evaluated_at: string;
  request_marker_present: boolean;
  capability_context_is_lab: boolean;
};

export type MockLabAuthorizationInput = {
  environment: string;
  loopback: boolean;
  lab_enabled: boolean;
  request_marker_present: boolean;
  requested_engine_id: string | null;
  engine_is_mock: boolean;
  engine_non_production: boolean;
  capability_context_is_lab?: boolean;
};

export function evaluateMockLabAuthorization(
  input: MockLabAuthorizationInput,
  evaluatedAt: string,
): MockLabAuthorizationDecision {
  const base = {
    environment: input.environment,
    loopback: input.loopback,
    lab_enabled: input.lab_enabled,
    requested_engine_id: input.requested_engine_id,
    engine_is_mock: input.engine_is_mock,
    non_production: input.engine_non_production,
    evaluated_at: evaluatedAt,
    request_marker_present: input.request_marker_present,
    capability_context_is_lab: input.capability_context_is_lab ?? true,
  };

  if (!input.lab_enabled) {
    return { allowed: false, reason_code: "MOCK_LAB_DISABLED", ...base };
  }
  if (!(ALLOWED_MOCK_LAB_ENVIRONMENTS as readonly string[]).includes(input.environment)) {
    return { allowed: false, reason_code: "MOCK_LAB_ENVIRONMENT_NOT_ALLOWED", ...base };
  }
  if (!input.loopback) {
    return { allowed: false, reason_code: "MOCK_LAB_LOOPBACK_REQUIRED", ...base };
  }
  if (!input.request_marker_present) {
    return { allowed: false, reason_code: "MOCK_LAB_REQUEST_MARKER_REQUIRED", ...base };
  }
  if (!input.engine_is_mock || input.requested_engine_id !== MOCK_ENGINE_ID) {
    return { allowed: false, reason_code: "MOCK_LAB_ENGINE_REQUIRED", ...base };
  }
  if (!input.engine_non_production) {
    return { allowed: false, reason_code: "MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE", ...base };
  }
  return { allowed: true, reason_code: null, ...base };
}
