import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TasksPage } from "./TasksPage";
import { analysisApi } from "../services/analysisApi";
import { ApiError } from "../services/apiClient";

vi.mock("../services/analysisApi", () => ({
  analysisApi: {
    runs: vi.fn(),
    run: vi.fn(),
    retry: vi.fn(),
    cancel: vi.fn(),
    resumeSceneAnalysis: vi.fn(),
    replaySceneAnalysisOffline: vi.fn(),
    sceneAnalysisResumePreflight: vi.fn(),
    invocations: vi.fn(),
    recoveryPreflight: vi.fn(),
    recoverPreflight: vi.fn(),
    continueFromCheckpoints: vi.fn(),
    readerJourney: vi.fn(async () => null),
  },
}));

vi.mock("../services/analysisRecoveryApi", () => ({
  analysisRecoveryApi: {
    recoveryPlan: vi.fn(async () => ({
      run_id: 1,
      status: "failed",
      user_status: "paused_recoverable",
      recoverable: false,
      blockers: [],
      warnings: [],
      checks: [],
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

vi.mock("../services/booksApi", () => ({
  booksApi: {
    list: vi.fn(async () => [{ id: 1, title: "测试书" }]),
    chapters: vi.fn(async () => [{ id: 2, section_type: "chapter", title: "开端" }]),
  },
}));

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
});

const baseRun = {
  subject_id: "2",
  provider: "fake",
  model: "fake",
  progress_current: 1,
  progress_total: 6,
  execution_mode: "cloud",
  cloud_consent: true,
  sends_content_to_cloud: true,
  retryable: false,
  created_at: "2026-07-29T00:00:00Z",
  reusable_checkpoint_count: 0,
  conflicted_checkpoint_count: 0,
  checkpoint_total_count: 0,
  checkpoint_available: false,
  completed_scene_count: 1,
  total_scene_count: 6,
  remaining_scene_count: 5,
  status_version: 1,
  can_cancel: true,
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TasksPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TasksPage stop analysis CHG-006", () => {
  it("shows stop for running and hides for completed/failed/cancelled", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([
      { ...baseRun, id: 1, status: "running" },
      { ...baseRun, id: 2, status: "succeeded", can_cancel: false, chapter_complete: true },
      { ...baseRun, id: 3, status: "failed", can_cancel: false },
      { ...baseRun, id: 4, status: "cancelled", can_cancel: false, can_restart_as_new_task: true },
      { ...baseRun, id: 5, status: "queued" },
      { ...baseRun, id: 6, status: "awaiting_provider_recovery" },
    ] as any);
    renderPage();
    await screen.findByTestId("stop-analysis-1");
    expect(screen.getByTestId("stop-analysis-5")).toBeTruthy();
    expect(screen.getByTestId("stop-analysis-6")).toBeTruthy();
    expect(screen.queryByTestId("stop-analysis-2")).toBeNull();
    expect(screen.queryByTestId("stop-analysis-3")).toBeNull();
    expect(screen.queryByTestId("stop-analysis-4")).toBeNull();
    expect(screen.getByTestId("reanalyze-4")).toBeTruthy();
    expect(screen.getAllByText("已停止").length).toBeGreaterThan(0);
  });

  it("confirm dialog; dismiss does not call cancel; confirm calls cancel once", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([
      { ...baseRun, id: 10, status: "scene_analysis_running" },
    ] as any);
    vi.mocked(analysisApi.cancel).mockResolvedValue({
      task_id: 10,
      previous_status: "scene_analysis_running",
      current_status: "cancellation_requested",
      message: "正在停止分析",
      already_requested: false,
      already_cancelled: false,
      already_completed: false,
      cannot_cancel: false,
      can_restart_as_new_task: true,
      status_version: 2,
    } as any);
    renderPage();
    fireEvent.click(await screen.findByTestId("stop-analysis-10"));
    expect(await screen.findByTestId("stop-confirm-dialog")).toBeTruthy();
    expect(screen.getByText(/确定停止本次分析吗/)).toBeTruthy();
    fireEvent.click(screen.getByTestId("stop-continue-analysis"));
    await waitFor(() => expect(screen.queryByTestId("stop-confirm-dialog")).toBeNull());
    expect(analysisApi.cancel).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("stop-analysis-10"));
    fireEvent.click(await screen.findByTestId("stop-confirm-submit"));
    await waitFor(() => expect(analysisApi.cancel).toHaveBeenCalledTimes(1));
    expect(vi.mocked(analysisApi.cancel).mock.calls[0][0]).toBe(10);
  });

  it("shows stopping copy and hides stop button", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([
      { ...baseRun, id: 11, status: "cancellation_requested", can_cancel: false },
    ] as any);
    renderPage();
    expect(await screen.findByText("正在停止")).toBeTruthy();
    expect(screen.getByTestId("stopping-hint-11")).toBeTruthy();
    expect(screen.queryByTestId("stop-analysis-11")).toBeNull();
  });

  it("surfaces cancel API error with technical code", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([
      { ...baseRun, id: 12, status: "running" },
    ] as any);
    vi.mocked(analysisApi.cancel).mockRejectedValue(
      new ApiError("ANALYSIS_RUN_VERSION_CONFLICT", "任务状态已变化，请刷新后重试。", 409),
    );
    renderPage();
    fireEvent.click(await screen.findByTestId("stop-analysis-12"));
    fireEvent.click(await screen.findByTestId("stop-confirm-submit"));
    expect(await screen.findByTestId("stop-error")).toBeTruthy();
    expect(screen.getByText("ANALYSIS_RUN_VERSION_CONFLICT")).toBeTruthy();
  });
});
