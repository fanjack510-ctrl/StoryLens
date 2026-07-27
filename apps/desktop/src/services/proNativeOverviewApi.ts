/**
 * Thin client for Pro Native Whole-Book Overview APIs (STEP 2.3-C).
 * Covers: preflight / create / get / retry / resume / overview.
 * Paths follow STEP 2.1 contract; backend may be mocked in Vitest.
 */
import { api, ApiError } from "./apiClient";
import {
  FIXTURE_ENGINE_ID,
  FIXTURE_ENGINE_LABEL,
  FIXTURE_ENGINE_VERSION,
  FIXTURE_PROMPT_VERSION,
  PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
  resolveEnginePresentation,
} from "./proNativeOverviewFlag";

export type OverviewFieldStatus =
  | "supported"
  | "low_confidence"
  | "insufficient_evidence"
  | "conflicted";

export type OverviewField = {
  value?: unknown;
  confidence?: number;
  evidence_refs?: string[];
  status?: OverviewFieldStatus;
};

export type PreflightBlockingError = {
  code?: string;
  message?: string;
};

export type ProNativeOverviewPreflight = {
  book_id: string | number;
  chapter_count: number;
  paragraph_count: number;
  character_count: number;
  snapshot_required?: boolean;
  provider_configured?: boolean;
  license_allowed?: boolean;
  mode?: string;
  estimated_windows?: number;
  estimated_tokens?: number;
  estimated_cost?: number;
  currency?: string;
  warnings?: string[];
  blocking_errors?: Array<PreflightBlockingError | string>;
  run_creation_enabled?: boolean;
  /** Optional engine identity extensions (walking skeleton / formal). */
  engine_id?: string;
  engine_version?: string;
  prompt_version?: string;
  /** Suggested create binding when backend supplies them. */
  provider_id?: string;
  model_id?: string;
  provider?: string;
  model?: string;
};

export type ProgressDTO = {
  completed_windows?: number;
  total_windows?: number;
  /** Backend may send percent; UI must not invent fake progress %. */
  percent?: number;
  current_window_index?: number | null;
  failed_window_index?: number | null;
};

export type CreateRunRequest = {
  mode?: string;
  module_key?: string;
  provider_id: string;
  model_id: string;
  client_request_id: string;
  consent: {
    estimated_tokens: number;
    estimated_cost: number;
    currency: string;
    confirmed: boolean;
  };
};

export type CreateRunResponse = {
  run_id: string;
  book_id: string | number;
  snapshot_id: string;
  mode?: string;
  module_key?: string;
  status: string;
  current_stage?: string | null;
  progress?: ProgressDTO;
  created_at?: string;
};

export type RunActionsDTO = {
  can_retry?: boolean;
  can_resume?: boolean;
};

export type RunStatusResponse = {
  run_id: string;
  book_id: string | number;
  snapshot_id: string;
  mode?: string;
  module_key?: string;
  status: string;
  current_stage?: string | null;
  progress?: ProgressDTO;
  estimated_tokens?: number | null;
  actual_tokens?: number | null;
  estimated_cost?: number | null;
  actual_cost?: number | null;
  currency?: string | null;
  provider?: string | null;
  model?: string | null;
  error?: string | null;
  error_code?: string | null;
  retryable?: boolean;
  actions?: RunActionsDTO;
  created_at?: string;
  started_at?: string | null;
  completed_at?: string | null;
  engine_id?: string;
  engine_version?: string;
  prompt_version?: string;
};

export type RetryRunRequest = {
  client_request_id: string;
  reason?: string | null;
};

export type ResumeRunRequest = {
  client_request_id: string;
};

export type RetryResumeRunResponse = {
  run_id: string;
  book_id: string | number;
  snapshot_id: string;
  status: string;
  current_stage?: string | null;
  progress?: ProgressDTO;
  retryable?: boolean;
  actions?: RunActionsDTO;
  message?: string;
};

export type EvidenceDeepLink = {
  book_id?: string | null;
  chapter_id: string;
  chapter_index?: number | null;
  paragraph_id: string;
  paragraph_index?: number | null;
  content_hash?: string | null;
  integrity_status?: string | null;
};

export type EvidenceIndexEntry = {
  evidence_id: string;
  chapter_id: string;
  paragraph_id: string;
  quote?: string;
  evidence_role?: string;
  confidence?: number;
  snapshot_id?: string | null;
  source_run_id?: string | null;
  deep_link: EvidenceDeepLink;
};

export type OverviewBody = {
  protagonist?: OverviewField | null;
  protagonist_core_goal?: OverviewField | null;
  primary_conflict?: OverviewField | null;
  central_question?: OverviewField | null;
  key_turning_points?: OverviewField | null;
  ending_state?: OverviewField | null;
  logline?: OverviewField | null;
  synopsis?: OverviewField | null;
  novel_type?: OverviewField | null;
  narrative_features?: OverviewField | null;
  core_setting?: OverviewField | null;
  climax?: OverviewField | null;
  resolved_problem?: OverviewField | null;
};

export type CoverageDTO = {
  original_paragraphs_total: number;
  original_paragraphs_covered: number;
  original_coverage_percent: number;
  windows_total: number;
  windows_completed: number;
  evidence_count?: number;
};

export type OverviewApiResponse = {
  run: {
    run_id: string;
    status: string;
    mode?: string;
    module_key?: string;
    current_stage?: string | null;
  };
  book: { book_id: string | number; title?: string };
  snapshot: { snapshot_id: string; status?: string };
  coverage: CoverageDTO;
  overview: OverviewBody;
  warnings?: string[];
  evidence_index?: EvidenceIndexEntry[];
  generated_at?: string;
  engine_version?: string;
  prompt_version?: string;
  contract_version?: string;
  engine_id?: string;
};

/** Normalize contract `{ error: { code, message, retryable } }` into ApiError. */
export function remapOverviewApiError(error: unknown): never {
  if (error instanceof ApiError) {
    const payload = error.detail as Record<string, unknown> | undefined;
    const nested =
      payload && typeof payload === "object" && payload.error && typeof payload.error === "object"
        ? (payload.error as Record<string, unknown>)
        : payload && typeof payload.code === "string"
          ? payload
          : null;
    if (nested && typeof nested.code === "string") {
      throw new ApiError(
        nested.code,
        typeof nested.message === "string" ? nested.message : error.message,
        error.status,
        typeof nested.details === "object" ? nested.details : nested,
        error.requestId,
        typeof nested.retryable === "boolean" ? nested.retryable : error.retryable,
        error.userActionHint,
        typeof nested.stage_key === "string" ? nested.stage_key : error.stage,
      );
    }
  }
  throw error;
}

async function call<T>(path: string, options?: RequestInit): Promise<T> {
  try {
    return await api<T>(path, options);
  } catch (error) {
    remapOverviewApiError(error);
  }
}

export const FIXTURE_CREATE_DEFAULTS = {
  mode: "whole_book_native",
  module_key: "book_overview",
  provider_id: "fixture",
  model_id: FIXTURE_ENGINE_ID,
  engine_label: FIXTURE_ENGINE_LABEL,
  engine_id: FIXTURE_ENGINE_ID,
  engine_version: FIXTURE_ENGINE_VERSION,
  prompt_version: FIXTURE_PROMPT_VERSION,
} as const;

/** Resolve create provider/model from preflight + fixture vs formal labeling. */
export function resolveCreateBinding(preflight?: ProNativeOverviewPreflight | null): {
  provider_id: string;
  model_id: string;
  engine: ReturnType<typeof resolveEnginePresentation>;
} {
  // Product default is Private; Fixture only when preflight/engine explicitly says so.
  const engineId =
    preflight?.engine_id ||
    preflight?.model_id ||
    preflight?.model ||
    PRIVATE_NATIVE_OVERVIEW_ENGINE_ID;
  const engine = resolveEnginePresentation(engineId, preflight?.model_id || preflight?.model);
  if (engine.isFixture) {
    return {
      provider_id: preflight?.provider_id || preflight?.provider || FIXTURE_CREATE_DEFAULTS.provider_id,
      model_id: FIXTURE_CREATE_DEFAULTS.model_id,
      engine,
    };
  }
  const providerCandidate =
    preflight?.provider_id || preflight?.provider || "";
  const modelCandidate = preflight?.model_id || preflight?.model || "";
  // Never send Engine identity as AI provider/model on create.
  const providerLooksLikeEngine =
    !providerCandidate ||
    providerCandidate === PRIVATE_NATIVE_OVERVIEW_ENGINE_ID ||
    providerCandidate === FIXTURE_ENGINE_ID ||
    providerCandidate.startsWith("private-") ||
    providerCandidate.startsWith("fixture");
  const modelLooksLikeEngine =
    !modelCandidate ||
    modelCandidate === PRIVATE_NATIVE_OVERVIEW_ENGINE_ID ||
    modelCandidate === FIXTURE_ENGINE_ID ||
    modelCandidate.startsWith("private-") ||
    modelCandidate.startsWith("fixture") ||
    modelCandidate === engine.engineId;

  return {
    provider_id: providerLooksLikeEngine ? "aliyun_qwen_plus" : providerCandidate,
    model_id: modelLooksLikeEngine ? "qwen3.7-plus" : modelCandidate,
    engine,
  };
}

export function newClientRequestId(prefix = "overview"): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${prefix}-${Date.now()}`;
}

export const proNativeOverviewApi = {
  preflight: (bookId: number, body?: Record<string, unknown>) =>
    call<ProNativeOverviewPreflight>(`/api/v1/books/${bookId}/whole-book-runs/preflight`, {
      method: "POST",
      body: JSON.stringify({
        mode: FIXTURE_CREATE_DEFAULTS.mode,
        module_key: FIXTURE_CREATE_DEFAULTS.module_key,
        ...(body || {}),
      }),
    }),

  createRun: (bookId: number, request: CreateRunRequest) =>
    call<CreateRunResponse>(`/api/v1/books/${bookId}/whole-book-runs`, {
      method: "POST",
      body: JSON.stringify({
        mode: request.mode ?? FIXTURE_CREATE_DEFAULTS.mode,
        module_key: request.module_key ?? FIXTURE_CREATE_DEFAULTS.module_key,
        provider_id: request.provider_id,
        model_id: request.model_id,
        client_request_id: request.client_request_id,
        consent: request.consent,
      }),
    }),

  getRun: (runId: string) => call<RunStatusResponse>(`/api/v1/whole-book-runs/${runId}`),

  retryRun: (runId: string, request: RetryRunRequest) =>
    call<RetryResumeRunResponse>(`/api/v1/whole-book-runs/${runId}/retry`, {
      method: "POST",
      body: JSON.stringify({
        client_request_id: request.client_request_id,
        ...(request.reason != null ? { reason: request.reason } : {}),
      }),
    }),

  resumeRun: (runId: string, request: ResumeRunRequest) =>
    call<RetryResumeRunResponse>(`/api/v1/whole-book-runs/${runId}/resume`, {
      method: "POST",
      body: JSON.stringify({
        client_request_id: request.client_request_id,
      }),
    }),

  getOverview: (runId: string) =>
    call<OverviewApiResponse>(`/api/v1/whole-book-runs/${runId}/overview`),
};
