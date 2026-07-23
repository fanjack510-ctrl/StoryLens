/**
 * Mock Whole Book Run client transport types (Phase 2A Agent N).
 * Status / allowed_actions always come from the backend — never invented locally.
 */

import type {
  RunAllowedAction,
  WholeBookAnalysisMode,
  WholeBookModuleKey,
  WholeBookModuleStatus,
  WholeBookRunViewStatus,
} from "../../contracts/keys";
import type {
  WholeBookRunViewState,
  WholeBookStageProgressDto,
} from "../../contracts/runView";
import type {
  CreateMockWholeBookRunRequest,
  CreateMockWholeBookRunResult,
  MockProfile,
} from "../contracts/createRun";
import type { MockRunAction, MockRunActionResult } from "../contracts/actions";
import type { MockRunErrorCode } from "../contracts/errors";

export type {
  CreateMockWholeBookRunRequest,
  CreateMockWholeBookRunResult,
  MockProfile,
  MockRunAction,
  MockRunActionResult,
};

/** Lab GET run view — extends Phase 1D RunView with mock markers + version. */
export type MockWholeBookRunViewDto = WholeBookRunViewState & {
  version: number;
  mock: true;
  non_production: true;
  /** Synthetic token/cost only — never real billing. */
  synthetic_usage: true;
  warnings: string[];
  mock_profile?: MockProfile | null;
  engine_id?: string | null;
};

export type MockWholeBookStagesResponse = {
  run_id: number;
  mock: true;
  non_production: true;
  stages: WholeBookStageProgressDto[];
  updated_at: string | null;
  version: number;
};

export type MockRunActionBody = {
  operation_idempotency_key: string;
  expected_state?: WholeBookRunViewStatus | null;
  expected_version?: number | null;
  confirm_cancel?: boolean;
  stage_key?: string | null;
};

export type WholeBookResultIndexDto = {
  run_id: number;
  book_id: number;
  book_snapshot_id: number;
  analysis_mode: WholeBookAnalysisMode;
  run_status: WholeBookRunViewStatus;
  requested_modules: WholeBookModuleKey[];
  available_modules: WholeBookModuleKey[];
  modules: Array<{
    module_key: WholeBookModuleKey;
    module_status: WholeBookModuleStatus;
    partial: boolean;
    stale: boolean;
    candidate?: boolean;
    evidence_count?: number;
  }>;
  mock?: boolean;
  non_production?: boolean;
};

export class MockRunClientError extends Error {
  constructor(
    message: string,
    public readonly code: MockRunErrorCode | "NETWORK" | "DTO_INVALID" | "UNKNOWN",
    public readonly status = 0,
    public readonly cause?: unknown,
    public readonly retryable = false,
  ) {
    super(message);
    this.name = "MockRunClientError";
  }
}

export const LAB_API_BASE = "/api/v1/labs/whole-book-runs";
export const FORMAL_RUN_CREATE_PATH = "/api/v1/books/{book_id}/whole-book-runs";
export const RESULT_INDEX_PATH = "/api/v1/whole-book-runs/{run_id}/results";
export const RESULT_MODULE_PATH =
  "/api/v1/whole-book-runs/{run_id}/results/{module_key}";

export type { RunAllowedAction, WholeBookModuleKey, WholeBookRunViewStatus };
