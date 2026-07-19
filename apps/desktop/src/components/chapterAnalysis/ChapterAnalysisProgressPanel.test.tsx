import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChapterAnalysisProgressPanel } from "./ChapterAnalysisProgressPanel";
import type { Run } from "../../types";

vi.mock("../../services/analysisApi", () => ({
  analysisApi: {
    readerJourney: vi.fn(async () => ({ status: "missing", visualization: null })),
  },
}));

vi.mock("../../services/analysisRecoveryApi", () => ({
  analysisRecoveryApi: {
    recoveryPlan: vi.fn(async () => ({
      run_id: 55,
      status: "succeeded",
      user_status: "paused_recoverable",
      recoverable: true,
      blockers: [
        {
          code: "AWAITING_READER_JOURNEY",
          reason: "awaiting_reader_journey",
          user_message: "阅读旅程尚未生成",
        },
      ],
      warnings: [],
      checks: [
        {
          id: "scene_artifacts",
          label: "scene",
          status: "pass",
          user_label: "Scene分析已完成",
        },
      ],
      recommended_actions: [],
      resume_stage: "reader_journey",
      will_reuse_artifacts: ["AnalysisRun", "SceneArtifacts"],
      will_create_entities: ["ReaderJourneyRun"],
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
      request_count: 1,
      total_tokens: 10,
      estimated_cost: 0.01,
      remaining_requests: 49,
    })),
  },
}));

function renderPanel(ui: React.ReactElement) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function run(partial: Partial<Run> = {}): Run {
  return {
    id: 55,
    subject_id: "2",
    provider: "fake",
    model: "fake",
    status: "scene_analysis_running",
    progress_current: 2,
    progress_total: 4,
    execution_mode: "cloud",
    cloud_consent: true,
    sends_content_to_cloud: true,
    retryable: false,
    created_at: "2026-01-01T00:00:00Z",
    reusable_checkpoint_count: 0,
    conflicted_checkpoint_count: 0,
    checkpoint_total_count: 0,
    checkpoint_available: false,
    completed_scene_count: 5,
    total_scene_count: 14,
    ...partial,
  };
}

afterEach(cleanup);

describe("ChapterAnalysisProgressPanel", () => {
  it("shows running progress with run id and scene counts from status API", () => {
    renderPanel(
        <ChapterAnalysisProgressPanel
          run={run()}
          uiState="running"
          chapterTitle="第一章"
        />,
    );
    expect(screen.getByTestId("chapter-analysis-progress")).toBeInTheDocument();
    expect(screen.getByTestId("chapter-analysis-status-badge")).toHaveTextContent("正在分析本章");
    expect(screen.getByTestId("chapter-analysis-run-id")).toHaveTextContent("#55");
    expect(screen.getByTestId("chapter-analysis-count")).toHaveTextContent("5 / 14");
    expect(screen.queryByText(/invocation/i)).not.toBeInTheDocument();
  });

  it("shows boundary review entry", () => {
    const onReview = vi.fn();
    renderPanel(
        <ChapterAnalysisProgressPanel
          run={run({ status: "awaiting_boundary_review" })}
          uiState="boundary_review_required"
          onReviewBoundary={onReview}
        />,
    );
    fireEvent.click(screen.getByTestId("chapter-analysis-review-boundary"));
    expect(onReview).toHaveBeenCalled();
  });

  it("shows success CTA that opens embedded results when callback provided", () => {
    const onViewResults = vi.fn();
    renderPanel(
        <ChapterAnalysisProgressPanel
          run={run({ status: "succeeded", completed_at: "2026-01-02T00:00:00Z" })}
          uiState="succeeded"
          onViewResults={onViewResults}
        />,
    );
    const cta = screen.getByTestId("chapter-analysis-open-results");
    expect(cta).toHaveTextContent("查看正文与读者旅程");
    fireEvent.click(cta);
    expect(onViewResults).toHaveBeenCalled();
  });

  it("shows unified recovery card when awaiting reader journey", async () => {
    renderPanel(
      <ChapterAnalysisProgressPanel
        run={run({ status: "succeeded", completed_scene_count: 13, total_scene_count: 13 })}
        uiState="awaiting_reader_journey_start"
        onContinueReaderJourney={vi.fn()}
        onViewResults={vi.fn()}
      />,
    );
    expect(await screen.findByTestId("unified-recovery-card")).toBeInTheDocument();
    expect(screen.getByTestId("unified-recovery-fix-continue")).toHaveTextContent(
      "修复并继续",
    );
    expect(screen.queryByText("分析全部完成")).not.toBeInTheDocument();
  });

  it("shows unified recovery card for partial resume", async () => {
    renderPanel(
        <ChapterAnalysisProgressPanel
          run={run({
            status: "scene_analysis_partial",
            scene_analysis_resume_available: true,
            remaining_scene_count: 4,
          })}
          uiState="partial"
          canResume
          onResume={vi.fn()}
        />,
    );
    expect(await screen.findByTestId("unified-recovery-card")).toBeInTheDocument();
    expect(screen.queryByTestId("chapter-analysis-failure")).not.toBeInTheDocument();
  });
});
