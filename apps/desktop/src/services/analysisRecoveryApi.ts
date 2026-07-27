import { api } from "./apiClient";

/** Unified Analysis Recovery Center client (non-frozen API surface). */
export const analysisRecoveryApi = {
  recoveryPlan: (runId: number) =>
    api<{
      run_id: number;
      chapter_id: number | null;
      status: string;
      user_status: string;
      pause_reason: string | null;
      recoverable: boolean;
      blockers: Array<{
        code: string;
        reason: string;
        user_message: string;
        severity?: string;
        required?: number | null;
        available?: number | null;
        shortfall?: number | null;
        provider?: string | null;
        model?: string | null;
        settings_focus?: string | null;
      }>;
      warnings: Array<{ code: string; message: string }>;
      checks: Array<{
        id: string;
        label: string;
        status: string;
        detail?: string | null;
        user_label?: string | null;
        internal_code?: string | null;
        required?: number | null;
        available?: number | null;
        shortfall?: number | null;
      }>;
      recommended_actions: Array<{
        action: string;
        label: string;
        automatic?: boolean;
        requires_user_authorization?: boolean;
      }>;
      resume_stage: string;
      will_reuse_artifacts: string[];
      will_create_entities: string[];
      estimated_requests: number;
      estimated_tokens: number;
      estimated_cost: number;
      currency: string;
      provider?: string | null;
      model?: string | null;
      request_hash?: string | null;
      recovery_attempts: number;
      retry_eligible?: boolean;
      existing_recovery_run_id?: number | null;
      budget_authorization_proposal?: {
        scope: string;
        current_daily_request_limit: number;
        current_remaining_requests: number;
        required_requests: number;
        suggested_extra_requests: number;
        suggested_daily_request_limit?: number | null;
        estimated_cost: number;
        currency: string;
        will_not_rerun: string[];
        message: string;
      } | null;
      details: Record<string, unknown>;
      reader_journey_run_id?: number | null;
      current_stage?: string | null;
    }>(`/api/v1/analysis-runs/${runId}/recovery-plan`),
  recover: (
    runId: number,
    payload: {
      client_request_id: string;
      cloud_consent: boolean;
      confirmed: boolean;
      recovery_mode?: "unified" | "boundary_checkpoints";
      provider_state_version?: string;
      resume?: boolean;
      authorize_budget?: {
        scope: "run_temporary" | "global_permanent";
        extra_requests?: number;
        extra_tokens?: number;
        extra_cost?: number;
        new_daily_request_limit?: number;
      };
    },
  ) =>
    api<{
      run_id: number;
      status: string;
      user_status: string;
      recoverable: boolean;
      idempotent_replay?: boolean;
      actions_executed: string[];
      resume_stage: string;
      blockers: Array<{
        code: string;
        reason: string;
        user_message: string;
        settings_focus?: string | null;
      }>;
      budget_authorization_proposal?: Record<string, unknown> | null;
      details: Record<string, unknown>;
      http_request_sent: boolean;
      model_invocations_started: boolean;
      reader_journey_run_id?: number | null;
      checks?: Array<{ id: string; status: string; user_label?: string | null }>;
    }>(`/api/v1/analysis-runs/${runId}/recover`, {
      method: "POST",
      body: JSON.stringify({ recovery_mode: "unified", resume: true, ...payload }),
    }),
  fullPipelinePreflight: (payload: Record<string, unknown>) =>
    api<Record<string, unknown>>("/api/v1/analysis-runs/full-pipeline-preflight", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
