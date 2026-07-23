import type { MockWholeBookRunViewDto } from "../client/types";
import { FIXTURE_RUN_RUNNING, FIXTURE_RUN_PAUSED, FIXTURE_RUN_FAILED_STAGE, FIXTURE_RUN_INTERRUPTED, FIXTURE_RUN_CANCELLED, FIXTURE_RUN_COMPLETED } from "../../runUx/fixtures/runViewFixtures";
import type { CreateMockWholeBookRunResult } from "../contracts/createRun";
import type { MockRunActionResult } from "../contracts/actions";
import type { WholeBookResultIndexDto } from "../client/types";
import { FIXTURE_RESULT_ENVELOPE } from "../../contracts/fixtures";

function withMock(view: typeof FIXTURE_RUN_RUNNING, overrides: Partial<MockWholeBookRunViewDto> = {}): MockWholeBookRunViewDto {
  return {
    ...view,
    version: 1,
    mock: true,
    non_production: true,
    synthetic_usage: true,
    warnings: [],
    ...overrides,
  };
}

export const MOCK_FIXTURE_RUNNING = withMock(FIXTURE_RUN_RUNNING, { version: 3 });
export const MOCK_FIXTURE_PAUSED = withMock(FIXTURE_RUN_PAUSED, {
  version: 4,
  status: "paused",
  allowed_actions: ["resume", "cancel", "view_partial_results"],
});
export const MOCK_FIXTURE_INTERRUPTED = withMock(FIXTURE_RUN_INTERRUPTED, {
  version: 5,
  status: "interrupted",
  allowed_actions: ["resume", "cancel", "view_partial_results"],
});
export const MOCK_FIXTURE_FAILED = withMock(FIXTURE_RUN_FAILED_STAGE, {
  version: 6,
  status: "failed",
  allowed_actions: ["retry", "cancel", "view_partial_results"],
});
export const MOCK_FIXTURE_CANCELLED = withMock(FIXTURE_RUN_CANCELLED, {
  version: 7,
  status: "cancelled",
  allowed_actions: ["view_partial_results"],
  partial_results_available: true,
});
export const MOCK_FIXTURE_COMPLETED = withMock(FIXTURE_RUN_COMPLETED, {
  version: 8,
  status: "completed",
  allowed_actions: ["view_partial_results"],
  partial_results_available: true,
});

export const MOCK_CREATE_RESULT_NEW: CreateMockWholeBookRunResult = {
  run_id: 101,
  book_id: 1,
  book_snapshot_id: 11,
  status: "pending",
  analysis_mode: "whole_book_native",
  requested_modules: ["book_overview", "structure_stages"],
  resolved_modules: ["book_overview", "structure_stages"],
  stage_plan: ["build_fulltext_index", "resolve_entities", "analyze_structure"],
  mock: true,
  non_production: true,
  created: true,
  duplicate_of_run_id: null,
  created_at: "2026-07-23T12:00:00Z",
};

export const MOCK_CREATE_RESULT_DUP: CreateMockWholeBookRunResult = {
  ...MOCK_CREATE_RESULT_NEW,
  created: false,
  duplicate_of_run_id: 101,
};

export function mockActionResult(
  action: MockRunActionResult["action"],
  current_state: MockRunActionResult["current_state"],
): MockRunActionResult {
  return {
    run_id: 101,
    action,
    requested: true,
    accepted: true,
    current_state,
    idempotent_replay: false,
    detail_code: null,
  };
}

export const MOCK_RESULT_INDEX: WholeBookResultIndexDto = {
  run_id: 101,
  book_id: 1,
  book_snapshot_id: 11,
  analysis_mode: "whole_book_native",
  run_status: "cancelled",
  requested_modules: ["book_overview", "structure_stages"],
  available_modules: ["book_overview"],
  modules: [
    {
      module_key: "book_overview",
      module_status: "completed",
      partial: false,
      stale: false,
      candidate: true,
      evidence_count: 1,
    },
    {
      module_key: "structure_stages",
      module_status: "failed",
      partial: false,
      stale: false,
      candidate: false,
      evidence_count: 0,
    },
  ],
  mock: true,
  non_production: true,
};

export const MOCK_MODULE_ENVELOPE = {
  ...FIXTURE_RESULT_ENVELOPE,
  module_status: "completed" as const,
  partial: false,
  stale: false,
};
