/** CreateMockWholeBookRun request/result mirror (Phase 2A-P). */

import type { WholeBookAnalysisMode, WholeBookModuleKey, WholeBookRunViewStatus } from "../../contracts/keys";

export const MOCK_PROFILES = [
  "deterministic_minimal",
  "deterministic_full",
  "fault_injection",
] as const;

export type MockProfile = (typeof MOCK_PROFILES)[number];

export const CREATE_MOCK_RUN_SEQUENCE = [
  "authorize",
  "validate_snapshot",
  "validate_request",
  "resolve_modules",
  "build_stage_plan",
  "reserve_mock_execution_slot",
  "create_analysis_run",
  "create_analysis_run_stages",
  "register_execution_task",
  "return_run_view",
] as const;

export type CreateMockWholeBookRunRequest = {
  book_id: number;
  book_snapshot_id: number;
  analysis_mode: WholeBookAnalysisMode;
  requested_modules: readonly WholeBookModuleKey[];
  configuration_fingerprint: string;
  idempotency_key: string;
  mock_profile: MockProfile;
  requested_by: string;
  preflight_fingerprint: string;
};

export type CreateMockWholeBookRunResult = {
  run_id: number;
  book_id: number;
  book_snapshot_id: number;
  status: WholeBookRunViewStatus;
  analysis_mode: WholeBookAnalysisMode;
  requested_modules: readonly WholeBookModuleKey[];
  resolved_modules: readonly WholeBookModuleKey[];
  stage_plan: readonly string[];
  mock: true;
  non_production: true;
  created: boolean;
  duplicate_of_run_id: number | null;
  created_at: string;
};
