/**
 * Run UX local view types — consume Phase 1D-P contracts; do not fork Preflight DTO.
 */

import type {
  PreflightStagePlanItemDto,
  WholeBookPreflightPageModel,
} from "../contracts/preflight";
import type {
  RunAllowedAction,
  WholeBookAnalysisMode,
  WholeBookModuleKey,
} from "../contracts/keys";
import type { WholeBookRunViewState } from "../contracts/runView";

/** Extended stage plan row for preview (optional fields may come from fixtures). */
export type StagePlanPreviewRow = PreflightStagePlanItemDto & {
  resumable?: boolean;
  retryable?: boolean;
  dependencies?: string[];
  auto_filled?: boolean;
  description?: string;
};

export type PreflightUiStatus =
  | "loading"
  | "empty"
  | "blocked"
  | "preview"
  | "error";

export type RunUxTheme = "light" | "dark";

export type PreflightLoadErrorCode =
  | "NETWORK"
  | "OFFLINE"
  | "DTO_INVALID"
  | "BOOK_NOT_FOUND"
  | "HTTP"
  | "UNKNOWN";

export type PreflightLoadError = {
  code: PreflightLoadErrorCode;
  message: string;
};

export type WholeBookPreflightRequest = {
  analysis_mode: WholeBookAnalysisMode;
  requested_modules?: WholeBookModuleKey[];
  book_snapshot_id?: number | null;
  configuration_fingerprint?: string | null;
};

/** Phase 1C live preflight HTTP body (backend is sole source of truth). */
export type Phase1cPreflightApiResponse = {
  book_id: number;
  book_snapshot_id: number | null;
  snapshot_status: string | null;
  chapter_count: number;
  character_count: number;
  requested_mode: string;
  analysis_mode: string;
  supported_modules: string[];
  stage_plan: Array<Record<string, unknown>>;
  capability_decision?: Record<string, unknown>;
  quota_decision?: Record<string, unknown>;
  engine_status?: Record<string, unknown>;
  run_creation_enabled: boolean;
  blocking_reasons: string[];
  warnings: string[];
  engine_id: string | null;
  stage_count?: number;
  capability?: Record<string, unknown>;
  notes?: Record<string, unknown>;
  /** Optional enriched page fields when Integration later aligns shapes. */
  book?: Record<string, unknown>;
  snapshot?: Record<string, unknown>;
  source_coverage?: Record<string, unknown> | {
    fulltext_snapshot_ready?: boolean;
    enhanced_asset_coverage_ratio?: number | null;
    scene_coverage_ratio?: number | null;
    reader_journey_coverage_ratio?: number | null;
    chapter_analysis_coverage_ratio?: number | null;
    enhanced_degraded?: boolean;
  };
  estimated_usage?: Record<string, unknown> | {
    estimated_token_input?: number | null;
    estimated_token_output?: number | null;
    estimated_cost?: number | null;
    estimated_duration_class?: string;
    currency?: string;
  };
  requested_modules?: string[];
  resolved_modules?: string[];
  auto_fill_notes?: string[];
  confirmation_required?: boolean;
  force_start_allowed?: boolean;
  title?: string;
  paragraph_count?: number;
};

export type MockRunActionRequest = {
  action: Extract<RunAllowedAction, "pause" | "resume" | "retry" | "cancel">;
  run_id: number;
  stage_key?: string;
  /** Future API path preview only — never executed against production. */
  future_path: string;
};

export type MockRunActionResult = {
  ok: boolean;
  action: MockRunActionRequest["action"];
  message: string;
  next_status?: WholeBookRunViewState["status"];
  request_preview: MockRunActionRequest;
};

export type PreflightViewModel = {
  status: PreflightUiStatus;
  model: WholeBookPreflightPageModel | null;
  error: PreflightLoadError | null;
  supported_modes: WholeBookAnalysisMode[];
  stage_plan_rows: StagePlanPreviewRow[];
};
