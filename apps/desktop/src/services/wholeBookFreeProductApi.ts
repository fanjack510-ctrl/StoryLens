/**
 * Wave D — formal Free whole-book product HTTP client.
 * Wraps prepare/create/progress/capabilities; re-exports foundation reads.
 */
import { api, ApiError } from "./apiClient";
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
import {
  assertStructureStagesResultV2,
  UnsupportedStructureContractError,
  type StructureProductResponse,
} from "./structureStagesResultV2";
import {
  assertChapterFunctionsResultV2,
  clampChapterFunctionsLimit,
  CHAPTER_FUNCTIONS_DEFAULT_LIMIT,
  UnsupportedChapterFunctionsContractError,
  type ChapterFunctionsProductResponse,
  type ChapterFunctionItemV2,
} from "./chapterFunctionsResultV2";

export { wholeBookFoundationApi, newFoundationClientRequestId };
export type { StructureProductResponse } from "./structureStagesResultV2";
export type {
  ChapterFunctionsProductResponse,
  ChapterFunctionItemV2,
  ChapterFunctionsResultV2,
  ChapterFunctionsClientViewState,
} from "./chapterFunctionsResultV2";

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
  call_breakdown?: {
    extraction_calls?: number;
    window_extraction_calls?: number;
    consolidation_calls?: number;
    final_synthesis_calls?: number;
    chapter_function_batch_calls?: number;
    repair_reserve_calls?: number;
    estimated_total_calls?: number;
  } | null;
  provider_name: string | null;
  model_name: string | null;
  price_known: boolean;
  currency: string;
  estimate_version?: string | null;
  planner?: string | null;
};

export type WholeBookPrepareResponse = {
  book_id: number;
  book_title: string;
  /** Which engine this book gets. Sent at the top level as well as inside `estimate`, and
   *  read from here to decide whether 拆文 can be offered — it exists only in the long-novel
   *  engine. The field was being read without being declared, so the check compiled to
   *  `undefined === "long_novel_engine"` in the type-checker's view while working at runtime. */
  planner?: string | null;
  chapter_count: number;
  character_count: number;
  mode: string;
  mode_label: string;
  product_enabled: boolean;
  real_provider_enabled: boolean;
  run_creation_enabled: boolean;
  active_provider_name?: string;
  active_model_name?: string;
  provider_available?: boolean;
  fixture_preview_enabled: boolean;
  latest_run: WholeBookRunRecord | null;
  recoverable_run: WholeBookRunRecord | null;
  /** 后端按心跳判定的「真正在跑的那个」。null = 没有在跑的任务；
   *  undefined = 后端还是旧版本，客户端退回自己按状态挑。 */
  live_run_id?: number | null;
  /** Last completed run that has or had V2 materialized. */
  completed_v2_run?: WholeBookRunRecord | null;
  /** Newest real completed run of each reading. A book can hold both a 评测 and a 拆文;
   *  without this the page can only ever reach the newer one. Absent on an older sidecar. */
  completed_v2_runs_by_reading?: Partial<Record<WholeBookAnalysisMode, WholeBookRunRecord>>;
  /** Pending, running, or recoverable run (may overlap with latest_run). */
  active_run?: WholeBookRunRecord | null;
  /** Latest failed WholeBookRun (CHG-084 — do not auto-show scaffold as completed). */
  latest_failed_run?: WholeBookRunRecord | null;
  /** Completed but non-real / scaffold result for optional old-result viewing. */
  non_real_completed_v2_run?: WholeBookRunRecord | null;
  /** CHG-085: failed run with reusable real_provider window checkpoints. */
  resumable_checkpoint?: {
    can_resume?: boolean;
    compatible?: boolean;
    run_id?: number;
    completed_windows?: number;
    total_windows?: number;
    provider_calls_completed?: number;
    provider_calls_estimated?: number;
    next_stage?: string;
    message?: string;
    reason?: string;
  } | null;
  context_safe?: boolean;
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
  /** When true, discard cached AI intermediates and re-run extraction. */
  force_full_reanalysis?: boolean;
  /** True when user confirms a reanalysis from an existing completed V2 run. */
  reanalyse?: boolean;
  /** Completed run id to preserve/display while the new run is in flight. */
  previous_run_id?: number | null;
  /** Which reading of the book to run. Omitted means the diagnostic, which is what every
   *  caller written before 拆文 existed intends. */
  analysis_mode?: WholeBookAnalysisMode;
};

/** 评测 finds what to fix in your own book; 拆文 reads someone else's for how it is done.
 *  They are different products over the same extraction, not two lengths of one report. */
/** 三种读法。`comprehend`（读懂）给的不是小说：专著、教材、工具书。
 *  它的产出形状跟前两种完全不同（主张 / 依据 / 做法 / 术语 / 存疑），所以走自己的读取口。 */
export type WholeBookAnalysisMode = "diagnostic" | "story_breakdown" | "comprehend";

/** 「读懂」的结果。字段与 WholeBookAnalysisV2 没有交集——它回答的是别的问题。 */
export type ComprehendSection = {
  label: string;
  claims: string[];
  evidence: string[];
  actions: string[];
  terms: string[];
  open_questions: string[];
  error?: string;
};
export type ComprehendChapter = {
  chapter: string;
  title: string;
  summary: string;
  through_line: string;
  error?: string;
  sections: ComprehendSection[];
};
export type ComprehendResult = {
  schema_version: string;
  book: {
    one_paragraph: string;
    argument: string;
    what_you_get: string;
    who_should_read: string;
    error?: string;
  };
  chapters: ComprehendChapter[];
  sections_total: number;
  sections_covered: number;
  coverage: number;
  /** 覆盖率低于九成就是 false。读者据此决定要不要回去读原文。 */
  trustworthy: boolean;
  provider_calls: number;
  failures: string[];
  rules: string[];
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
  { key: "structure", label: "故事结构", status: "available" },
  { key: "chapter_functions", label: "章节功能", status: "available" },
  { key: "pro_depth", label: "Pro 深度分析", status: "pro_planned" },
];

export type ChapterFunctionsQueryParams = {
  limit?: number;
  cursor?: string | null;
  function?: string | null;
  status?: string | null;
  offset?: number | null;
};

function mapChapterFunctionsApiError(err: unknown): never {
  if (err instanceof ApiError) {
    const detailCode =
      err.detail && typeof err.detail === "object"
        ? String((err.detail as { error_code?: string }).error_code || "")
        : "";
    if (err.status === 404) {
      if (
        detailCode === "CHAPTER_FUNCTION_CHAPTER_NOT_FOUND" ||
        detailCode === "CHAPTER_FUNCTIONS_CHAPTER_NOT_FOUND"
      ) {
        throw err;
      }
      if (!detailCode || detailCode === "CHAPTER_FUNCTIONS_RESULT_ABSENT") {
        throw new ApiError(
          "CHAPTER_FUNCTIONS_RESULT_ABSENT",
          err.message || "章节功能结果尚未生成",
          404,
          { error_code: "CHAPTER_FUNCTIONS_RESULT_ABSENT" },
        );
      }
    }
    if (
      detailCode === "CHAPTER_FUNCTIONS_INVALID_CURSOR" ||
      detailCode === "CHAPTER_FN_INVALID_CURSOR" ||
      err.code === "CHAPTER_FUNCTIONS_INVALID_CURSOR" ||
      err.code === "CHAPTER_FN_INVALID_CURSOR"
    ) {
      throw new ApiError(
        "CHAPTER_FUNCTIONS_INVALID_CURSOR",
        err.message || "分页游标无效，请清除筛选后重试",
        err.status || 400,
        { error_code: "CHAPTER_FUNCTIONS_INVALID_CURSOR", ...(typeof err.detail === "object" ? err.detail : {}) },
      );
    }
  }
  throw err;
}

function assertChapterFunctionsEnvelope(
  resp: ChapterFunctionsProductResponse,
): ChapterFunctionsProductResponse {
  if (resp.chapter_functions != null) {
    try {
      resp.chapter_functions = assertChapterFunctionsResultV2(resp.chapter_functions);
    } catch (err) {
      if (err instanceof UnsupportedChapterFunctionsContractError) {
        throw new ApiError(
          "CHAPTER_FUNCTIONS_CONTRACT_UNSUPPORTED",
          err.message,
          422,
          {
            error_code: "CHAPTER_FUNCTIONS_CONTRACT_UNSUPPORTED",
            contract_version: err.contractVersion,
          },
        );
      }
      throw err;
    }
  }
  if (
    resp.failure_code === "CHAPTER_FN_UNSUPPORTED_VERSION" ||
    resp.failure_code === "CHAPTER_FUNCTIONS_CONTRACT_UNSUPPORTED"
  ) {
    throw new ApiError(
      "CHAPTER_FUNCTIONS_CONTRACT_UNSUPPORTED",
      resp.failure_message_safe || "章节功能合同版本不受支持",
      422,
      {
        error_code: "CHAPTER_FUNCTIONS_CONTRACT_UNSUPPORTED",
        contract_version: resp.contract_version,
        failure_code: resp.failure_code,
      },
    );
  }
  if (!Array.isArray(resp.items)) {
    resp.items = [] as ChapterFunctionItemV2[];
  }
  return resp;
}

export function newWholeBookClientRequestId(prefix = "wb-free"): string {
  return newFoundationClientRequestId(prefix);
}

export const wholeBookFreeProductApi = {
  productCapabilities: () =>
    api<{ capabilities: ProductCapabilityRow[] }>("/api/v1/whole-book/product-capabilities"),

  /** Product prepare — aliases `/whole-book/free/prepare`.
   *
   *  The mode is a query parameter because the panel quotes calls and money, and the two modes
   *  do not cost the same: 拆文 runs four bounded units where the diagnostic runs eight. */
  prepare: (bookId: number, analysisMode: WholeBookAnalysisMode = "diagnostic") =>
    api<WholeBookPrepareResponse>(
      `/api/v1/books/${bookId}/whole-book/prepare?analysis_mode=${analysisMode}`,
    ),

  createRun: (bookId: number, body: CreateWholeBookRunRequest) =>
    api<CreateWholeBookRunResponse>(`/api/v1/books/${bookId}/whole-book/free/create`, {
      method: "POST",
      body: JSON.stringify({
        estimate_id: body.estimate_id,
        ...(body.consent_id != null ? { consent_id: body.consent_id } : {}),
        client_request_id: body.client_request_id,
        max_provider_calls: body.max_provider_calls ?? undefined,
        max_input_tokens: body.max_input_tokens ?? undefined,
        max_output_tokens: body.max_output_tokens ?? undefined,
        max_cost_budget_cny: body.max_cost_budget_cny ?? undefined,
        auto_retry_enabled: Boolean(body.auto_retry_enabled),
        force_full_reanalysis: Boolean(body.force_full_reanalysis),
        reanalyse: Boolean(body.reanalyse),
        ...(body.previous_run_id != null ? { previous_run_id: body.previous_run_id } : {}),
        ...(body.analysis_mode ? { analysis_mode: body.analysis_mode } : {}),
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

  /** CHG-085: continue failed Hierarchical V2 from same-run checkpoints (no new run). */
  resumeFailedRun: (bookId: number, runId: number) =>
    api<{ run: WholeBookRunRecord; run_id: number; resumable_checkpoint?: unknown }>(
      `/api/v1/books/${bookId}/whole-book/free/resume`,
      {
        method: "POST",
        body: JSON.stringify({ run_id: runId }),
      },
    ),

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

  /**
   * Product structure result — GET /api/v1/whole-book/runs/{run_id}/structure
   * Canonical payload: StructureStagesResultV2 (wire v2).
   */
  getStructure: async (runId: number): Promise<StructureProductResponse> => {
    try {
      const resp = await api<StructureProductResponse>(
        `/api/v1/whole-book/runs/${runId}/structure`,
      );
      if (resp.structure != null) {
        try {
          resp.structure = assertStructureStagesResultV2(resp.structure);
        } catch (err) {
          if (err instanceof UnsupportedStructureContractError) {
            throw new ApiError(
              "STRUCTURE_CONTRACT_UNSUPPORTED",
              err.message,
              422,
              { error_code: "STRUCTURE_CONTRACT_UNSUPPORTED", contract_version: err.contractVersion },
            );
          }
          throw err;
        }
      }
      return resp;
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        const detailCode =
          err.detail && typeof err.detail === "object"
            ? String((err.detail as { error_code?: string }).error_code || "")
            : "";
        if (!detailCode) {
          throw new ApiError(
            "STRUCTURE_RESULT_ABSENT",
            err.message || "STRUCTURE_RESULT_ABSENT",
            404,
            { error_code: "STRUCTURE_RESULT_ABSENT" },
          );
        }
      }
      throw err;
    }
  },

  /**
   * Product chapter-functions list — GET /api/v1/whole-book/runs/{run_id}/chapter-functions
   * Canonical payload: ChapterFunctionsResultV2 (wire v2) + cursor pagination.
   */
  getChapterFunctions: async (
    runId: number,
    params?: ChapterFunctionsQueryParams,
  ): Promise<ChapterFunctionsProductResponse> => {
    const limit = clampChapterFunctionsLimit(params?.limit ?? CHAPTER_FUNCTIONS_DEFAULT_LIMIT);
    const qs = new URLSearchParams();
    qs.set("limit", String(limit));
    if (params?.cursor) qs.set("cursor", params.cursor);
    if (params?.offset != null) qs.set("offset", String(params.offset));
    if (params?.function) qs.set("function", params.function);
    if (params?.status) qs.set("status", params.status);
    try {
      const resp = await api<ChapterFunctionsProductResponse>(
        `/api/v1/whole-book/runs/${runId}/chapter-functions?${qs.toString()}`,
      );
      return assertChapterFunctionsEnvelope(resp);
    } catch (err) {
      mapChapterFunctionsApiError(err);
    }
  },

  /**
   * Single-chapter detail — GET .../chapter-functions/{chapter_id}
   * 404 CHAPTER_FUNCTION_CHAPTER_NOT_FOUND when chapter not in set (not module absent).
   */
  getChapterFunctionChapter: async (
    runId: number,
    chapterId: string | number,
  ): Promise<ChapterFunctionsProductResponse> => {
    try {
      const resp = await api<ChapterFunctionsProductResponse>(
        `/api/v1/whole-book/runs/${runId}/chapter-functions/${encodeURIComponent(String(chapterId))}`,
      );
      return assertChapterFunctionsEnvelope(resp);
    } catch (err) {
      mapChapterFunctionsApiError(err);
    }
  },
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
