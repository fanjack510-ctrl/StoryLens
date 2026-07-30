import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UnifiedAnalysisRecoveryCard } from "../components/chapterAnalysis/UnifiedAnalysisRecoveryCard";
import { analysisRecoveryApi } from "./analysisRecoveryApi";
import type { Run } from "../types";

vi.mock("./analysisRecoveryApi", () => ({
  analysisRecoveryApi: {
    recoveryPlan: vi.fn(),
    recover: vi.fn(),
  },
}));

function baseRun(extra: Partial<Run> = {}): Run {
  return {
    id: 77,
    task_type: "chapter_analysis",
    subject_type: "chapter",
    subject_id: "2",
    provider: "fake",
    model: "fake",
    status: "succeeded",
    progress_current: 3,
    progress_total: 3,
    error_code: null,
    error_message: null,
    root_error_code: null,
    root_error_message: null,
    failed_stage: null,
    failed_invocation_id: null,
    provider_health_at_failure: null,
    retryable: true,
    user_action_hint: null,
    retry_of_run_id: null,
    created_at: "",
    queued_at: "",
    started_at: null,
    completed_at: null,
    execution_mode: "cloud",
    analysis_mode: "BALANCED",
    cloud_consent: true,
    cloud_consent_at: null,
    sends_content_to_cloud: true,
    ...extra,
  } as Run;
}

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CHG-018 UnifiedAnalysisRecoveryCard vs active journey", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("does not render paused card when journeyPageActive", async () => {
    vi.mocked(analysisRecoveryApi.recoveryPlan).mockResolvedValue({
      run_id: 77,
      status: "succeeded",
      user_status: "paused_recoverable",
      recoverable: true,
      pause_reason: "awaiting_reader_journey",
      blockers: [],
      warnings: [],
      checks: [],
      recommended_actions: [
        { action: "fix_and_continue", label: "修复并继续", automatic: false },
      ],
      resume_stage: "reader_journey",
      will_reuse_artifacts: [],
      will_create_entities: [],
      estimated_requests: 0,
      estimated_tokens: 0,
      estimated_cost: 0,
      currency: "CNY",
      recovery_attempts: 0,
      details: {},
    } as any);

    wrap(
      <UnifiedAnalysisRecoveryCard
        run={baseRun({ journey_status: "starting" })}
        journeyPageActive
      />,
    );
    await waitFor(() => {
      expect(screen.queryByTestId("unified-recovery-card")).not.toBeInTheDocument();
    });
    expect(screen.queryByText("分析已暂停")).not.toBeInTheDocument();
    expect(analysisRecoveryApi.recover).not.toHaveBeenCalled();
  });

  it("hides card when plan reports running journey", async () => {
    vi.mocked(analysisRecoveryApi.recoveryPlan).mockResolvedValue({
      run_id: 77,
      status: "succeeded",
      user_status: "running",
      recoverable: false,
      pause_reason: null,
      blockers: [],
      warnings: [],
      checks: [],
      recommended_actions: [],
      resume_stage: "reader_journey",
      reader_journey_status: "scene_profiles_running",
      will_reuse_artifacts: [],
      will_create_entities: [],
      estimated_requests: 0,
      estimated_tokens: 0,
      estimated_cost: 0,
      currency: "CNY",
      recovery_attempts: 0,
      details: {},
    } as any);

    wrap(<UnifiedAnalysisRecoveryCard run={baseRun()} />);
    await waitFor(() => {
      expect(screen.queryByTestId("unified-recovery-card")).not.toBeInTheDocument();
    });
  });
});
