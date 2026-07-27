import type { WholeBookRunViewState, WholeBookStageProgressDto } from "../../contracts/runView";
import { FIXTURE_RUN_VIEW } from "../../contracts/fixtures";

const baseStages: WholeBookStageProgressDto[] = [
  {
    stage_key: "build_fulltext_index",
    display_name: "建立全文索引",
    order: 10,
    status: "completed",
    required: true,
    resumable: true,
    retryable: true,
    progress_percent: 100,
    started_at: "2026-07-23T01:00:00Z",
    completed_at: "2026-07-23T01:01:00Z",
    attempt_count: 1,
    checkpoint_available: true,
    token_input: null,
    token_output: null,
    cost: null,
    output_artifact_ids: ["art-1"],
    produced_module_keys: ["book_overview"],
    warnings: [],
    error_code: null,
    error_message: null,
    allowed_actions: [],
  },
  {
    stage_key: "resolve_entities",
    display_name: "解析实体",
    order: 20,
    status: "completed",
    required: true,
    resumable: true,
    retryable: true,
    progress_percent: 100,
    started_at: "2026-07-23T01:01:00Z",
    completed_at: "2026-07-23T01:02:00Z",
    attempt_count: 1,
    checkpoint_available: true,
    token_input: null,
    token_output: null,
    cost: null,
    output_artifact_ids: ["art-2"],
    produced_module_keys: ["characters"],
    warnings: [],
    error_code: null,
    error_message: null,
    allowed_actions: [],
  },
  {
    stage_key: "analyze_structure",
    display_name: "分析结构",
    order: 30,
    status: "running",
    required: true,
    resumable: true,
    retryable: true,
    progress_percent: null,
    started_at: "2026-07-23T01:02:00Z",
    completed_at: null,
    attempt_count: 1,
    checkpoint_available: false,
    token_input: null,
    token_output: null,
    cost: null,
    output_artifact_ids: [],
    produced_module_keys: ["structure_stages", "chapter_functions"],
    warnings: [],
    error_code: null,
    error_message: null,
    allowed_actions: ["pause", "cancel"],
  },
  {
    stage_key: "analyze_storylines",
    display_name: "分析故事线",
    order: 40,
    status: "pending",
    required: true,
    resumable: true,
    retryable: true,
    progress_percent: null,
    started_at: null,
    completed_at: null,
    attempt_count: 0,
    checkpoint_available: false,
    token_input: null,
    token_output: null,
    cost: null,
    output_artifact_ids: [],
    produced_module_keys: ["storylines"],
    warnings: [],
    error_code: null,
    error_message: null,
    allowed_actions: [],
  },
];

export const FIXTURE_RUN_RUNNING: WholeBookRunViewState = {
  ...FIXTURE_RUN_VIEW,
  status: "running",
  current_stage: "analyze_structure",
  stages: baseStages,
  completed_modules: ["book_overview"],
  available_modules: [
    "book_overview",
    "structure_stages",
    "chapter_functions",
    "storylines",
  ],
  failed_modules: [],
  partial_results_available: true,
  progress_percent: null,
  token_usage: { input: 0, output: 0 },
  cost: null,
  estimated_remaining: null,
  blocking_issue: null,
  allowed_actions: ["pause", "cancel", "view_partial_results"],
  module_statuses: {
    book_overview: "completed",
    structure_stages: "running",
    chapter_functions: "pending",
    storylines: "pending",
  },
};

export const FIXTURE_RUN_PAUSED: WholeBookRunViewState = {
  ...FIXTURE_RUN_RUNNING,
  status: "paused",
  allowed_actions: ["resume", "cancel", "view_partial_results"],
  stages: baseStages.map((s) =>
    s.stage_key === "analyze_structure"
      ? { ...s, status: "paused", allowed_actions: ["resume", "cancel"] }
      : s,
  ),
};

export const FIXTURE_RUN_INTERRUPTED: WholeBookRunViewState = {
  ...FIXTURE_RUN_RUNNING,
  status: "interrupted",
  blocking_issue: "进程中断：宿主重启（非阶段逻辑失败）",
  allowed_actions: ["resume", "cancel", "view_partial_results"],
  stages: baseStages.map((s) =>
    s.stage_key === "analyze_structure"
      ? {
          ...s,
          status: "interrupted",
          allowed_actions: ["resume", "cancel"],
          error_code: "RUN_INTERRUPTED",
          error_message: "宿主中断，可从检查点恢复",
        }
      : s,
  ),
};

export const FIXTURE_RUN_FAILED_STAGE: WholeBookRunViewState = {
  ...FIXTURE_RUN_RUNNING,
  status: "failed",
  current_stage: "analyze_structure",
  failed_modules: ["structure_stages"],
  partial_results_available: true,
  blocking_issue: "阶段 analyze_structure 失败",
  allowed_actions: ["retry", "cancel", "view_partial_results"],
  stages: baseStages.map((s) => {
    if (s.stage_key === "analyze_structure") {
      return {
        ...s,
        status: "failed",
        error_code: "STAGE_FAILED",
        error_message: "结构分析失败（Fixture）—— 不含正文全文",
        allowed_actions: ["retry", "cancel"],
      };
    }
    return s;
  }),
  module_statuses: {
    book_overview: "completed",
    structure_stages: "failed",
    chapter_functions: "blocked",
    storylines: "pending",
  },
};

export const FIXTURE_RUN_COMPLETED: WholeBookRunViewState = {
  ...FIXTURE_RUN_RUNNING,
  status: "completed",
  current_stage: null,
  completed_modules: [
    "book_overview",
    "structure_stages",
    "chapter_functions",
    "storylines",
  ],
  failed_modules: [],
  partial_results_available: false,
  progress_percent: 100,
  allowed_actions: ["view_partial_results"],
  stages: baseStages.map((s) => ({
    ...s,
    status: "completed",
    progress_percent: 100,
    completed_at: s.completed_at ?? "2026-07-23T01:10:00Z",
    allowed_actions: [],
  })),
};

export const FIXTURE_RUN_CANCELLED: WholeBookRunViewState = {
  ...FIXTURE_RUN_RUNNING,
  status: "cancelled",
  allowed_actions: ["view_partial_results"],
  stages: baseStages.map((s) => {
    if (s.status === "completed") return s;
    return { ...s, status: "cancelled", allowed_actions: [] };
  }),
};

export const RUN_VIEW_FIXTURES = {
  running: FIXTURE_RUN_RUNNING,
  paused: FIXTURE_RUN_PAUSED,
  interrupted: FIXTURE_RUN_INTERRUPTED,
  failed: FIXTURE_RUN_FAILED_STAGE,
  completed: FIXTURE_RUN_COMPLETED,
  cancelled: FIXTURE_RUN_CANCELLED,
} as const;
