import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChapterAnalysisProgressPanel } from "./ChapterAnalysisProgressPanel";
import type { Run } from "../../types";

vi.mock("../../services/analysisApi", () => ({
  analysisApi: {
    readerJourney: vi.fn(async () => ({ status: "missing" })),
    sceneAnalysisResumePreflight: vi.fn(),
    resumeSceneAnalysis: vi.fn(),
  },
}));

vi.mock("../../services/analysisRecoveryApi", () => ({
  analysisRecoveryApi: {
    recoveryPlan: vi.fn(async () => ({
      run_id: 5,
      status: "boundary_confirmed_budget_blocked",
      user_status: "paused_recoverable",
      recoverable: true,
      blockers: [
        {
          code: "REQUEST_BUDGET_INSUFFICIENT",
          reason: "request_budget_insufficient",
          user_message: "今日云端请求额度不足",
        },
      ],
      warnings: [],
      checks: [
        {
          id: "request_budget",
          label: "req",
          status: "fail",
          user_label: "请求额度不足",
        },
      ],
      recommended_actions: [],
      resume_stage: "scene_analysis",
      will_reuse_artifacts: [],
      will_create_entities: [],
      estimated_requests: 0,
      estimated_tokens: 0,
      estimated_cost: 0,
      currency: "CNY",
      recovery_attempts: 0,
      details: {},
    })),
    recover: vi.fn(),
  },
}));

vi.mock("../../services/settingsApi", () => ({
  settingsApi: {
    cloudUsage: vi.fn(async () => ({
      request_count: 37,
      total_tokens: 12000,
      estimated_cost: 0.12,
      remaining_requests: 13,
      remaining_tokens: 164405,
      remaining_estimated_cost: 19.87,
    })),
    cloudBudget: vi.fn(async () => ({
      cloud_daily_request_limit: 50,
      cloud_daily_estimated_cost_limit: 20,
    })),
    saveCloudBudget: vi.fn(),
  },
}));

function run(partial: Partial<Run> = {}): Run {
  return {
    id: 5,
    subject_id: "2",
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
    current_stage: "scene_analysis",
    total_scene_count: 13,
    completed_scene_count: 0,
    scene_analysis_resume_available: true,
    budget_required: { requests: 26 },
    budget_remaining: { requests: 13, tokens: 164405, estimated_cost: 19.87 },
    exceeded_dimensions: ["requests"],
    ...partial,
  };
}

afterEach(cleanup);

describe("ChapterAnalysisProgressPanel budget pause", () => {
  it("shows live run meta and unified recovery card, not failed card", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <ChapterAnalysisProgressPanel
            run={run()}
            uiState="awaiting_budget_adjustment"
            chapterTitle="第一章"
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("chapter-analysis-run-id")).toHaveTextContent("#5");
    expect(screen.getByTestId("chapter-analysis-scene-progress")).toHaveTextContent("0 / 13");
    expect(screen.getByTestId("chapter-analysis-status-badge")).toHaveTextContent("分析已暂停");
    expect(await screen.findByTestId("unified-recovery-card")).toBeInTheDocument();
    expect(screen.queryByTestId("chapter-analysis-failure")).not.toBeInTheDocument();
  });
});
