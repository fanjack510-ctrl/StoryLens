import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SceneBoundaryReviewPanel } from "./SceneBoundaryReviewPanel";
import { analysisApi } from "../../services/analysisApi";
import { booksApi } from "../../services/booksApi";

vi.mock("../../services/analysisApi", () => ({
  analysisApi: {
    sceneBoundariesOverview: vi.fn(),
    createSceneBoundaryDraft: vi.fn(),
    saveSceneBoundaryDraft: vi.fn(),
    restoreSceneBoundaryAi: vi.fn(),
    confirmSceneBoundary: vi.fn(),
    discardSceneBoundaryDraft: vi.fn(),
    sceneBoundaryDiff: vi.fn(),
  },
}));

vi.mock("../../services/booksApi", () => ({
  booksApi: {
    paragraphs: vi.fn(),
  },
}));

const MODEL_SCENES = [
  {
    scene_order: 1,
    start_paragraph_id: "P1",
    end_paragraph_id: "P2",
    included_in_journey: true,
  },
  {
    scene_order: 2,
    start_paragraph_id: "P3",
    end_paragraph_id: "P4",
    included_in_journey: true,
  },
];

const PARAGRAPHS = [
  { id: "P1", chapter_id: 2, paragraph_index: 1, raw_text: "第一段。" },
  { id: "P2", chapter_id: 2, paragraph_index: 2, raw_text: "第二段。" },
  { id: "P3", chapter_id: 2, paragraph_index: 3, raw_text: "第三段。" },
  { id: "P4", chapter_id: 2, paragraph_index: 4, raw_text: "第四段。" },
];

function overviewFixture(overrides: Record<string, unknown> = {}) {
  return {
    chapter_id: 2,
    chapter_text_hash: "hash",
    confirmed_revision: {
      revision_id: 10,
      revision_number: 1,
      status: "confirmed",
      source: "model",
      revision_etag: "etag-confirmed",
      boundary_hash: "bh",
      chapter_text_hash: "hash",
      scenes: MODEL_SCENES,
      confirmed_at: null,
    },
    draft_revision: null,
    model_revision: {
      revision_id: 9,
      revision_number: 1,
      status: "model",
      source: "model",
      revision_etag: "etag-model",
      boundary_hash: "bh",
      chapter_text_hash: "hash",
      scenes: MODEL_SCENES,
      confirmed_at: null,
    },
    awaiting_confirmation: true,
    ...overrides,
  };
}

function renderPanel(props: Partial<ComponentProps<typeof SceneBoundaryReviewPanel>> = {}) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SceneBoundaryReviewPanel
        chapterId={2}
        chapterTitle="第一章"
        {...props}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(booksApi.paragraphs).mockResolvedValue({
    items: PARAGRAPHS,
    offset: 0,
    limit: 200,
    total: 4,
    has_more: false,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("SceneBoundaryReviewPanel CHG-041", () => {
  it("renders waiting confirmation page", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(overviewFixture() as any);
    renderPanel();
    expect(await screen.findByRole("heading", { name: "确认场景划分" })).toBeInTheDocument();
    expect(screen.getByTestId("scene-boundary-waiting-lead")).toHaveTextContent("共识别 2");
  });

  it("shows adopt AI button", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(overviewFixture() as any);
    renderPanel();
    expect(await screen.findByTestId("scene-boundary-adopt-ai")).toHaveTextContent(
      "采用 AI 场景并开始旅程分析",
    );
  });

  it("opens editor and loads paragraphs", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(overviewFixture() as any);
    vi.mocked(analysisApi.createSceneBoundaryDraft).mockResolvedValue({
      revision_id: 11,
      revision_etag: "etag-draft",
      scenes: MODEL_SCENES,
    });
    renderPanel();
    fireEvent.click(await screen.findByTestId("scene-boundary-open-editor"));
    await waitFor(() => expect(analysisApi.createSceneBoundaryDraft).toHaveBeenCalledWith(2));
    expect(await screen.findByTestId("scene-boundary-editor-body")).toBeInTheDocument();
    expect(screen.getByTestId("scene-boundary-para-P1")).toHaveTextContent("第一段。");
  });

  it("moves boundary down", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(
      overviewFixture({
        draft_revision: {
          revision_id: 11,
          revision_number: 2,
          status: "draft",
          source: "user",
          revision_etag: "etag-draft",
          boundary_hash: "bh2",
          chapter_text_hash: "hash",
          scenes: MODEL_SCENES,
        },
        awaiting_confirmation: false,
      }) as any,
    );
    renderPanel();
    await screen.findByTestId("scene-boundary-divider-0");
    fireEvent.click(screen.getByTestId("scene-boundary-move-down-0"));
    expect(screen.getByTestId("scene-boundary-range-1")).toHaveTextContent("1—3");
    expect(screen.getByTestId("scene-boundary-range-2")).toHaveTextContent("4—4");
    expect(screen.getByTestId("scene-boundary-status-text")).toHaveTextContent("有未保存修改");
  });

  it("adds boundary inside a scene", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(
      overviewFixture({
        draft_revision: {
          revision_id: 11,
          revision_number: 2,
          status: "draft",
          source: "user",
          revision_etag: "etag-draft",
          boundary_hash: "bh2",
          chapter_text_hash: "hash",
          scenes: [
            {
              scene_order: 1,
              start_paragraph_id: "P1",
              end_paragraph_id: "P4",
              included_in_journey: true,
            },
          ],
        },
        awaiting_confirmation: false,
      }) as any,
    );
    renderPanel();
    fireEvent.click(await screen.findByTestId("scene-boundary-add-after-P2"));
    expect(screen.getByTestId("scene-boundary-current-count")).toHaveTextContent("当前场景数：2");
  });

  it("deletes divider by merging scenes", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(
      overviewFixture({
        draft_revision: {
          revision_id: 11,
          revision_number: 2,
          status: "draft",
          source: "user",
          revision_etag: "etag-draft",
          boundary_hash: "bh2",
          chapter_text_hash: "hash",
          scenes: MODEL_SCENES,
        },
        awaiting_confirmation: false,
      }) as any,
    );
    renderPanel();
    await screen.findByTestId("scene-boundary-divider-0");
    fireEvent.click(await screen.findByTestId("scene-boundary-delete-divider-0"));
    expect(screen.getByTestId("scene-boundary-current-count")).toHaveTextContent("当前场景数：1");
  });

  it("excludes a scene from journey", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(
      overviewFixture({
        draft_revision: {
          revision_id: 11,
          revision_number: 2,
          status: "draft",
          source: "user",
          revision_etag: "etag-draft",
          boundary_hash: "bh2",
          chapter_text_hash: "hash",
          scenes: MODEL_SCENES,
        },
        awaiting_confirmation: false,
      }) as any,
    );
    renderPanel();
    const toolbar = await screen.findByTestId("scene-boundary-toolbar-1");
    fireEvent.click(within(toolbar).getByTestId("scene-boundary-toggle-include-1"));
    expect(within(toolbar).getByTestId("scene-boundary-include-1")).not.toBeChecked();
    expect(screen.getByTestId("scene-boundary-change-summary")).toHaveTextContent("排除 1");
  });

  it("saves draft", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(
      overviewFixture({
        draft_revision: {
          revision_id: 11,
          revision_number: 2,
          status: "draft",
          source: "user",
          revision_etag: "etag-draft",
          boundary_hash: "bh2",
          chapter_text_hash: "hash",
          scenes: MODEL_SCENES,
        },
        awaiting_confirmation: false,
      }) as any,
    );
    vi.mocked(analysisApi.saveSceneBoundaryDraft).mockResolvedValue({
      revision_id: 11,
      revision_etag: "etag-saved",
      boundary_hash: "bh2",
    });
    renderPanel();
    await screen.findByTestId("scene-boundary-divider-0");
    fireEvent.click(screen.getByTestId("scene-boundary-move-down-0"));
    fireEvent.click(screen.getByTestId("scene-boundary-save-draft"));
    await waitFor(() =>
      expect(analysisApi.saveSceneBoundaryDraft).toHaveBeenCalledWith(
        2,
        11,
        expect.objectContaining({ expected_etag: "etag-draft" }),
      ),
    );
    expect(screen.getByTestId("scene-boundary-status-text")).toHaveTextContent("已保存");
  });

  it("restores AI partition", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(
      overviewFixture({
        draft_revision: {
          revision_id: 11,
          revision_number: 2,
          status: "draft",
          source: "user",
          revision_etag: "etag-draft",
          boundary_hash: "bh2",
          chapter_text_hash: "hash",
          scenes: MODEL_SCENES,
        },
        awaiting_confirmation: false,
      }) as any,
    );
    vi.mocked(analysisApi.restoreSceneBoundaryAi).mockResolvedValue({
      revision_id: 11,
      revision_etag: "etag-restored",
      scenes: MODEL_SCENES,
    });
    renderPanel();
    fireEvent.click(await screen.findByTestId("scene-boundary-restore-ai"));
    await waitFor(() => expect(analysisApi.restoreSceneBoundaryAi).toHaveBeenCalledWith(2, 11));
  });

  it("warns on leave with unsaved changes", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(
      overviewFixture({
        draft_revision: {
          revision_id: 11,
          revision_number: 2,
          status: "draft",
          source: "user",
          revision_etag: "etag-draft",
          boundary_hash: "bh2",
          chapter_text_hash: "hash",
          scenes: MODEL_SCENES,
        },
        awaiting_confirmation: false,
      }) as any,
    );
    const onExit = vi.fn();
    renderPanel({ onExit });
    await screen.findByTestId("scene-boundary-divider-0");
    fireEvent.click(screen.getByTestId("scene-boundary-move-down-0"));
    fireEvent.click(screen.getByTestId("scene-boundary-exit"));
    expect(confirmSpy).toHaveBeenCalled();
    expect(onExit).not.toHaveBeenCalled();
  });

  it("confirms and starts journey", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(
      overviewFixture({
        draft_revision: {
          revision_id: 11,
          revision_number: 2,
          status: "draft",
          source: "user",
          revision_etag: "etag-draft",
          boundary_hash: "bh2",
          chapter_text_hash: "hash",
          scenes: MODEL_SCENES,
        },
        awaiting_confirmation: false,
      }) as any,
    );
    vi.mocked(analysisApi.confirmSceneBoundary).mockResolvedValue({
      revision_id: 11,
      revision_etag: "etag-final",
      boundary_hash: "bh2",
      journey_run_id: 99,
      journey_started: true,
    });
    const onConfirmed = vi.fn();
    renderPanel({ onConfirmed });
    await screen.findByTestId("scene-boundary-confirm-start");
    fireEvent.click(screen.getByTestId("scene-boundary-confirm-start"));
    await waitFor(() =>
      expect(analysisApi.confirmSceneBoundary).toHaveBeenCalledWith(
        2,
        11,
        expect.objectContaining({ start_journey: true }),
      ),
    );
    expect(onConfirmed).toHaveBeenCalledWith(
      expect.objectContaining({ journeyStarted: true, journeyRunId: 99 }),
    );
  });

  it("shows readonly message when journey is running", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(overviewFixture() as any);
    renderPanel({ journeyRunning: true });
    expect(await screen.findByTestId("scene-boundary-journey-running")).toHaveTextContent(
      "暂不可编辑",
    );
    expect(screen.queryByTestId("scene-boundary-adopt-ai")).not.toBeInTheDocument();
  });

  it("shows stale journey banner", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(overviewFixture() as any);
    renderPanel({ journeyRevisionId: 7 });
    expect(await screen.findByTestId("scene-boundary-stale-journey")).toHaveTextContent(
      "较早的场景划分",
    );
  });

  it("does not offer delete-text action", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(
      overviewFixture({
        draft_revision: {
          revision_id: 11,
          revision_number: 2,
          status: "draft",
          source: "user",
          revision_etag: "etag-draft",
          boundary_hash: "bh2",
          chapter_text_hash: "hash",
          scenes: MODEL_SCENES,
        },
        awaiting_confirmation: false,
      }) as any,
    );
    renderPanel();
    await screen.findByTestId("scene-boundary-editor-body");
    expect(screen.queryByText(/删除段落/)).not.toBeInTheDocument();
    expect(screen.queryByText(/删除正文/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /删除文本/ })).not.toBeInTheDocument();
  });
});
