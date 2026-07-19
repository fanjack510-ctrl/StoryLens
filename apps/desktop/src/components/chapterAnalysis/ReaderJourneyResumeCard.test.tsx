import type { ComponentProps } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneyResumeCard } from "./ReaderJourneyResumeCard";
import { analysisApi } from "../../services/analysisApi";
import { settingsApi } from "../../services/settingsApi";
import { journeyClientRequestKey } from "../../services/chapterJourneyComposition";
import type { Run } from "../../types";

vi.mock("../../services/analysisApi", async () => {
  const actual = await vi.importActual<typeof import("../../services/analysisApi")>(
    "../../services/analysisApi",
  );
  return {
    analysisApi: {
      ...actual.analysisApi,
      readerJourneyPreflight: vi.fn(),
      createReaderJourney: vi.fn(),
      resumeReaderJourney: vi.fn(),
    },
  };
});

vi.mock("../../services/settingsApi", () => ({
  settingsApi: {
    cloudUsage: vi.fn(async () => ({
      remaining_requests: 40,
      remaining_tokens: 800000,
      remaining_estimated_cost: 12.5,
    })),
  },
}));

const baseRun = {
  id: 5,
  subject_id: "2",
  status: "succeeded",
  completed_scene_count: 13,
  total_scene_count: 13,
  provider: "aliyun_qwen_plus",
  model: "qwen3.7-plus",
} as Run;

function renderCard(props?: Partial<ComponentProps<typeof ReaderJourneyResumeCard>>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onStarted = vi.fn();
  const onViewScene = vi.fn();
  const onTasks = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <ReaderJourneyResumeCard
        run={baseRun}
        onStarted={onStarted}
        onViewSceneAnalysis={onViewScene}
        onViewTaskDetails={onTasks}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onStarted, onViewScene, onTasks };
}

describe("ReaderJourneyResumeCard", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.mocked(analysisApi.readerJourneyPreflight).mockResolvedValue({
      analysis_run_id: 5,
      total_scenes: 13,
      remaining_scenes: 13,
      scene_batch_count: 3,
      expected_requests: 14,
      worst_case_requests: 16,
      estimated_tokens: 120000,
      worst_case_tokens: 140000,
      estimated_cost: 1.2,
      worst_case_cost: 1.5,
      within_budget: true,
      exceeded_dimensions: [],
      provider_state_version: "v1",
      provider_name: "aliyun_qwen_plus",
      eligible: true,
      blockers: [],
      requires_cloud_consent: true,
      currency: "CNY",
    });
    vi.mocked(analysisApi.createReaderJourney).mockResolvedValue({
      journey_run_id: 99,
      status: "queued",
    });
    vi.mocked(settingsApi.cloudUsage).mockResolvedValue({
      remaining_requests: 40,
      remaining_tokens: 800000,
      remaining_estimated_cost: 12.5,
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows scene-complete copy and budget preflight before create", async () => {
    renderCard();
    expect(screen.getByTestId("reader-journey-resume-title")).toHaveTextContent(
      "Scene分析已完成",
    );
    expect(screen.getByTestId("reader-journey-resume-body").textContent).toMatch(
      /不会重新执行场景边界/,
    );
    expect(screen.queryByText("分析全部完成")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("reader-journey-resume-expected-requests")).toHaveTextContent(
        "14",
      );
    });
    expect(screen.getByTestId("reader-journey-resume-remaining-requests")).toHaveTextContent(
      "40",
    );
    expect(screen.getByTestId("reader-journey-resume-within-budget")).toHaveAttribute(
      "data-ok",
      "true",
    );
    expect(analysisApi.createReaderJourney).not.toHaveBeenCalled();
  });

  it("blocks create when reservation is insufficient", async () => {
    vi.mocked(analysisApi.readerJourneyPreflight).mockResolvedValue({
      analysis_run_id: 5,
      total_scenes: 13,
      remaining_scenes: 13,
      scene_batch_count: 3,
      expected_requests: 14,
      worst_case_requests: 16,
      estimated_tokens: 120000,
      worst_case_tokens: 140000,
      estimated_cost: 1.2,
      worst_case_cost: 1.5,
      within_budget: false,
      exceeded_dimensions: ["requests"],
      provider_state_version: "v1",
      provider_name: "aliyun_qwen_plus",
      eligible: false,
      blockers: ["INSUFFICIENT_BUDGET_RESERVATION"],
      requires_cloud_consent: true,
      currency: "CNY",
    });
    renderCard();
    await waitFor(() => {
      expect(screen.getByTestId("reader-journey-resume-budget-gap")).toBeInTheDocument();
    });
    expect(screen.getByTestId("reader-journey-resume-continue")).toBeDisabled();
    expect(analysisApi.createReaderJourney).not.toHaveBeenCalled();
  });

  it("creates one journey run with stable client_request_id (idempotent)", async () => {
    const { onStarted } = renderCard();
    await waitFor(() => {
      expect(screen.getByTestId("reader-journey-resume-continue")).not.toBeDisabled();
    });
    fireEvent.click(screen.getByTestId("reader-journey-resume-consent-input"));
    fireEvent.click(screen.getByTestId("reader-journey-resume-continue"));
    await waitFor(() => {
      expect(analysisApi.createReaderJourney).toHaveBeenCalledTimes(1);
    });
    const firstId = vi.mocked(analysisApi.createReaderJourney).mock.calls[0][1]
      .client_request_id;
    expect(sessionStorage.getItem(journeyClientRequestKey(5))).toBe(firstId);
    fireEvent.click(screen.getByTestId("reader-journey-resume-continue"));
    await waitFor(() => {
      expect(analysisApi.createReaderJourney).toHaveBeenCalledTimes(2);
    });
    expect(vi.mocked(analysisApi.createReaderJourney).mock.calls[1][1].client_request_id).toBe(
      firstId,
    );
    expect(onStarted).toHaveBeenCalledWith(99);
  });

  it("resumes existing journey run instead of creating another", async () => {
    vi.mocked(analysisApi.resumeReaderJourney).mockResolvedValue({
      journey_run_id: 7,
      status: "queued",
    });
    renderCard({ existingJourneyRunId: 7 });
    await waitFor(() => {
      expect(screen.getByTestId("reader-journey-resume-continue")).not.toBeDisabled();
    });
    fireEvent.click(screen.getByTestId("reader-journey-resume-consent-input"));
    fireEvent.click(screen.getByTestId("reader-journey-resume-continue"));
    await waitFor(() => {
      expect(analysisApi.resumeReaderJourney).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ cloud_consent: true }),
      );
    });
    expect(analysisApi.createReaderJourney).not.toHaveBeenCalled();
  });
});
