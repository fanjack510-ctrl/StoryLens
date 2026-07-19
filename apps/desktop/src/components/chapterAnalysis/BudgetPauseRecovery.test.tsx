import type { ReactNode } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BudgetPauseRecovery } from "./BudgetPauseRecovery";
import type { Run } from "../../types";

vi.mock("../../services/settingsApi", () => ({
  settingsApi: {
    cloudBudget: vi.fn(async () => ({
      cloud_daily_request_limit: 50,
      cloud_daily_estimated_cost_limit: 20,
      currency: "CNY",
    })),
    saveCloudBudget: vi.fn(async (v: unknown) => v),
    cloudUsage: vi.fn(async () => ({
      request_count: 37,
      remaining_requests: 13,
      remaining_tokens: 164405,
      remaining_estimated_cost: 19.877306,
    })),
  },
}));

vi.mock("../../services/analysisApi", () => ({
  analysisApi: {
    sceneAnalysisResumePreflight: vi.fn(async () => ({
      eligible: true,
      within_budget: true,
      worst_case_requests: 26,
      remaining_budget: { requests: 43 },
      provider_state_version: "v1",
    })),
    resumeSceneAnalysis: vi.fn(async () => ({ run_id: 5, status: "scene_analysis_running" })),
  },
}));

import { analysisApi } from "../../services/analysisApi";
import { settingsApi } from "../../services/settingsApi";

function run(partial: Partial<Run> = {}): Run {
  return {
    id: 5,
    subject_id: "1",
    provider: "aliyun_qwen_plus",
    model: "qwen",
    status: "boundary_confirmed_budget_blocked",
    progress_current: 0,
    progress_total: 13,
    execution_mode: "cloud",
    cloud_consent: true,
    sends_content_to_cloud: true,
    retryable: true,
    created_at: "2026-07-19T00:00:00Z",
    reusable_checkpoint_count: 0,
    conflicted_checkpoint_count: 0,
    checkpoint_total_count: 0,
    checkpoint_available: false,
    error_code: "INSUFFICIENT_BUDGET_RESERVATION",
    failed_stage: "scene_analysis_budget",
    total_scene_count: 13,
    completed_scene_count: 0,
    scene_analysis_resume_available: true,
    budget_required: { requests: 26, tokens: 1000, estimated_cost: 0.3 },
    budget_remaining: { requests: 13, tokens: 164405, estimated_cost: 19.877306 },
    exceeded_dimensions: ["requests"],
    ...partial,
  };
}

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("BudgetPauseRecovery", () => {
  it("shows request shortage and keeps recovery card", async () => {
    renderWithClient(<BudgetPauseRecovery run={run()} variant="card" />);
    expect(await screen.findByTestId("budget-pause-title")).toHaveTextContent(
      "分析已暂停：今日云端请求额度不足",
    );
    expect(screen.getByTestId("budget-pause-body")).toHaveTextContent("26");
    expect(screen.getByTestId("budget-pause-body")).toHaveTextContent("13");
    expect(screen.getByTestId("budget-pause-body")).toHaveTextContent("Token预算充足");
    expect(screen.getByTestId("budget-pause-body")).not.toHaveTextContent("费用不足");
  });

  it("one-click adjust updates request limit and resumes same run", async () => {
    const onContinued = vi.fn();
    renderWithClient(
      <BudgetPauseRecovery run={run()} variant="card" onContinued={onContinued} />,
    );
    fireEvent.click(await screen.findByTestId("budget-adjust-and-continue"));
    expect(screen.getByTestId("budget-adjust-recommended")).toHaveTextContent("80");
    expect(screen.getByTestId("budget-adjust-cost-limit")).toHaveTextContent("20");
    fireEvent.click(screen.getByTestId("budget-confirm-adjust-continue"));
    await waitFor(() => expect(settingsApi.saveCloudBudget).toHaveBeenCalled());
    const saved = vi.mocked(settingsApi.saveCloudBudget).mock.calls[0][0] as {
      cloud_daily_request_limit: number;
      cloud_daily_estimated_cost_limit: number;
    };
    expect(saved.cloud_daily_request_limit).toBe(80);
    expect(saved.cloud_daily_estimated_cost_limit).toBe(20);
    await waitFor(() => expect(analysisApi.resumeSceneAnalysis).toHaveBeenCalledWith(
      5,
      expect.objectContaining({ confirmed: true, cloud_consent: true }),
    ));
    expect(onContinued).toHaveBeenCalled();
  });

  it("keeps technical error code only in details", async () => {
    renderWithClient(<BudgetPauseRecovery run={run()} variant="modal" onCloseModal={() => undefined} />);
    expect(screen.queryByText("INSUFFICIENT_BUDGET_RESERVATION")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("budget-pause-tech-toggle"));
    expect(screen.getByTestId("budget-pause-tech-details")).toHaveTextContent(
      "INSUFFICIENT_BUDGET_RESERVATION",
    );
  });
});
