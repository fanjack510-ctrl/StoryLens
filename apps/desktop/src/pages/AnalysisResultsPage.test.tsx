import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AnalysisResultsPage } from "./AnalysisResultsPage";
import { analysisApi } from "../services/analysisApi";

vi.mock("../services/analysisApi", () => ({
  analysisApi: {
    results: vi.fn(),
    sceneParagraphs: vi.fn(),
    readerJourney: vi.fn().mockResolvedValue(null),
    readerJourneyPreflight: vi.fn(),
    createReaderJourney: vi.fn(),
    readerJourneyProgress: vi.fn(),
    resumeReaderJourney: vi.fn(),
    offlineReplayReaderJourney: vi.fn(),
    resultsExportUrl: vi.fn(
      (runId: number, format: string) =>
        `http://api/api/v1/analysis-runs/${runId}/results/export?format=${format}`,
    ),
  },
}));

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
});

function makeScene(ordinal: number, opts: Partial<any> = {}) {
  const start = `B0001-C0002-P${String(ordinal * 10).padStart(4, "0")}`;
  const end = opts.single ? start : `B0001-C0002-P${String(ordinal * 10 + 2).padStart(4, "0")}`;
  return {
    scene: {
      id: ordinal,
      scene_key: `B0001-C0002-R0001-S${String(ordinal).padStart(4, "0")}`,
      ordinal,
      start_paragraph_id: start,
      end_paragraph_id: end,
      paragraph_count: opts.single ? 1 : 3,
      is_single_paragraph: !!opts.single,
      boundary_source: opts.boundary_source ?? "model_accepted",
      boundary_revision_id: 1,
      boundary_detected: true,
      boundary_confidence: 0.9,
    },
    analysis_artifact: {
      id: 100 + ordinal,
      schema_version: "v1",
      prompt_version: "v3.1",
      provider: "aliyun_qwen_plus",
      model: "qwen3.7-plus",
      confidence: 0.8,
      validation_status: "valid",
      created_at: "2026-07-17T07:00:00Z",
      offline_recovered: !!opts.offline,
      analysis: {
        scene_id: `B0001-C0002-R0001-S${String(ordinal).padStart(4, "0")}`,
        entry_state: { summary: `进入-${ordinal}`, evidence_paragraph_ids: [start] },
        goal: { summary: `目标-${ordinal}`, evidence_paragraph_ids: [start] },
        obstacle: { summary: "", evidence_paragraph_ids: [] },
        key_actions: [{ summary: `动作-${ordinal}`, evidence_paragraph_ids: [start] }],
        turning_point: { summary: "", evidence_paragraph_ids: [] },
        outcome: { summary: `结果-${ordinal}`, evidence_paragraph_ids: [end] },
        unresolved_question: { summary: "", evidence_paragraph_ids: [] },
        function_tags: ["事件推进"],
        confidence: 0.8,
      },
    },
    evidence: [
      { field_path: "entry_state.evidence", group: "entry_state", paragraph_id: start, in_scope: true, order_index: ordinal * 10 },
      { field_path: "goal.evidence", group: "goal", paragraph_id: start, in_scope: true, order_index: ordinal * 10 },
      { field_path: "outcome.evidence", group: "outcome", paragraph_id: end, in_scope: true, order_index: ordinal * 10 + 2 },
    ],
    illegal_evidence: [],
    revision: null,
  };
}

const results = {
  run: {
    id: 55,
    status: "succeeded",
    provider: "aliyun_qwen_plus",
    model: "qwen3.7-plus",
    prompt_version: "v3.5",
    schema_version: "v1",
    analysis_mode: "assisted_boundary_review",
    execution_mode: "cloud",
    completed_at: "2026-07-17T07:10:00Z",
  },
  chapter: { id: 2, book_id: 1, chapter_index: 2, title: "第1章 戏鬼回家", display_title: "第1章 戏鬼回家" },
  boundary_revision: { id: 1, revision_number: 1, coverage_rate: 1.0, confirmed_by: "desktop-user", confirmed_at: "2026-07-17T06:00:00Z" },
  summary: {
    total_scene_count: 14,
    coverage_rate: 1.0,
    single_paragraph_scene_count: 4,
    longest_scene_ordinal: 9,
    longest_scene_paragraph_count: 16,
    manual_added_boundary_count: 3,
    model_accepted_boundary_count: 7,
    user_accepted_conflict_count: 3,
    artifact_coverage_rate: 1.0,
    evidence_coverage_rate: 1.0,
    offline_recovered_scene_count: 2,
  },
  scenes: Array.from({ length: 14 }, (_, index) =>
    makeScene(index + 1, {
      single: [3, 5, 6, 13].includes(index + 1),
      offline: [5, 13].includes(index + 1),
    }),
  ),
};

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/analysis-runs/55/results"]}>
        <Routes>
          <Route path="/analysis-runs/:runId/results" element={<AnalysisResultsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockParagraphs(sceneId: number) {
  const scene = results.scenes.find((s) => s.scene.id === sceneId)!.scene;
  return {
    scene_id: sceneId,
    scene_key: scene.scene_key,
    ordinal: scene.ordinal,
    start_paragraph_id: scene.start_paragraph_id,
    end_paragraph_id: scene.end_paragraph_id,
    paragraphs: [
      { id: scene.start_paragraph_id, paragraph_index: scene.ordinal * 10, raw_text: `正文${scene.ordinal}`, in_scene: true },
      { id: scene.end_paragraph_id, paragraph_index: scene.ordinal * 10 + 2, raw_text: `尾段${scene.ordinal}`, in_scene: true },
    ],
  };
}

describe("AnalysisResultsPage", () => {
  beforeEach(() => {
    vi.mocked(analysisApi.results).mockResolvedValue(results as any);
    vi.mocked(analysisApi.sceneParagraphs).mockImplementation((id: any) =>
      Promise.resolve(mockParagraphs(Number(id)) as any),
    );
  });

  it("自动选中Scene 01并显示14项场景列表", async () => {
    renderPage();
    expect(await screen.findByTestId("results-header")).toHaveTextContent(
      "分析结果：Run #55 · 14个Scene",
    );
    for (let ordinal = 1; ordinal <= 14; ordinal += 1) {
      expect(screen.getByTestId(`scene-list-item-${ordinal}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("scene-list-item-1").className).toContain("selected");
    expect(await screen.findByTestId("structure-field-goal")).toHaveTextContent("目标-1");
  });

  it("切换Scene会加载对应正文与结构", async () => {
    renderPage();
    await screen.findByTestId("structure-field-goal");
    fireEvent.click(screen.getByTestId("scene-list-item-5"));
    await waitFor(() =>
      expect(screen.getByTestId("structure-field-goal")).toHaveTextContent("目标-5"),
    );
    await waitFor(() => expect(analysisApi.sceneParagraphs).toHaveBeenCalledWith(5));
  });

  it("点击Evidence高亮对应段落", async () => {
    renderPage();
    await screen.findByTestId("structure-field-goal");
    fireEvent.click(screen.getByTestId("tab-evidence"));
    const start = results.scenes[0].scene.start_paragraph_id;
    const items = await screen.findAllByTestId(`evidence-item-${start}`);
    fireEvent.click(items[0]);
    await waitFor(() =>
      expect(screen.getByTestId(`paragraph-${start}`).className).toContain("highlight"),
    );
  });

  it("历史页显示离线恢复标记", async () => {
    renderPage();
    await screen.findByTestId("structure-field-goal");
    fireEvent.click(screen.getByTestId("scene-list-item-5"));
    fireEvent.click(screen.getByTestId("tab-history"));
    expect(await screen.findByTestId("history-panel")).toHaveTextContent("离线恢复");
  });

  it("整章概览显示统计与14个Scene", async () => {
    renderPage();
    await screen.findByTestId("structure-field-goal");
    fireEvent.click(screen.getByTestId("tab-overview"));
    const panel = await screen.findByTestId("overview-panel");
    expect(panel).toHaveTextContent("Scene总数");
    for (let ordinal = 1; ordinal <= 14; ordinal += 1) {
      expect(screen.getByTestId(`overview-scene-${ordinal}`)).toBeInTheDocument();
    }
  });

  it("导出按钮触发下载", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ blob: () => Promise.resolve(new Blob(["x"])) });
    vi.stubGlobal("fetch", fetchMock);
    const createObjectURL = vi.fn(() => "blob:url");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL } as any);
    renderPage();
    await screen.findByTestId("structure-field-goal");
    fireEvent.click(screen.getByTestId("export-markdown"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toContain("format=markdown");
    vi.unstubAllGlobals();
  });

  it("读者旅程失败态显示截断错误且盲目恢复按钮禁用", async () => {
    vi.mocked(analysisApi.readerJourneyPreflight).mockResolvedValue({
      analysis_run_id: 55,
      total_scenes: 14,
      remaining_scenes: 14,
      scene_batch_count: 7,
      expected_requests: 8,
      worst_case_requests: 20,
      estimated_tokens: 12000,
      worst_case_tokens: 24000,
      estimated_cost: 0.1,
      worst_case_cost: 0.2,
      within_budget: true,
      exceeded_dimensions: [],
      provider_state_version: "test",
      provider_name: "fake",
      eligible: true,
      blockers: [],
      requires_cloud_consent: false,
      currency: "CNY",
    } as any);
    vi.mocked(analysisApi.createReaderJourney).mockResolvedValue({
      journey_run_id: 902,
      status: "failed",
      idempotent_replay: true,
      existing_journey_run_id: 902,
      creation_blocked_reason: "ACTIVE_OR_RECOVERABLE_JOURNEY_EXISTS",
    } as any);
    vi.mocked(analysisApi.offlineReplayReaderJourney).mockResolvedValue({
      journey_run_id: 902,
      replayed_scene_ids: [1],
      completed_count: 1,
      remaining_count: 13,
      source_invocation_ids: [134],
      migrated_from_contract_version: "1.1",
      current_contract_version: "1.2",
      http_requests: 0,
      tokens: 0,
      cost: 0,
      idempotent_replay: false,
    } as any);
    vi.mocked(analysisApi.readerJourneyProgress).mockResolvedValue({
      journey_run_id: 902,
      analysis_run_id: 55,
      status: "failed",
      total_scene_count: 14,
      completed_scene_count: 0,
      remaining_scene_count: 14,
      phase_count: 0,
      has_chapter_summary: false,
      retryable: false,
      root_error_code: "OUTPUT_TRUNCATED",
      user_error_message: "模型输出达到上限，当前批次未形成有效JSON",
      blind_resume_blocked: true,
      resume_block_reason: "planner_outdated",
      recovery_safe: false,
      failed_stage: "reader_journey_scene_profiles",
      request_count: 2,
      total_tokens: 1000,
      estimated_cost: 0.02,
      currency: "CNY",
      reservation_released: true,
    } as any);

    renderPage();
    await screen.findByTestId("structure-field-goal");
    fireEvent.click(screen.getByTestId("generate-reader-journey"));
    await waitFor(() => expect(screen.getByTestId("journey-preflight")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("journey-cloud-consent"));
    fireEvent.click(screen.getByTestId("start-reader-journey"));
    fireEvent.click(screen.getByTestId("tab-journey"));

    const failed = await screen.findByTestId("journey-failed");
    expect(failed).toHaveTextContent("模型输出达到上限，当前批次未形成有效JSON");
    const resume = screen.getByTestId("resume-reader-journey");
    expect(resume).toBeDisabled();
    expect(resume).toHaveTextContent("请升级批次规划后恢复");
  });

  it("旧契约失败时显示离线重放并禁用付费恢复", async () => {
    vi.mocked(analysisApi.readerJourneyPreflight).mockResolvedValue({
      analysis_run_id: 55,
      total_scenes: 14,
      remaining_scenes: 14,
      scene_batch_count: 7,
      expected_requests: 8,
      worst_case_requests: 20,
      estimated_tokens: 12000,
      worst_case_tokens: 24000,
      estimated_cost: 0.1,
      worst_case_cost: 0.2,
      within_budget: true,
      exceeded_dimensions: [],
      provider_state_version: "test",
      provider_name: "fake",
      eligible: true,
      blockers: [],
      requires_cloud_consent: false,
      currency: "CNY",
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      journey_run_id: 902,
      status: "failed",
    } as any);
    vi.mocked(analysisApi.readerJourneyProgress).mockResolvedValue({
      journey_run_id: 902,
      analysis_run_id: 55,
      status: "failed",
      total_scene_count: 14,
      completed_scene_count: 0,
      remaining_scene_count: 14,
      phase_count: 0,
      has_chapter_summary: false,
      retryable: false,
      root_error_code: "JOURNEY_QUESTION_CHAIN_INVALID",
      user_error_message: "旧版契约要求 reader_question_in 非空；请使用离线重放",
      offline_replay_available: true,
      offline_replayable_scene_count: 1,
      offline_replayable_invocation_ids: [134],
      current_contract_version: "1.2",
      blind_resume_blocked: true,
      resume_block_reason: "offline_replay_required",
      recovery_safe: false,
      failed_stage: "reader_journey_scene_profiles",
      reservation_released: true,
    } as any);
    vi.mocked(analysisApi.offlineReplayReaderJourney).mockResolvedValue({
      journey_run_id: 902,
      replayed_scene_ids: [1],
      completed_count: 1,
      remaining_count: 13,
      source_invocation_ids: [134],
      migrated_from_contract_version: "1.1",
      current_contract_version: "1.2",
      http_requests: 0,
      tokens: 0,
      cost: 0,
      idempotent_replay: false,
    } as any);

    renderPage();
    await screen.findByTestId("structure-field-goal");
    fireEvent.click(screen.getByTestId("tab-journey"));
    expect(await screen.findByTestId("journey-old-contract-notice")).toBeInTheDocument();
    expect(screen.getByTestId("resume-reader-journey")).toBeDisabled();
    fireEvent.click(screen.getByTestId("offline-replay-reader-journey"));
    await waitFor(() =>
      expect(screen.getByTestId("journey-offline-replay-success")).toHaveTextContent("离线重放成功"),
    );
    expect(analysisApi.offlineReplayReaderJourney).toHaveBeenCalled();
  });

  it("离线重放后清除创建 preflight 并展示剩余 resume preflight", async () => {
    vi.mocked(analysisApi.readerJourneyPreflight).mockResolvedValue({
      analysis_run_id: 55,
      total_scenes: 14,
      remaining_scenes: 14,
      scene_batch_count: 9,
      expected_requests: 10,
      worst_case_requests: 20,
      estimated_tokens: 12000,
      worst_case_tokens: 24000,
      estimated_cost: 0.1,
      worst_case_cost: 0.2,
      within_budget: true,
      exceeded_dimensions: [],
      provider_state_version: "test",
      provider_name: "fake",
      eligible: true,
      blockers: [],
      requires_cloud_consent: false,
      currency: "CNY",
      planner_version: "1.1",
      batch_plan: ["Scene 1单独", "Scene 2—3", "Scene 4—5"],
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      journey_run_id: 2,
      status: "failed",
    } as any);

    const failedProgress = {
      journey_run_id: 2,
      analysis_run_id: 55,
      status: "failed",
      total_scene_count: 14,
      completed_scene_count: 0,
      remaining_scene_count: 14,
      completed_scene_ids: [],
      remaining_scene_ids: [6, 7, 8],
      phase_count: 0,
      has_chapter_summary: false,
      retryable: false,
      root_error_code: "STRUCTURAL_VALIDATION_FAILED",
      offline_replay_available: true,
      offline_replayable_scene_count: 1,
      offline_replayable_invocation_ids: [134],
      current_contract_version: "1.2",
      blind_resume_blocked: true,
      resume_block_reason: "offline_replay_required",
      recovery_safe: false,
      planner_version: "1.1",
      scene_contract_version: "1.1",
      reservation_released: true,
    };
    const partialProgress = {
      ...failedProgress,
      status: "scene_profiles_partial",
      completed_scene_count: 1,
      remaining_scene_count: 13,
      completed_scene_ids: [6],
      remaining_scene_ids: [7, 8, 9],
      offline_replay_available: false,
      offline_replayable_scene_count: 0,
      offline_replayable_invocation_ids: [],
      blind_resume_blocked: false,
      resume_block_reason: null,
      recovery_safe: true,
      scene_contract_version: "1.2",
      resume_preflight: {
        remaining_scenes: 13,
        scene_batch_count: 7,
        batch_plan: ["Scene 2—3", "Scene 4—5", "Scene 6—7"],
        expected_requests: 8,
        worst_case_requests: 16,
        estimated_cost: 0.08,
        planner_version: "1.1",
        scene_contract_version: "1.2",
        currency: "CNY",
      },
    };

    vi.mocked(analysisApi.readerJourneyProgress)
      .mockResolvedValueOnce(failedProgress as any)
      .mockResolvedValue(partialProgress as any);
    vi.mocked(analysisApi.offlineReplayReaderJourney).mockResolvedValue({
      journey_run_id: 2,
      replayed_scene_ids: [6],
      completed_count: 1,
      remaining_count: 13,
      source_invocation_ids: [134],
      migrated_from_contract_version: "1.1",
      current_contract_version: "1.2",
      http_requests: 0,
      tokens: 0,
      cost: 0,
      idempotent_replay: false,
    } as any);

    renderPage();
    await screen.findByTestId("structure-field-goal");
    fireEvent.click(screen.getByTestId("generate-reader-journey"));
    await waitFor(() => expect(screen.getByTestId("journey-preflight")).toBeInTheDocument());
    expect(screen.getByTestId("journey-batch-plan")).toHaveTextContent("Scene 1单独");

    fireEvent.click(screen.getByTestId("offline-replay-reader-journey"));
    await waitFor(() =>
      expect(screen.getByTestId("journey-offline-replay-success")).toHaveTextContent("离线重放成功"),
    );
    await waitFor(() => expect(screen.getByTestId("journey-resume-preflight")).toBeInTheDocument());
    expect(screen.queryByTestId("journey-preflight")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-batch-plan")).not.toHaveTextContent("Scene 1单独");
    expect(screen.getByTestId("journey-resume-preflight")).toHaveTextContent("7");
    expect(screen.getByTestId("journey-resume-preflight")).toHaveTextContent("8");

    const generate = screen.getByTestId("generate-reader-journey");
    expect(generate).toBeDisabled();
    expect(generate).toHaveTextContent("请先恢复剩余任务");

    fireEvent.click(screen.getByTestId("journey-cloud-consent"));
    const resume = screen.getByTestId("resume-reader-journey");
    expect(resume).not.toBeDisabled();
    expect(resume).toHaveTextContent("恢复剩余任务");
  });
});
