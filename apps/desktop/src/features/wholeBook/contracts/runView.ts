import type {
  RunAllowedAction,
  StageStatus,
  WholeBookAnalysisMode,
  WholeBookModuleKey,
  WholeBookModuleStatus,
  WholeBookRunViewStatus,
} from "./keys";

export interface WholeBookStageProgressDto {
  stage_key: string;
  display_name: string;
  order: number;
  status: StageStatus;
  required: boolean;
  resumable: boolean;
  retryable: boolean;
  progress_percent: number | null;
  started_at: string | null;
  completed_at: string | null;
  attempt_count: number;
  checkpoint_available: boolean;
  token_input: number | null;
  token_output: number | null;
  cost: number | null;
  output_artifact_ids: string[];
  produced_module_keys: string[];
  warnings: string[];
  error_code: string | null;
  error_message: string | null;
  allowed_actions: RunAllowedAction[];
}

export interface WholeBookRunViewState {
  run_id: number;
  book_id: number;
  snapshot_id: number;
  analysis_mode: WholeBookAnalysisMode;
  status: WholeBookRunViewStatus;
  current_stage: string | null;
  stages: WholeBookStageProgressDto[];
  completed_modules: WholeBookModuleKey[];
  available_modules: WholeBookModuleKey[];
  failed_modules: WholeBookModuleKey[];
  partial_results_available: boolean;
  progress_percent: number | null;
  token_usage: Record<string, number>;
  cost: number | null;
  started_at: string | null;
  updated_at: string | null;
  estimated_remaining: string | null;
  blocking_issue: string | null;
  allowed_actions: RunAllowedAction[];
  module_statuses: Partial<Record<WholeBookModuleKey, WholeBookModuleStatus>>;
}
