import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConfirmBoundaryDivisionPanel } from "./ConfirmBoundaryDivisionPanel";
import { analysisApi } from "../../services/analysisApi";

vi.mock("../../services/analysisApi", () => ({
  analysisApi: {
    boundaryReview: vi.fn(),
    finalBoundaryProposal: vi.fn(),
    confirmFinalBoundaryProposal: vi.fn(),
    cancelBoundaryReview: vi.fn(),
  },
}));

vi.mock("../../services/boundaryReviewMode", () => ({
  getBoundaryReviewMode: () => "confirm_only",
  isConfirmOnlyBoundaryReview: () => true,
}));

function renderPanel() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ConfirmBoundaryDivisionPanel bookId={1} chapterId={2} chapterTitle="第一章｜开端" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ConfirmBoundaryDivisionPanel", () => {
  it("shows confirm-only copy without legacy candidate controls", async () => {
    vi.mocked(analysisApi.boundaryReview).mockResolvedValue({
      id: 9,
      analysis_run_id: 8,
      status: "pending",
      paragraphs: [
        { id: "P1", paragraph_index: 1, raw_text: "第一段。" },
        { id: "P2", paragraph_index: 2, raw_text: "第二段。" },
        { id: "P3", paragraph_index: 3, raw_text: "第三段。" },
      ],
    } as any);
    vi.mocked(analysisApi.finalBoundaryProposal).mockResolvedValue({
      review_id: 9,
      analysis_run_id: 8,
      chapter_id: 2,
      validation_status: "valid",
      proposal_fingerprint: "abc12345fingerprint",
      scene_count: 2,
      paragraph_count: 3,
      chapter_title: "第一章｜开端",
      final_scene_ranges: [
        {
          ordinal: 1,
          start_paragraph_id: "P1",
          end_paragraph_id: "P1",
          start_paragraph_index: 1,
          end_paragraph_index: 1,
          paragraph_ids: ["P1"],
        },
        {
          ordinal: 2,
          start_paragraph_id: "P2",
          end_paragraph_id: "P3",
          start_paragraph_index: 2,
          end_paragraph_index: 3,
          paragraph_ids: ["P2", "P3"],
        },
      ],
      paragraphs: [
        { id: "P1", paragraph_index: 1, raw_text: "第一段。" },
        { id: "P2", paragraph_index: 2, raw_text: "第二段。" },
        { id: "P3", paragraph_index: 3, raw_text: "第三段。" },
      ],
      source_summary: {},
    } as any);

    renderPanel();
    expect(await screen.findByRole("heading", { name: "确认场景划分" })).toBeInTheDocument();
    expect(screen.getByTestId("confirm-boundary-scene-count")).toHaveTextContent("建议场景数：2");
    expect(screen.getByTestId("confirm-boundary-divider")).toHaveTextContent("场景分隔");
    expect(screen.getByTestId("confirm-boundary-submit")).toHaveTextContent("确认边界并继续");
    expect(screen.queryByText("接受边界")).not.toBeInTheDocument();
    expect(screen.queryByText("拒绝边界")).not.toBeInTheDocument();
    expect(screen.queryByText("保持待处理")).not.toBeInTheDocument();
    expect(screen.queryByText("接受全部非冲突项")).not.toBeInTheDocument();
    expect(screen.queryByText("完成审阅")).not.toBeInTheDocument();
    expect(screen.queryByText(/候选边界/)).not.toBeInTheDocument();
    expect(screen.queryByText(/冲突/)).not.toBeInTheDocument();
  });

  it("locks duplicate confirm clicks to one request", async () => {
    vi.mocked(analysisApi.boundaryReview).mockResolvedValue({
      id: 9,
      analysis_run_id: 8,
      status: "pending",
      paragraphs: [],
    } as any);
    vi.mocked(analysisApi.finalBoundaryProposal).mockResolvedValue({
      review_id: 9,
      analysis_run_id: 8,
      chapter_id: 2,
      validation_status: "valid",
      proposal_fingerprint: "abc12345fingerprint",
      scene_count: 1,
      paragraph_count: 1,
      final_scene_ranges: [
        {
          ordinal: 1,
          start_paragraph_id: "P1",
          end_paragraph_id: "P1",
          start_paragraph_index: 1,
          end_paragraph_index: 1,
          paragraph_ids: ["P1"],
        },
      ],
      paragraphs: [{ id: "P1", paragraph_index: 1, raw_text: "一段。" }],
      source_summary: {},
    } as any);
    let resolveConfirm: (v: unknown) => void = () => undefined;
    vi.mocked(analysisApi.confirmFinalBoundaryProposal).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveConfirm = resolve;
        }),
    );

    renderPanel();
    const button = await screen.findByTestId("confirm-boundary-submit");
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(analysisApi.confirmFinalBoundaryProposal).toHaveBeenCalledTimes(1));
    expect(button).toHaveTextContent("正在确认…");
    resolveConfirm({
      revision_id: 1,
      revision_number: 1,
      scene_count: 1,
      coverage_rate: 1,
      run_status: "scene_analysis_running",
      scene_analysis_started: true,
      budget_blocked: false,
    });
  });
});
