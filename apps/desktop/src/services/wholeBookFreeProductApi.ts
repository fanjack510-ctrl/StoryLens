/**
 * Wave D — formal Free whole-book product HTTP client.
 * Wraps prepare/create/progress/capabilities; re-exports foundation reads.
 */
import { api } from "./apiClient";
import {
  wholeBookFoundationApi,
  newFoundationClientRequestId,
  type BookOverviewResultRow,
  type EvidenceSourceDetail,
  type NarrativeAssetRow,
  type NarrativeEntityRow,
  type NarrativeEvidenceRow,
  type WholeBookRunRecord,
  type WholeBookRunStageRow,
} from "./wholeBookFoundationApi";

export { wholeBookFoundationApi, newFoundationClientRequestId };

export type ProductCapabilityRow = {
  capability_id: string;
  display_name: string;
  required_tier: "free" | "pro";
  release_status: "available" | "planned";
  access_status: "granted" | "locked" | "planned";
  reason_code: string | null;
};

export type WholeBookCostEstimateRow = {
  estimate_id: number;
  book_id: number;
  mode: string;
  estimated_windows: number | null;
  estimated_provider_calls: number | null;
  estimated_input_tokens: number | null;
  estimated_output_tokens: number | null;
  estimated_cost_min_cny: string | null;
  estimated_cost_max_cny: string | null;
  provider_name: string | null;
  model_name: string | null;
  price_known: boolean;
  currency: string;
};

export type WholeBookPrepareResponse = {
  book_id: number;
  book_title: string;
  chapter_count: number;
  character_count: number;
  mode: string;
  mode_label: string;
  product_enabled: boolean;
  real_provider_enabled: boolean;
  run_creation_enabled: boolean;
  fixture_preview_enabled: boolean;
  latest_run: WholeBookRunRecord | null;
  recoverable_run: WholeBookRunRecord | null;
  snapshot_rebuild_required: boolean;
  estimate: WholeBookCostEstimateRow | null;
  recommended_limits: {
    max_provider_calls: number | null;
    max_input_tokens: number | null;
    max_output_tokens: number | null;
    max_cost_budget_cny: string | null;
  };
  blocking_reasons: string[];
  warnings: string[];
};

export type CreateWholeBookRunRequest = {
  client_request_id: string;
  estimate_id?: number | null;
  consent_id?: number | null;
  max_provider_calls?: number | null;
  max_input_tokens?: number | null;
  max_output_tokens?: number | null;
  max_cost_budget_cny?: string | null;
  auto_retry_enabled?: boolean;
};

export type CreateWholeBookRunResponse = {
  run: WholeBookRunRecord;
};

export type WholeBookProgressResponse = {
  run_id: number;
  status: string;
  overall_progress: number | null;
  current_stage: string | null;
  completed_windows: number;
  total_windows: number;
  completed_provider_units: number;
  total_provider_units: number;
  provider_calls_used: number;
  provider_calls_limit: number | null;
  input_tokens_used: number;
  output_tokens_used: number;
  cost_used_cny: string | null;
  pause_requested: boolean;
  cancel_requested: boolean;
  can_pause: boolean;
  can_resume: boolean;
  can_cancel: boolean;
  started_at: string | null;
  updated_at: string | null;
  result_origin: string | null;
};

export type WholeBookModuleKey =
  | "overview"
  | "characters_events"
  | "structure"
  | "chapter_functions"
  | "pro_depth";

export const WHOLE_BOOK_FREE_MODULES: Array<{
  key: WholeBookModuleKey;
  label: string;
  status: "available" | "planned" | "pro_planned";
}> = [
  { key: "overview", label: "全书总览", status: "available" },
  { key: "characters_events", label: "主要人物与关键事件", status: "available" },
  { key: "structure", label: "故事结构", status: "planned" },
  { key: "chapter_functions", label: "章节功能", status: "planned" },
  { key: "pro_depth", label: "Pro 深度分析", status: "pro_planned" },
];

export function newWholeBookClientRequestId(prefix = "wb-free"): string {
  return newFoundationClientRequestId(prefix);
}

export const wholeBookFreeProductApi = {
  productCapabilities: () =>
    api<{ capabilities: ProductCapabilityRow[] }>("/api/v1/whole-book/product-capabilities"),

  /** Product prepare — aliases `/whole-book/free/prepare`. */
  prepare: (bookId: number) =>
    api<WholeBookPrepareResponse>(`/api/v1/books/${bookId}/whole-book/prepare`),

  createRun: (bookId: number, body: CreateWholeBookRunRequest) =>
    api<CreateWholeBookRunResponse>(`/api/v1/books/${bookId}/whole-book/free/create`, {
      method: "POST",
      body: JSON.stringify({
        estimate_id: body.estimate_id,
        consent_id: body.consent_id,
        client_request_id: body.client_request_id,
      }),
    }),

  /** Fixture preview — aliases `/whole-book/free/create-fixture`. */
  createFixtureRun: (bookId: number, body: { client_request_id: string }) =>
    api<CreateWholeBookRunResponse>(`/api/v1/books/${bookId}/whole-book/runs/fixture`, {
      method: "POST",
      body: JSON.stringify({
        client_request_id: body.client_request_id,
        execute_pipeline: true,
      }),
    }),

  getProgress: (runId: number) =>
    api<WholeBookProgressResponse>(`/api/v1/whole-book/runs/${runId}/progress`),

  pauseRun: (runId: number) =>
    api<{ run: WholeBookRunRecord }>(`/api/v1/whole-book/runs/${runId}/pause`, {
      method: "POST",
    }),

  resumeRun: (runId: number) =>
    api<{ run: WholeBookRunRecord }>(`/api/v1/whole-book/runs/${runId}/resume`, {
      method: "POST",
    }),

  cancelRun: (runId: number) =>
    api<{ run: WholeBookRunRecord }>(`/api/v1/whole-book/runs/${runId}/cancel`, {
      method: "POST",
    }),

  createCostEstimate: (bookId: number, body: { mode: string; provider_config_id: number }) =>
    api<WholeBookCostEstimateRow>(`/api/v1/books/${bookId}/whole-book/cost-estimates`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // Foundation reads (Wave C)
  getOverview: (runId: number) => wholeBookFoundationApi.getOverview(runId),
  listEntities: (runId: number) => wholeBookFoundationApi.listEntities(runId),
  listAssets: (runId: number, params?: { asset_type?: string }) =>
    wholeBookFoundationApi.listAssets(runId, params),
  listEvidences: (runId: number) => wholeBookFoundationApi.listEvidences(runId),
  getEvidenceSource: (evidenceId: number) => wholeBookFoundationApi.getEvidenceSource(evidenceId),
  listStages: (runId: number) => wholeBookFoundationApi.listStages(runId),
  getRun: (runId: number) => wholeBookFoundationApi.getRun(runId),
};

export type {
  BookOverviewResultRow,
  EvidenceSourceDetail,
  NarrativeAssetRow,
  NarrativeEntityRow,
  NarrativeEvidenceRow,
  WholeBookRunRecord,
  WholeBookRunStageRow,
};
