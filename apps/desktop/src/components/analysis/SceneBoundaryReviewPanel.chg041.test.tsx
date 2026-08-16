import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SceneBoundaryReviewPanel } from "./SceneBoundaryReviewPanel";
import { analysisApi } from "../../services/analysisApi";
import { booksApi } from "../../services/booksApi";
import { ApiError } from "../../services/apiClient";
import { mapSceneBoundaryError } from "../../services/sceneBoundaryErrors";

vi.mock("../../services/analysisApi", () => ({
  analysisApi: {
    sceneBoundariesOverview: vi.fn(),
    createSceneBoundaryDraft: vi.fn(),
    saveSceneBoundaryDraft: vi.fn(),
    splitSceneBoundaryDraft: vi.fn(),
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

function draftOverview(etag = "etag-A", scenes = MODEL_SCENES) {
  return overviewFixture({
    draft_revision: {
      revision_id: 11,
      revision_number: 2,
      status: "draft",
      source: "user",
      revision_etag: etag,
      boundary_hash: "bh2",
      chapter_text_hash: "hash",
      scenes,
    },
    awaiting_confirmation: false,
  });
}

function renderPanel(props: Partial<ComponentProps<typeof SceneBoundaryReviewPanel>> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SceneBoundaryReviewPanel chapterId={2} chapterTitle="第二章" {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(booksApi.paragraphs).mockResolvedValue({
    items: PARAGRAPHS as any,
    offset: 0,
    limit: 200,
    has_more: false,
  });
  vi.mocked(analysisApi.saveSceneBoundaryDraft).mockImplementation(async (_c, _r, body) => ({
    revision_id: 11,
    revision_etag: `next-of-${body.expected_etag}`,
    boundary_hash: "bh2",
    scenes: body.scenes,
    status: "draft",
  }));
  vi.mocked(analysisApi.splitSceneBoundaryDraft).mockImplementation(async (_c, _r, body) => {
    const { addSceneBoundary } = await import("../../services/sceneBoundaryPartitionOps");
    const overview = await vi.mocked(analysisApi.sceneBoundariesOverview).getMockImplementation()?.(2);
    const currentScenes =
      (overview as any)?.draft_revision?.scenes ||
      MODEL_SCENES;
    // Prefer last saved scenes from save mock chain if present via body scene_order path.
    const paragraphIds = PARAGRAPHS.map((p) => p.id);
    // Reconstruct from draft overview etag chain is hard; use MODEL_SCENES as base then split.
    let base = currentScenes.map((s: any) => ({ ...s }));
    // If already more scenes from prior ops, try reading from last save call.
    const saveCalls = vi.mocked(analysisApi.saveSceneBoundaryDraft).mock.calls;
    if (saveCalls.length > 0) {
      const last = saveCalls[saveCalls.length - 1]?.[2] as { scenes?: typeof MODEL_SCENES };
      if (last?.scenes?.length) base = last.scenes.map((s) => ({ ...s }));
    }
    const scenes = addSceneBoundary(base, body.boundary_after_paragraph_id, paragraphIds);
    return {
      revision_id: 11,
      revision_etag: `next-of-${body.expected_etag}`,
      boundary_hash: "bh-split",
      scenes,
      already_split: false,
      status: "draft",
      diff_summary: { scene_count_delta: 1, changes: [] },
    };
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
    expect(screen.getByTestId("scene-boundary-waiting-lead")).toHaveTextContent("共 2 个场景");
  });

  it("lists the proposed scenes so there is something to confirm", async () => {
    // The screen used to ask for a yes on a bare count. Nobody can confirm a division they
    // cannot see, so each proposed scene shows its paragraph range and its opening line.
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(overviewFixture() as any);
    renderPanel();
    const preview = await screen.findByTestId("scene-boundary-preview");
    expect(preview.querySelectorAll("li")).toHaveLength(2);
    await waitFor(() => expect(preview).toHaveTextContent("第一段。"));
  });

  it("shows adopt AI button", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(overviewFixture() as any);
    renderPanel();
    expect(await screen.findByTestId("scene-boundary-adopt-ai")).toHaveTextContent(
      "确认这 2 个场景并开始分析",
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

  it("moves boundary down and persists with etag chain", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(draftOverview("etag-A") as any);
    renderPanel();
    await screen.findByTestId("scene-boundary-divider-0");
    fireEvent.click(screen.getByTestId("scene-boundary-move-down-0"));
    expect(screen.getByTestId("scene-boundary-range-1")).toHaveTextContent("1—3");
    await waitFor(() =>
      expect(analysisApi.saveSceneBoundaryDraft).toHaveBeenCalledWith(
        2,
        11,
        expect.objectContaining({ expected_etag: "etag-A" }),
      ),
    );
    await waitFor(() =>
      expect(screen.getByTestId("scene-boundary-status-text")).toHaveTextContent("已保存"),
    );
    expect(screen.getByTestId("scene-boundary-etag")).toHaveAttribute(
      "data-revision-etag",
      "next-of-etag-A",
    );
  });

  it("chains etags across consecutive mutations then confirms with latest", async () => {
    let call = 0;
    const etags = ["etag-A", "etag-B", "etag-C", "etag-D", "etag-E", "etag-F"];
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(draftOverview(etags[0]) as any);
    vi.mocked(analysisApi.saveSceneBoundaryDraft).mockImplementation(async (_c, _r, body) => {
      expect(body.expected_etag).toBe(etags[call]);
      call += 1;
      return {
        revision_id: 11,
        revision_etag: etags[call],
        boundary_hash: "bh2",
        scenes: body.scenes,
        status: "draft",
      };
    });
    vi.mocked(analysisApi.splitSceneBoundaryDraft).mockImplementation(async (_c, _r, body) => {
      expect(body.expected_etag).toBe(etags[call]);
      const { addSceneBoundary } = await import("../../services/sceneBoundaryPartitionOps");
      const saveCalls = vi.mocked(analysisApi.saveSceneBoundaryDraft).mock.calls;
      const last = saveCalls[saveCalls.length - 1]?.[2] as { scenes?: typeof MODEL_SCENES };
      const base = (last?.scenes || MODEL_SCENES).map((s) => ({ ...s }));
      const scenes = addSceneBoundary(
        base,
        body.boundary_after_paragraph_id,
        PARAGRAPHS.map((p) => p.id),
      );
      call += 1;
      return {
        revision_id: 11,
        revision_etag: etags[call],
        boundary_hash: "bh-split",
        scenes,
        already_split: false,
        status: "draft",
      };
    });
    vi.mocked(analysisApi.confirmSceneBoundary).mockResolvedValue({
      revision_id: 11,
      revision_etag: "etag-final",
      boundary_hash: "bh2",
      journey_run_id: null,
      journey_started: false,
    });
    renderPanel();
    await screen.findByTestId("scene-boundary-divider-0");
    fireEvent.click(screen.getByTestId("scene-boundary-move-down-0"));
    await waitFor(() => expect(call).toBe(1));
    fireEvent.click(screen.getByTestId("scene-boundary-move-up-0"));
    await waitFor(() => expect(call).toBe(2));
    fireEvent.click(screen.getByTestId("scene-boundary-delete-divider-0"));
    await waitFor(() => expect(call).toBe(3));
    fireEvent.click(await screen.findByTestId("scene-boundary-add-after-P2"));
    await waitFor(() => expect(call).toBe(4));
    expect(await screen.findByTestId("scene-boundary-success")).toHaveTextContent("已新增一个场景");
    const toolbar = screen.getByTestId("scene-boundary-toolbar-1");
    fireEvent.click(within(toolbar).getByTestId("scene-boundary-toggle-include-1"));
    await waitFor(() => expect(call).toBe(5));
    fireEvent.click(screen.getByTestId("scene-boundary-confirm"));
    await waitFor(() =>
      expect(analysisApi.confirmSceneBoundary).toHaveBeenCalledWith(
        2,
        11,
        expect.objectContaining({ expected_etag: "etag-F", start_journey: false }),
      ),
    );
    expect(await screen.findByTestId("scene-boundary-success")).toHaveTextContent("场景划分已确认");
    expect(screen.getByTestId("scene-boundary-confirmed-readonly")).toBeInTheDocument();
    expect(screen.queryByText("SCENE_REVISION_CONCURRENT_MODIFICATION")).not.toBeInTheDocument();
    expect(screen.getByTestId("scene-boundary-start-journey")).toHaveTextContent("生成阅读旅程");
    expect(screen.queryByTestId("scene-boundary-retry-journey")).not.toBeInTheDocument();
  });

  it("blocks duplicate confirm while pending and shows loading", async () => {
    let resolveConfirm: (v: any) => void = () => undefined;
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(draftOverview() as any);
    vi.mocked(analysisApi.confirmSceneBoundary).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveConfirm = resolve;
        }),
    );
    renderPanel();
    await screen.findByTestId("scene-boundary-confirm");
    fireEvent.click(screen.getByTestId("scene-boundary-confirm"));
    expect(await screen.findByTestId("scene-boundary-confirm")).toHaveTextContent("确认中");
    fireEvent.click(screen.getByTestId("scene-boundary-confirm"));
    fireEvent.click(screen.getByTestId("scene-boundary-confirm-start"));
    expect(analysisApi.confirmSceneBoundary).toHaveBeenCalledTimes(1);
    resolveConfirm({
      revision_id: 11,
      revision_etag: "etag-final",
      boundary_hash: "bh2",
      journey_run_id: null,
      journey_started: false,
    });
    expect(await screen.findByTestId("scene-boundary-success")).toBeInTheDocument();
  });

  it("shows conflict dialog on 409 without raw code in primary UI", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(draftOverview() as any);
    vi.mocked(analysisApi.saveSceneBoundaryDraft).mockRejectedValue(
      new ApiError(
        "SCENE_REVISION_CONCURRENT_MODIFICATION",
        "SCENE_REVISION_CONCURRENT_MODIFICATION",
        409,
        { error_code: "SCENE_REVISION_CONCURRENT_MODIFICATION" },
      ),
    );
    renderPanel();
    await screen.findByTestId("scene-boundary-divider-0");
    fireEvent.click(screen.getByTestId("scene-boundary-move-down-0"));
    expect(await screen.findByTestId("scene-boundary-conflict-dialog")).toHaveTextContent(
      "场景草稿已更新",
    );
    expect(screen.getByTestId("scene-boundary-conflict-reload")).toBeInTheDocument();
    expect(screen.getByTestId("scene-boundary-conflict-keep")).toBeInTheDocument();
    expect(screen.queryByTestId("scene-boundary-error")).not.toBeInTheDocument();
    expect(screen.getByTestId("scene-boundary-error-tech")).toHaveTextContent(
      "SCENE_REVISION_CONCURRENT_MODIFICATION",
    );
  });

  it("maps conflict error for user message helper", () => {
    const mapped = mapSceneBoundaryError(
      new ApiError("SCENE_REVISION_CONCURRENT_MODIFICATION", "raw", 409, {}),
    );
    expect(mapped.isConflict).toBe(true);
    expect(mapped.userMessage).not.toContain("SCENE_REVISION");
  });

  it("adds boundary inside a scene", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(
      draftOverview("etag-A", [
        {
          scene_order: 1,
          start_paragraph_id: "P1",
          end_paragraph_id: "P4",
          included_in_journey: true,
        },
      ]) as any,
    );
    renderPanel();
    fireEvent.click(await screen.findByTestId("scene-boundary-add-after-P2"));
    await waitFor(() =>
      expect(screen.getByTestId("scene-boundary-current-count")).toHaveTextContent("当前场景数：2"),
    );
    expect(await screen.findByTestId("scene-boundary-success")).toHaveTextContent("已新增一个场景");
    expect(screen.getAllByText("＋ 在此拆分为新场景").length).toBeGreaterThan(0);
  });

  it("hides add control for single-paragraph scenes and existing boundaries", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(
      draftOverview("etag-A", [
        {
          scene_order: 1,
          start_paragraph_id: "P1",
          end_paragraph_id: "P1",
          included_in_journey: true,
        },
        {
          scene_order: 2,
          start_paragraph_id: "P2",
          end_paragraph_id: "P4",
          included_in_journey: true,
        },
      ]) as any,
    );
    renderPanel();
    await screen.findByTestId("scene-boundary-divider-0");
    expect(screen.queryByTestId("scene-boundary-add-after-P1")).not.toBeInTheDocument();
    expect(screen.getByTestId("scene-boundary-add-after-P2")).toBeInTheDocument();
    expect(screen.getByTestId("scene-boundary-add-after-P3")).toBeInTheDocument();
  });

  it("deletes divider by merging scenes", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(draftOverview() as any);
    renderPanel();
    await screen.findByTestId("scene-boundary-divider-0");
    fireEvent.click(await screen.findByTestId("scene-boundary-delete-divider-0"));
    expect(screen.getByTestId("scene-boundary-current-count")).toHaveTextContent("当前场景数：1");
  });

  it("excludes a scene from journey", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(draftOverview() as any);
    renderPanel();
    const toolbar = await screen.findByTestId("scene-boundary-toolbar-1");
    fireEvent.click(within(toolbar).getByTestId("scene-boundary-toggle-include-1"));
    await waitFor(() =>
      expect(screen.getByTestId("scene-boundary-change-summary")).toHaveTextContent("排除 1"),
    );
  });

  it("restores AI partition", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(draftOverview() as any);
    vi.mocked(analysisApi.restoreSceneBoundaryAi).mockResolvedValue({
      revision_id: 11,
      revision_etag: "etag-restored",
      scenes: MODEL_SCENES,
    });
    renderPanel();
    fireEvent.click(await screen.findByTestId("scene-boundary-restore-ai"));
    await waitFor(() => expect(analysisApi.restoreSceneBoundaryAi).toHaveBeenCalledWith(2, 11));
  });

  it("warns on leave while persist still dirty", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(draftOverview() as any);
    vi.mocked(analysisApi.saveSceneBoundaryDraft).mockImplementation(
      () => new Promise(() => undefined),
    );
    const onExit = vi.fn();
    renderPanel({ onExit });
    await screen.findByTestId("scene-boundary-divider-0");
    fireEvent.click(screen.getByTestId("scene-boundary-move-down-0"));
    fireEvent.click(screen.getByTestId("scene-boundary-exit"));
    expect(confirmSpy).toHaveBeenCalled();
    expect(onExit).not.toHaveBeenCalled();
  });

  it("confirms and starts journey then leaves editable mode", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(draftOverview() as any);
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
        expect.objectContaining({ start_journey: true, expected_etag: "etag-A" }),
      ),
    );
    expect(onConfirmed).toHaveBeenCalledWith(
      expect.objectContaining({ journeyStarted: true, journeyRunId: 99 }),
    );
    expect(screen.queryByTestId("scene-boundary-editor-body")).not.toBeInTheDocument();
  });

  it("keeps confirmed revision when journey start fails with single retry CTA", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(draftOverview() as any);
    vi.mocked(analysisApi.confirmSceneBoundary).mockResolvedValue({
      revision_id: 11,
      revision_etag: "etag-final",
      boundary_hash: "bh2",
      journey_run_id: null,
      journey_started: false,
      journey_error_code: "SCENE_CONFIRMED_JOURNEY_NOT_STARTED",
      journey_error_message: "阅读旅程任务未能启动。",
    });
    renderPanel();
    fireEvent.click(await screen.findByTestId("scene-boundary-confirm-start"));
    expect(await screen.findByTestId("scene-boundary-journey-failed")).toHaveTextContent(
      "阅读旅程任务未能启动",
    );
    expect(screen.getByTestId("scene-boundary-retry-journey")).toHaveTextContent(
      "重新尝试生成阅读旅程",
    );
    expect(screen.queryByTestId("scene-boundary-start-journey")).not.toBeInTheDocument();
  });

  it("uses frozen button labels", async () => {
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(draftOverview() as any);
    renderPanel();
    expect(await screen.findByTestId("scene-boundary-confirm")).toHaveTextContent("仅确认场景划分");
    expect(screen.getByTestId("scene-boundary-confirm-start")).toHaveTextContent(
      "确认这 2 个场景并开始分析",
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
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue(draftOverview() as any);
    renderPanel();
    await screen.findByTestId("scene-boundary-editor-body");
    expect(screen.queryByText("删除段落文字")).not.toBeInTheDocument();
    expect(screen.queryByText("删除正文")).not.toBeInTheDocument();
  });
});
